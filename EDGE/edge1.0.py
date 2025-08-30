#!/usr/bin/env python3

from http.server import HTTPServer, SimpleHTTPRequestHandler
import requests
import json
from collections import deque
import threading
import time
from urllib.parse import parse_qs
import csv
import os

# Executor IP
EDGE_IP = "192.168.17.115"

# Queues
high_priority_queue = deque()
low_priority_queue = deque()
queue_lock = threading.Lock()

# Maximum queue sizes
MAX_HIGH_QUEUE = 50
MAX_LOW_QUEUE = 50

# Snapshot configuration
SNAPSHOT_FILE = "queue_snapshot.csv"
SNAPSHOT_INTERVAL = 0.1  # seconds

# Initialize CSV file
if not os.path.exists(SNAPSHOT_FILE):
    with open(SNAPSHOT_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp",
            "high_queue_high", "high_queue_low",
            "low_queue_high", "low_queue_low"
        ])


class CustomHandler(SimpleHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            self.send_response(400)
            self.end_headers()
            return

        post_data = self.rfile.read(content_length)
        try:
            # Parse JSON or form data
            if self.headers.get('Content-Type') == 'application/json':
                data = json.loads(post_data.decode('utf-8'))
                request_number = data.get('request_number')
                priority_level = data.get('priority_level')
            else:
                parsed_data = parse_qs(post_data.decode('utf-8'))
                request_number = parsed_data.get('request_number', [None])[0]
                priority_level = parsed_data.get('priority_level', [None])[0]

            if not request_number or not priority_level:
                self.send_response(400)
                self.end_headers()
                return

            request_data = {
                "request_number": request_number,
                "priority_level": priority_level,
                "timestamp": time.time()
            }

            with queue_lock:
                if priority_level.lower() == "high":
                    if len(high_priority_queue) < MAX_HIGH_QUEUE:
                        high_priority_queue.append(request_data)
                        print(f"Added HIGH request {request_number} to HIGH queue ({len(high_priority_queue)})")
                    elif len(low_priority_queue) < MAX_LOW_QUEUE:
                        low_priority_queue.append(request_data)
                        print(f"Added HIGH request {request_number} to LOW queue ({len(low_priority_queue)})")
                    else:
                        print(f"Both queues full! Dropping HIGH request {request_number}")
                        self.send_response(503)
                        self.end_headers()
                        return
                else:  # Low-priority
                    if len(low_priority_queue) < MAX_LOW_QUEUE:
                        low_priority_queue.append(request_data)
                        print(f"Added LOW request {request_number} to LOW queue ({len(low_priority_queue)})")
                    else:
                        print(f"Low queue full! Dropping LOW request {request_number}")
                        self.send_response(503)
                        self.end_headers()
                        return

        except Exception as e:
            print(f"Error parsing request: {e}")
            self.send_response(400)
            self.end_headers()
            return

        self.send_response(200)
        self.end_headers()


def process_queue():
    """Process high-priority first, then low-priority requests."""
    while True:
        try:
            request_data = None
            with queue_lock:
                if high_priority_queue:
                    request_data = high_priority_queue.popleft()
                elif low_priority_queue:
                    request_data = low_priority_queue.popleft()

            if request_data:
                executor_url = f"http://{EDGE_IP}:80"
                host_header = f"{request_data['priority_level']}priorityfunc.default.{EDGE_IP}.sslip.io"
                payload = {
                    "request_number": request_data["request_number"],
                    "priority_level": request_data["priority_level"]
                }
                headers = {
                    "Host": host_header,
                    "Content-Type": "application/json"
                }
                try:
                    response = requests.post(executor_url, json=payload, headers=headers, timeout=30)
                    print(f"Processed {request_data['priority_level']} request {request_data['request_number']} - Status: {response.status_code}")
                except requests.exceptions.RequestException as e:
                    print(f"Error forwarding request {request_data['request_number']}: {e}")
            else:
                time.sleep(0.1)
        except Exception as e:
            print(f"Queue processor error: {e}")
            time.sleep(1)




LOG_FILE = "queue_totals.csv"

# Initialize log file if it doesn't exist
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "total_high", "total_low"])


def log_queue_counts():
    """Log total high and low requests every second to both console and file."""
    while True:
        try:
            with queue_lock:
                total_high = sum(1 for r in high_priority_queue if r["priority_level"].lower() == "high") + \
                             sum(1 for r in low_priority_queue if r["priority_level"].lower() == "high")
                total_low = sum(1 for r in high_priority_queue if r["priority_level"].lower() != "high") + \
                            sum(1 for r in low_priority_queue if r["priority_level"].lower() != "high")

            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            log_line = f"[{timestamp}] Total HIGH requests: {total_high}, Total LOW requests: {total_low}"

            # Print to console
            print(log_line)

            # Write to CSV
            with open(LOG_FILE, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([timestamp, total_high, total_low])

        except Exception as e:
            print(f"Logging error: {e}")

        time.sleep(1)



def run_server():
    host = '0.0.0.0'
    port = 8000
    server = HTTPServer((host, port), CustomHandler)

    threading.Thread(target=log_queue_counts, daemon=True).start()
    threading.Thread(target=process_queue, daemon=True).start()

    print(f"Server running at http://{host}:{port}")
    print(f"Queue snapshots every {int(SNAPSHOT_INTERVAL*1000)} ms to {SNAPSHOT_FILE}")
    print(f"High/Low priority queues enabled (max HIGH={MAX_HIGH_QUEUE}, LOW={MAX_LOW_QUEUE})")
    print("Press Ctrl+C to stop the server")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped")
        server.server_close()


if __name__ == '__main__':
    run_server()

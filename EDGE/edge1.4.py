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

# Executor IPs
EDGE_IP = "192.168.17.115"        # Main edge node
BACKUP_EDGE_IP = "192.168.17.89"  # Backup edge node for low-priority overflow

# Queues
high_priority_queue = deque()
low_priority_queue = deque()
queue_lock = threading.Lock()

# Maximum queue sizes
MAX_HIGH_QUEUE = 1000
MAX_LOW_QUEUE = 1000

# Counters for dropped requests
dropped_high_in_low = 0
dropped_low = 0

# Counters for forwarded requests
forwarded_high_to_backup = 0
forwarded_low_to_backup = 0

# Snapshot configuration
SNAPSHOT_FILE = "queue_snapshot.csv"
SNAPSHOT_INTERVAL = 0.1  # seconds

# Logging configuration
LOG_FILE = "queue_totals.csv"

# Initialize snapshot CSV
if not os.path.exists(SNAPSHOT_FILE):
    with open(SNAPSHOT_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp",
            "high_in_high_queue", "low_in_high_queue",
            "high_in_low_queue", "low_in_low_queue",
            "forwarded_high_to_backup", "forwarded_low_to_backup"
        ])

# Initialize totals CSV
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp",
            "total_queue",
            "high_in_high_queue", "low_in_high_queue",
            "high_in_low_queue", "low_in_low_queue",
            "dropped_high_in_low", "dropped_low",
            "forwarded_high_to_backup", "forwarded_low_to_backup"
        ])


class CustomHandler(SimpleHTTPRequestHandler):
    """Handles incoming POST requests and adds them to the appropriate queue."""
    def do_POST(self):
        global dropped_high_in_low, dropped_low, forwarded_low_to_backup
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
                    else:
                        # High queue full, try low queue
                        if len(low_priority_queue) < MAX_LOW_QUEUE:
                            low_priority_queue.appendleft(request_data)
                            print(f"Added HIGH request {request_number} to LOW queue front ({len(low_priority_queue)})")
                        else:
                            # Both full → drop one low and insert high
                            dropped_request = low_priority_queue.pop()
                            dropped_low += 1
                            low_priority_queue.appendleft(request_data)
                            print(f"Dropped LOW request {dropped_request['request_number']} to insert HIGH request {request_number}")
                            dropped_high_in_low += 1

                else:  # Low-priority
                    if len(low_priority_queue) < MAX_LOW_QUEUE:
                        low_priority_queue.append(request_data)
                        print(f"Added LOW request {request_number} to LOW queue ({len(low_priority_queue)})")
                    else:
                        # Low queue full → forward to backup edge
                        try:
                            executor_url = f"http://{BACKUP_EDGE_IP}:80"
                            host_header = f"{priority_level}priorityfunc.default.{BACKUP_EDGE_IP}.sslip.io"
                            payload = {
                                "request_number": request_number,
                                "priority_level": priority_level
                            }
                            headers = {
                                "Host": host_header,
                                "Content-Type": "application/json"
                            }
                            response = requests.post(executor_url, json=payload, headers=headers, timeout=10)
                            print(f"Forwarded LOW request {request_number} to BACKUP edge {BACKUP_EDGE_IP} - Status: {response.status_code}")
                            forwarded_low_to_backup += 1

                        except requests.exceptions.RequestException as e:
                            print(f"Error forwarding LOW request {request_number} to backup: {e}")
                            dropped_low += 1
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


def forward_request(request_data):
    """Send request to executor node."""
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


def process_high_queue():
    """Process high-priority requests in its own thread."""
    while True:
        request_data = None
        try:
            with queue_lock:
                if high_priority_queue:
                    request_data = high_priority_queue.popleft()

            if request_data:
                forward_request(request_data)
            else:
                time.sleep(0.05)

        except Exception as e:
            print(f"High queue processor error: {e}")
            time.sleep(1)


def process_low_queue():
    """Process low-priority requests in its own thread."""
    while True:
        request_data = None
        try:
            with queue_lock:
                if low_priority_queue:
                    request_data = low_priority_queue.popleft()

            if request_data:
                forward_request(request_data)
            else:
                time.sleep(0.05)

        except Exception as e:
            print(f"Low queue processor error: {e}")
            time.sleep(1)


def log_queue_counts():
    """Log detailed queue info every second."""
    global dropped_high_in_low, dropped_low, forwarded_high_to_backup, forwarded_low_to_backup
    while True:
        try:
            with queue_lock:
                high_in_high = sum(1 for r in high_priority_queue if r["priority_level"].lower() == "high")
                low_in_high  = sum(1 for r in high_priority_queue if r["priority_level"].lower() != "high")
                high_in_low  = sum(1 for r in low_priority_queue if r["priority_level"].lower() == "high")
                low_in_low   = sum(1 for r in low_priority_queue if r["priority_level"].lower() != "high")
                total_queue = len(high_priority_queue) + len(low_priority_queue)

            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            log_line = (f"[{timestamp}] Total queue: {total_queue}, "
                        f"High in HIGH queue: {high_in_high}, Low in HIGH queue: {low_in_high}, "
                        f"High in LOW queue: {high_in_low}, Low in LOW queue: {low_in_low}, "
                        f"Dropped HIGH in LOW: {dropped_high_in_low}, Dropped LOW: {dropped_low}, "
                        f"Forwarded HIGH to backup: {forwarded_high_to_backup}, Forwarded LOW to backup: {forwarded_low_to_backup}")
            
            print(log_line)

            with open(LOG_FILE, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([timestamp, total_queue, high_in_high, low_in_high, high_in_low, low_in_low,
                                 dropped_high_in_low, dropped_low, forwarded_high_to_backup, forwarded_low_to_backup])

        except Exception as e:
            print(f"Logging error: {e}")

        time.sleep(1)


def snapshot_queue():
    """Take fine-grained snapshots of queue contents."""
    global forwarded_high_to_backup, forwarded_low_to_backup
    while True:
        try:
            with queue_lock:
                high_in_high = sum(1 for r in high_priority_queue if r["priority_level"].lower() == "high")
                low_in_high  = sum(1 for r in high_priority_queue if r["priority_level"].lower() != "high")
                high_in_low  = sum(1 for r in low_priority_queue if r["priority_level"].lower() == "high")
                low_in_low   = sum(1 for r in low_priority_queue if r["priority_level"].lower() != "high")

            timestamp = time.time()
            with open(SNAPSHOT_FILE, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([timestamp, high_in_high, low_in_high, high_in_low, low_in_low,
                                 forwarded_high_to_backup, forwarded_low_to_backup])

        except Exception as e:
            print(f"Snapshot error: {e}")

        time.sleep(SNAPSHOT_INTERVAL)


def run_server():
    host = '0.0.0.0'
    port = 8000
    server = HTTPServer((host, port), CustomHandler)

    # Start background threads
    threading.Thread(target=log_queue_counts, daemon=True).start()
    threading.Thread(target=process_high_queue, daemon=True).start()
    threading.Thread(target=process_low_queue, daemon=True).start()
    threading.Thread(target=snapshot_queue, daemon=True).start()

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

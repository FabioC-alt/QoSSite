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
from datetime import datetime

# ---------- Configuration ----------
EDGE_IP = "192.168.17.115"
CLOUD_IP = "192.168.17.89"

MAX_HIGH_QUEUE = 50
MAX_LOW_QUEUE = 50
MAX_RETRIES = 3
RETRY_DELAY = 0.5  # seconds

SNAPSHOT_FILE = "queue_snapshot.csv"
LOG_FILE = "queue_totals.csv"
LATENCY_FILE = "latency_log.csv"
SCHEDULING_FILE = "scheduling_log.csv"

# ---------- Queues ----------
high_priority_queue = deque()
low_priority_queue = deque()
queue_lock = threading.Lock()

# ---------- CSV Initialization ----------
for file, headers in [
    (SNAPSHOT_FILE, ["timestamp","high_queue_high","high_queue_low","low_queue_high","low_queue_low"]),
    (LOG_FILE, ["timestamp","total_high","total_low"]),
    (LATENCY_FILE, ["request_number","priority_level","latency_ms","timestamp"]),
    (SCHEDULING_FILE, ["request_number","priority_level","scheduling_ms","timestamp"])
]:
    if not os.path.exists(file):
        with open(file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)

# ---------- Helper Functions ----------
def current_timestamp():
    """Return current wall-clock timestamp with milliseconds (for human-readable logs)."""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

def log_latency(request_data, latency_s):
    """Log total latency in ms"""
    latency_ms = latency_s * 1000
    timestamp = current_timestamp()
    try:
        with open(LATENCY_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([request_data["request_number"], request_data["priority_level"], round(latency_ms, 3), timestamp])
        print(f"Latency logged for request {request_data['request_number']} ({request_data['priority_level']}): {latency_ms:.3f} ms")
    except Exception as e:
        print(f"Error logging latency: {e}")

def log_scheduling(request_data, scheduling_s):
    """Log scheduling time in ms"""
    scheduling_ms = scheduling_s * 1000
    timestamp = current_timestamp()
    try:
        with open(SCHEDULING_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                request_data["request_number"],
                request_data["priority_level"],
                round(scheduling_ms, 3),
                timestamp
            ])
        print(f"Scheduling logged for request {request_data['request_number']} "
              f"({request_data['priority_level']}): {scheduling_ms:.3f} ms")
    except Exception as e:
        print(f"Error logging scheduling: {e}")

def send_post_with_retry(url, headers, payload, request_data):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            requests.post(url, json=payload, headers=headers, timeout=30)
            latency_s = time.perf_counter() - request_data["start_time"]
            log_latency(request_data, latency_s)
            return True
        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt} failed for request {request_data['request_number']}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
            else:
                print(f"Request {request_data['request_number']} failed after {MAX_RETRIES} attempts")
                return False

def forward_request(request_data, executor_ip):
    executor_url = f"http://{executor_ip}:80"
    host_header = f"{request_data['priority_level']}priorityfunc.default.{executor_ip}.sslip.io"
    headers = {"Host": host_header, "Content-Type": "application/json"}
    payload = {"request_number": request_data["request_number"], "priority_level": request_data["priority_level"]}
    send_post_with_retry(executor_url, headers, payload, request_data)
    print(f"Forwarded {request_data['priority_level']} request {request_data['request_number']} to {executor_ip}")

# ---------- HTTP Handler ----------
class CustomHandler(SimpleHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            self.send_response(400)
            self.end_headers()
            return

        post_data = self.rfile.read(content_length)
        try:
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

            now = time.perf_counter()
            request_data = {
                "request_number": request_number,
                "priority_level": priority_level,
                "start_time": now,      # per latenza totale
                "received_time": now    # per scheduling
            }

            with queue_lock:
                if priority_level.lower() == "high":
                    if len(high_priority_queue) < MAX_HIGH_QUEUE:
                        high_priority_queue.append(request_data)
                        print(f"Added HIGH request {request_number} to HIGH queue ({len(high_priority_queue)})")
                    else:
                        forward_request(request_data, CLOUD_IP)
                        self.send_response(200)
                        self.end_headers()
                        return
                else:
                    if len(low_priority_queue) < MAX_LOW_QUEUE:
                        low_priority_queue.append(request_data)
                        print(f"Added LOW request {request_number} to LOW queue ({len(low_priority_queue)})")
                    else:
                        forward_request(request_data, CLOUD_IP)
                        self.send_response(200)
                        self.end_headers()
                        return

        except Exception as e:
            print(f"Error parsing request: {e}")
            self.send_response(400)
            self.end_headers()
            return

        self.send_response(200)
        self.end_headers()

# ---------- Queue Processing ----------
def process_queue(queue, executor_ip, queue_name):
    while True:
        request_data = None
        with queue_lock:
            if queue:
                request_data = queue.popleft()

        if request_data:
            # Calcola tempo di scheduling
            scheduling_s = time.perf_counter() - request_data["received_time"]
            log_scheduling(request_data, scheduling_s)

            forward_request(request_data, executor_ip)
            print(f"Processed {queue_name} request {request_data['request_number']}")
        else:
            time.sleep(0.05)

# ---------- Queue Totals Logger ----------
def log_queue_counts():
    while True:
        try:
            with queue_lock:
                total_high = sum(1 for r in high_priority_queue if r["priority_level"].lower() == "high") + \
                             sum(1 for r in low_priority_queue if r["priority_level"].lower() == "high")
                total_low = sum(1 for r in high_priority_queue if r["priority_level"].lower() != "high") + \
                            sum(1 for r in low_priority_queue if r["priority_level"].lower() != "high")

            timestamp = current_timestamp()
            print(f"[{timestamp}] Total HIGH requests: {total_high}, Total LOW requests: {total_low}")

            with open(LOG_FILE, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([timestamp, total_high, total_low])
        except Exception as e:
            print(f"Logging error: {e}")

        time.sleep(1)

# ---------- Server Runner ----------
def run_server():
    host = '0.0.0.0'
    port = 8000
    server = HTTPServer((host, port), CustomHandler)

    # Start multiple high-priority workers
    HIGH_WORKERS = 1
    for _ in range(HIGH_WORKERS):
        threading.Thread(target=process_queue, args=(high_priority_queue, EDGE_IP, "HIGH"), daemon=True).start()

    # Start multiple low-priority workers
    LOW_WORKERS = 1
    for _ in range(LOW_WORKERS):
        threading.Thread(target=process_queue, args=(low_priority_queue, EDGE_IP, "LOW"), daemon=True).start()

    # Start logger
    threading.Thread(target=log_queue_counts, daemon=True).start()

    print(f"Server running at http://{host}:{port}")
    print(f"High/Low priority queues enabled (max HIGH={MAX_HIGH_QUEUE}, LOW={MAX_LOW_QUEUE})")
    print("Press Ctrl+C to stop the server")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped")
        server.server_close()

if __name__ == '__main__':
    run_server()

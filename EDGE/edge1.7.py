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
EDGE_IP = "192.168.17.115"
BACKUP_EDGE_IP = "192.168.17.89"

# Queues
high_priority_queue = deque()
low_priority_queue = deque()
queue_lock = threading.Lock()

# Maximum queue sizes
MAX_HIGH_QUEUE = 10
MAX_LOW_QUEUE = 10

# Counters
dropped_high_in_low = 0
dropped_low = 0
forwarded_high_to_backup = 0
forwarded_low_to_backup = 0

# Log files
LOG_FILE = "queue_totals.csv"
QUEUE_WAIT_LOG_FILE = "queue_wait_log.csv"

# Initialize CSV files
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp",
            "total_queue",
            "high_in_high",
            "low_in_high",
            "high_in_low",
            "low_in_low",
            "dropped_high_in_low",
            "dropped_low",
            "forwarded_high_to_backup",
            "forwarded_low_to_backup"
        ])

if not os.path.exists(QUEUE_WAIT_LOG_FILE):
    with open(QUEUE_WAIT_LOG_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp",
            "request_number",
            "priority_level",
            "target",
            "queue_wait_seconds"
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
                "enqueue_timestamp": time.time()
            }

            if priority_level.lower() == "high":
                insert_high_request(request_data)
            else:
                insert_low_request(request_data)

        except Exception as e:
            print(f"Error parsing request: {e}")
            self.send_response(400)
            self.end_headers()
            return

        self.send_response(200)
        self.end_headers()


# --- Queue waiting time logging ---
def log_queue_wait(request_data, target="main"):
    try:
        queue_wait = time.time() - request_data["enqueue_timestamp"]
        print(f"Queue wait for {request_data['priority_level']} request {request_data['request_number']} (to {target}) = {queue_wait:.4f}s")
        with open(QUEUE_WAIT_LOG_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([time.strftime('%Y-%m-%d %H:%M:%S'),
                             request_data["request_number"],
                             request_data["priority_level"],
                             target,
                             f"{queue_wait:.4f}"])
    except Exception as e:
        print(f"Error logging queue wait: {e}")


# --- Queue insertion logic ---
def insert_high_request(request_data):
    global dropped_high_in_low, dropped_low, forwarded_high_to_backup
    with queue_lock:
        if len(high_priority_queue) < MAX_HIGH_QUEUE:
            high_priority_queue.append(request_data)
            print(f"Added HIGH request {request_data['request_number']} to HIGH queue ({len(high_priority_queue)})")
        else:
            if len(low_priority_queue) < MAX_LOW_QUEUE:
                low_priority_queue.appendleft(request_data)
                print(f"Added HIGH request {request_data['request_number']} to LOW queue front ({len(low_priority_queue)})")
            else:
                # Drop low-priority request in low queue if any
                dropped_request = None
                for i in reversed(range(len(low_priority_queue))):
                    if low_priority_queue[i]["priority_level"].lower() != "high":
                        dropped_request = low_priority_queue.pop()
                        dropped_low += 1
                        break
                if dropped_request:
                    low_priority_queue.appendleft(request_data)
                    dropped_high_in_low += 1
                    print(f"Dropped LOW request {dropped_request['request_number']} to insert HIGH request {request_data['request_number']} in LOW queue")
                else:
                    # Forward oldest high-priority request to backup
                    oldest_high = high_priority_queue.popleft()
                    try:
                        executor_url = f"http://{BACKUP_EDGE_IP}:80"
                        host_header = f"{oldest_high['priority_level']}priorityfunc.default.{BACKUP_EDGE_IP}.sslip.io"
                        headers = {"Host": host_header, "Content-Type": "application/json"}
                        requests.post(executor_url, json=oldest_high, headers=headers, timeout=10)
                        forwarded_high_to_backup += 1
                        log_queue_wait(oldest_high, target="backup")
                    except requests.exceptions.RequestException as e:
                        print(f"Error forwarding HIGH request {oldest_high['request_number']} to backup: {e}")
                        dropped_high_in_low += 1

                    high_priority_queue.append(request_data)
                    print(f"Replaced OLDEST HIGH with new HIGH request {request_data['request_number']} in HIGH queue")


def insert_low_request(request_data):
    global forwarded_low_to_backup, dropped_low
    with queue_lock:
        if len(low_priority_queue) < MAX_LOW_QUEUE:
            low_priority_queue.append(request_data)
            print(f"Added LOW request {request_data['request_number']} to LOW queue ({len(low_priority_queue)})")
        else:
            # Forward to backup
            try:
                executor_url = f"http://{BACKUP_EDGE_IP}:80"
                host_header = f"{request_data['priority_level']}priorityfunc.default.{BACKUP_EDGE_IP}.sslip.io"
                headers = {"Host": host_header, "Content-Type": "application/json"}
                requests.post(executor_url, json=request_data, headers=headers, timeout=10)
                forwarded_low_to_backup += 1
                log_queue_wait(request_data, target="backup")
            except requests.exceptions.RequestException as e:
                print(f"Error forwarding LOW request {request_data['request_number']} to backup: {e}")
                dropped_low += 1


# --- Request forwarding ---
def forward_request(request_data):
    executor_url = f"http://{EDGE_IP}:80"
    host_header = f"{request_data['priority_level']}priorityfunc.default.{EDGE_IP}.sslip.io"
    headers = {"Host": host_header, "Content-Type": "application/json"}
    try:
        requests.post(executor_url, json=request_data, headers=headers, timeout=30)
        log_queue_wait(request_data, target="main")
    except requests.exceptions.RequestException as e:
        print(f"Error forwarding request {request_data['request_number']}: {e}")


# --- Queue processors ---
def process_high_queue():
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
    while True:
        request_data = None
        try:
            with queue_lock:
                for req in list(low_priority_queue):
                    if req["priority_level"].lower() == "high" and len(high_priority_queue) < MAX_HIGH_QUEUE:
                        high_priority_queue.append(req)
                        low_priority_queue.remove(req)
                        print(f"Moved HIGH request {req['request_number']} from LOW to HIGH queue")
                        break

                if low_priority_queue:
                    request_data = low_priority_queue.popleft()

            if request_data:
                forward_request(request_data)
            else:
                time.sleep(0.05)
        except Exception as e:
            print(f"Low queue processor error: {e}")
            time.sleep(1)


# --- Logging ---
def log_queue_counts():
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
            print(f"[{timestamp}] Total queue: {total_queue}, High in HIGH: {high_in_high}, Low in HIGH: {low_in_high}, High in LOW: {high_in_low}, Low in LOW: {low_in_low}, Dropped HIGH in LOW: {dropped_high_in_low}, Dropped LOW: {dropped_low}, Forwarded HIGH: {forwarded_high_to_backup}, Forwarded LOW: {forwarded_low_to_backup}")
            with open(LOG_FILE, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    timestamp, total_queue, high_in_high, low_in_high,
                    high_in_low, low_in_low, dropped_high_in_low,
                    dropped_low, forwarded_high_to_backup, forwarded_low_to_backup
                ])
        except Exception as e:
            print(f"Logging error: {e}")
        time.sleep(1)


# --- Server ---
def run_server():
    host = '0.0.0.0'
    port = 8000
    server = HTTPServer((host, port), CustomHandler)

    threading.Thread(target=log_queue_counts, daemon=True).start()
    threading.Thread(target=process_high_queue, daemon=True).start()
    threading.Thread(target=process_low_queue, daemon=True).start()

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

#!/usr/bin/env python3

import asyncio
import httpx
from aiohttp import web
import json
from collections import deque
import csv
import os
import time
from datetime import datetime
import psutil

# ---------- Configuration ----------
EDGE_IP = "192.168.17.115"  # Removed stray 's'
CLOUD_IP = "192.168.17.89"
ALLOW_CLOUD_FORWARD = True
CLOUD_FORWARD_DELAY = 0.5  # seconds

MAX_HIGH_QUEUE = 10
MAX_LOW_QUEUE = 10

SNAPSHOT_FILE = "queue_snapshot.csv"
LOG_FILE = "queue_totals.csv"
LATENCY_FILE = "latency_log.csv"
CLOUD_LATENCY_FILE = "cloud_latency_log.csv"
SCHEDULING_FILE = "scheduling_log.csv"
CPU_FILE = "cpu_usage.csv"
DEPLOYMENT_NAME = "edge"
NAMESPACE = "default"

# ---------- FaaS Deployments ----------
ALL_FAAS_HIGH = ["highpriorityfunc", "highpriorityfunc2","highpriorityfunc3", "highpriorityfunc4",
"highpriorityfunc5", "highpriorityfunc6","highpriorityfunc7","highpriorityfunc8"]
ALL_FAAS_LOW = ["lowpriorityfunc", "lowpriorityfunc2","highpriorityfunc3",
"highpriorityfunc4","highpriorityfunc5"]

USE_HIGH_FUNCS = 1
USE_LOW_FUNCS = 1

FAAS_HIGH = ALL_FAAS_HIGH[:USE_HIGH_FUNCS] if USE_HIGH_FUNCS > 0 else []
FAAS_LOW = ALL_FAAS_LOW[:USE_LOW_FUNCS] if USE_LOW_FUNCS > 0 else []

# ---------- Queues ----------
high_priority_queue = deque()
low_priority_queue = deque()
queue_lock = asyncio.Lock()

# ---------- Request Counter ----------
requests_this_second = 0

# ---------- CSV Initialization ----------
for file, headers in [
    (SNAPSHOT_FILE, ["timestamp","high_queue_high","high_queue_low","low_queue_high","low_queue_low"]),
    (LOG_FILE, ["timestamp","total_high","total_low"]),
    (LATENCY_FILE, ["request_number","priority_level","latency_seconds","timestamp"]),
    (CLOUD_LATENCY_FILE, ["request_number","priority_level","latency_seconds","timestamp"]),
    (SCHEDULING_FILE, ["request_number","priority_level","scheduling_seconds","timestamp"]),
    (CPU_FILE, ["timestamp","cpu_percent","rps"]),
]:
    if not os.path.exists(file):
        with open(file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)

# ---------- Helper Functions ----------
def current_timestamp():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

def log_latency(request_data, latency):
    timestamp = current_timestamp()
    with open(LATENCY_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([request_data["request_number"], request_data["priority_level"], round(latency, 6), timestamp])
    print(f"Latency logged for request {request_data['request_number']} ({request_data['priority_level']}): {latency:.6f}s")

def log_cloud_latency(request_data, latency):
    timestamp = current_timestamp()
    with open(CLOUD_LATENCY_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([request_data["request_number"], request_data["priority_level"], round(latency, 6), timestamp])
    print(f"Cloud latency logged for request {request_data['request_number']} ({request_data['priority_level']}): {latency:.6f}s")

def log_scheduling(request_data, scheduling_time):
    timestamp = current_timestamp()
    with open(SCHEDULING_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([request_data["request_number"], request_data["priority_level"], round(scheduling_time, 6), timestamp])
    print(f"Scheduling logged for request {request_data['request_number']} ({request_data['priority_level']}): {scheduling_time:.6f}s")

# ---------- CPU + RPS Logger ----------
def log_cpu_usage(rps):
    cpu_percent = psutil.cpu_percent(interval=None)
    timestamp = current_timestamp()
    with open(CPU_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([timestamp, cpu_percent, rps])
    print(f"CPU usage logged: {cpu_percent:.2f}% | RPS: {rps}")

async def log_cpu_usage_loop():
    global requests_this_second
    while True:
        rps = requests_this_second
        requests_this_second = 0
        log_cpu_usage(rps)
        await asyncio.sleep(1)

# ---------- Async Forward Request ----------
high_counter = 0
low_counter = 0

async def forward_request_async(request_data, priority_level, to_cloud=False):
    global high_counter, low_counter

    if priority_level.lower() == "high":
        target = FAAS_HIGH[high_counter % len(FAAS_HIGH)]
        high_counter += 1
    else:
        target = FAAS_LOW[low_counter % len(FAAS_LOW)]
        low_counter += 1

    executor_ip = CLOUD_IP if to_cloud else EDGE_IP
    url = f"http://{executor_ip}:80"
    headers = {"Host": f"{target}.default.{executor_ip}.sslip.io", "Content-Type": "application/json"}
    payload = {"request_number": request_data["request_number"], "priority_level": request_data["priority_level"]}

    if to_cloud and CLOUD_FORWARD_DELAY > 0:
        await asyncio.sleep(CLOUD_FORWARD_DELAY)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            await client.post(url, json=payload, headers=headers)
        latency = time.time() - request_data["timestamp"]
        if to_cloud:
            log_cloud_latency(request_data, latency)
        log_latency(request_data, latency)
        print(f"Forwarded {priority_level.upper()} request {request_data['request_number']} "
              f"{'(CLOUD)' if to_cloud else '(EDGE)'}")
    except Exception as e:
        print(f"Request {request_data['request_number']} failed: {e}")

def forward_request(request_data, priority_level, to_cloud=False):
    asyncio.create_task(forward_request_async(request_data, priority_level, to_cloud))

# ---------- HTTP Handler ----------
async def handle_post(request):
    global requests_this_second
    try:
        data = await request.json()
        request_number = data.get("request_number")
        priority_level = data.get("priority_level")
        if not request_number or not priority_level:
            return web.Response(status=400, text="Missing fields")

        request_data = {
            "request_number": request_number,
            "priority_level": priority_level,
            "timestamp": time.time(),
            "received_time": time.time()
        }

        async with queue_lock:
            if priority_level.lower() == "high":
                if not FAAS_HIGH:
                    return web.Response(status=503)
                if len(high_priority_queue) < MAX_HIGH_QUEUE:
                    high_priority_queue.append(request_data)
                    print(f"Added HIGH request {request_number} to HIGH queue ({len(high_priority_queue)})")
                elif ALLOW_CLOUD_FORWARD:
                    forward_request(request_data, "high", True)
                    return web.Response(status=200)
                else:
                    return web.Response(status=503)
            else:
                if not FAAS_LOW:
                    return web.Response(status=503)
                if len(low_priority_queue) < MAX_LOW_QUEUE:
                    low_priority_queue.append(request_data)
                    print(f"Added LOW request {request_number} to LOW queue ({len(low_priority_queue)})")
                elif ALLOW_CLOUD_FORWARD:
                    forward_request(request_data, "low", True)
                    return web.Response(status=200)
                else:
                    return web.Response(status=503)

        requests_this_second += 1
        return web.Response(status=200)

    except Exception as e:
        print(f"Error parsing request: {e}")
        return web.Response(status=400, text=str(e))

# ---------- Unified Scheduler ----------


async def unified_scheduler():
    while True:
        requests_to_process = []
        async with queue_lock:
            # Always empty the high-priority queue first
            while high_priority_queue:
                requests_to_process.append(high_priority_queue.popleft())

            # If no high requests remain, process lows
            if not requests_to_process:
                while low_priority_queue:
                    requests_to_process.append(low_priority_queue.popleft())

        if requests_to_process:
            # Log scheduling times
            for req in requests_to_process:
                scheduling_time = time.time() - req["received_time"]
                log_scheduling(req, scheduling_time)

            # Forward all requests concurrently
            await asyncio.gather(*[
                forward_request_async(req, req["priority_level"]) 
                for req in requests_to_process
            ])

        await asyncio.sleep(0.01)  # yield control

# ---------- Queue Logger ----------
async def log_queue_counts():
    while True:
        async with queue_lock:
            total_high = len(high_priority_queue)
            total_low = len(low_priority_queue)
        timestamp = current_timestamp()
        print(f"[{timestamp}] Total HIGH requests: {total_high}, Total LOW requests: {total_low}")
        with open(LOG_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, total_high, total_low])
        await asyncio.sleep(1)

# ---------- Queue Warning + Auto Scaling Monitor ----------
MAX_EDGE_REPLICAS = 1 # Set the maximum number of edge replicas

async def queue_warning_and_scale_monitor(namespace="default"):
    from kubernetes import client, config

    try:
        config.load_kube_config()  # local testing
    except:
        config.load_incluster_config()  # in-cluster

    apps_v1 = client.AppsV1Api()
    scaled_before = False

    while True:
        async with queue_lock:
            high_len = len(high_priority_queue)

        high_edge_usage = high_len / MAX_HIGH_QUEUE

        if high_edge_usage >= 0.8:
            print("HELP: Edge queue above 80%")

            if not scaled_before:
                try:
                    edge_dep = apps_v1.read_namespaced_deployment(DEPLOYMENT_NAME, namespace)
                    current_replicas = edge_dep.status.ready_replicas or 0
                    if current_replicas < MAX_EDGE_REPLICAS:
                        new_edge_replicas = min(current_replicas + 1, MAX_EDGE_REPLICAS)
                        body = {"spec": {"replicas": new_edge_replicas}}
                        apps_v1.patch_namespaced_deployment_scale(DEPLOYMENT_NAME, namespace, body)
                        print(f"Scaled EDGE deployment {DEPLOYMENT_NAME} to {new_edge_replicas} replicas")
                    else:
                        print(f"Edge deployment already at max replicas ({MAX_EDGE_REPLICAS})")
                    scaled_before = True
                except Exception as e:
                    print(f"Failed to scale deployments: {e}")
        else:
            scaled_before = False

        await asyncio.sleep(0.5)


# ---------- Server Runner ----------
async def main():
    app = web.Application()
    app.router.add_post('/', handle_post)

    # Start background tasks
    asyncio.create_task(unified_scheduler())
    asyncio.create_task(log_queue_counts())
    asyncio.create_task(log_cpu_usage_loop())
    asyncio.create_task(queue_warning_and_scale_monitor())

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8000)
    await site.start()
    print("Server running at http://0.0.0.0:8000")
    print(f"High priority functions: {FAAS_HIGH if FAAS_HIGH else 'DISABLED'}")
    print(f"Low priority functions: {FAAS_LOW if FAAS_LOW else 'DISABLED'}")
    print(f"Cloud forwarding: {'ENABLED' if ALLOW_CLOUD_FORWARD else 'DISABLED'} ({CLOUD_FORWARD_DELAY:.3f}s delay)")

    while True:
        await asyncio.sleep(3600) 
if __name__ == '__main__':
    asyncio.run(main()) 
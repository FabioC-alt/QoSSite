#!/usr/bin/env python3
import asyncio
from aiohttp import web, ClientSession
import json
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass

# Configuration
PORT = 8000
HOST = "0.0.0.0"

# Executors
edge = "192.168.17.115"
cloud = "192.168.17.89"

class ExecutorType(Enum):
    EDGE = "edge"
    CLOUD = "cloud"

@dataclass
class Executor:
    name: str
    address: str
    type: ExecutorType
    failure_count: int = 0
    is_healthy: bool = True
    current_load: float = 0.0

class SmartRequestRouter:
    def __init__(self):
        # Available executors
        self.executors = {
            ExecutorType.EDGE: Executor("edge-1", edge, ExecutorType.EDGE),
            ExecutorType.CLOUD: Executor("cloud-1", cloud, ExecutorType.CLOUD)
        }
        
        # Configurable thresholds for wait time (seconds)
        self.wait_thresholds = {
            'low': 2.0,      # < 2s -> Edge
            'medium': 5.0,   # 2–5s -> Round-robin
            'high': 5.0      # >= 5s -> Cloud
        }
        
        # For round-robin selection
        self.round_robin_counter = 0
        self.lock = asyncio.Lock()

    async def route_request(self, wait_time: float) -> str:
        """
        Smart routing based on waiting time.
        - Wait < low: Edge
        - Wait in [low, medium): Round-robin
        - Wait >= medium: Cloud
        """
        async with self.lock:
            if wait_time < self.wait_thresholds['low']:
                selected_executor = self.executors[ExecutorType.EDGE].address
                reasoning = f"Wait {wait_time:.2f}s < {self.wait_thresholds['low']}s -> Edge"

            elif wait_time < self.wait_thresholds['medium']:
                if self.round_robin_counter % 2 == 0:
                    selected_executor = self.executors[ExecutorType.EDGE].address
                    reasoning = f"Wait {wait_time:.2f}s in medium range -> Edge (round-robin)"
                else:
                    selected_executor = self.executors[ExecutorType.CLOUD].address
                    reasoning = f"Wait {wait_time:.2f}s in medium range -> Cloud (round-robin)"
                self.round_robin_counter += 1

            else:
                selected_executor = self.executors[ExecutorType.CLOUD].address
                reasoning = f"Wait {wait_time:.2f}s >= {self.wait_thresholds['medium']}s -> Cloud"

        print(f"🎯 Routing decision: {reasoning}")
        return selected_executor

# Global instances
router = SmartRequestRouter()

# Queues
high_priority_queue = asyncio.Queue()
low_priority_queue = asyncio.Queue()

async def serve_request(request_number, priority, executor, queue_timestamp):
    """Simulate serving a request by sending an HTTP request."""
    start_time = datetime.now(timezone.utc).isoformat()

    # Calculate queue wait time
    queue_time = datetime.fromisoformat(queue_timestamp.replace("Z", "+00:00"))
    wait_time = datetime.now(timezone.utc) - queue_time

    print(f"🚀 Serving request #{request_number} (priority={priority}), executor={executor}")
    print(f"   Queued at: {queue_timestamp}")
    print(f"   Wait time in queue: {wait_time.total_seconds():.2f} seconds")

    # Map priority to Host header
    host_header = f"{priority}priorityfunc.default.{executor}.sslip.io"
    url = f"http://{executor}"
    print(f"   Target URL: {url}")

    try:
        async with ClientSession() as session:
            async with session.get(url, headers={"Host": host_header}) as response:
                status = response.status
                text = await response.text()
                print(f"   HTTP {status}: {text}")
    except Exception as e:
        print(f"   Error sending HTTP request: {e}")

    end_time = datetime.now(timezone.utc).isoformat()
    print(f"✅ Completed request #{request_number} at {end_time}")

async def request_worker_high():
    """Worker for high priority requests (always Edge)."""
    while True:
        req = await high_priority_queue.get()
        req["executor"] = edge
        asyncio.create_task(
            serve_request(
                req["request_number"],
                req["priority"],
                req["executor"],
                req["QueueTimeStamp"],
            )
        )
        high_priority_queue.task_done()

async def request_worker_low():
    """Worker for low priority requests using SmartRequestRouter (wait-time-based)."""
    while True:
        req = await low_priority_queue.get()
        
        try:
            # Compute wait time
            queue_time = datetime.fromisoformat(req["QueueTimeStamp"].replace("Z", "+00:00"))
            wait_time = (datetime.now(timezone.utc) - queue_time).total_seconds()

            # Route request
            selected_executor = await router.route_request(wait_time)
            req["executor"] = selected_executor

            asyncio.create_task(
                serve_request(
                    req["request_number"],
                    req["priority"],
                    req["executor"],
                    req["QueueTimeStamp"],
                )
            )
            
        except Exception as e:
            print(f"❌ Error in request_worker_low: {e}")
            # Fallback to Edge
            req["executor"] = edge
            asyncio.create_task(
                serve_request(
                    req["request_number"],
                    req["priority"],
                    req["executor"],
                    req["QueueTimeStamp"],
                )
            )
        
        low_priority_queue.task_done()

async def handle_post(request):
    """Handle incoming POST requests to queue new tasks."""
    try:
        data = await request.json()
        request_number = data.get("request_number")
        priority = data.get("priority")

        if priority not in ["high", "low"]:
            return web.json_response(
                {"status": "error", "message": "Priority must be 'high' or 'low'"},
                status=400,
            )

        timestamp = datetime.now(timezone.utc).isoformat()
        request_data = {
            "request_number": request_number,
            "priority": priority,
            "QueueTimeStamp": timestamp,
        }

        if priority == "high":
            await high_priority_queue.put(request_data)
        else:
            await low_priority_queue.put(request_data)

        print(f"📥 Received request #{request_number} with priority: {priority}")
        return web.json_response({"status": "success", "queued_at": timestamp})

    except (json.JSONDecodeError, KeyError, TypeError):
        return web.json_response(
            {"status": "error", "message": "Invalid JSON format or missing fields"},
            status=400,
        )

async def handle_get(request):
    """Return the current queue status and routing info."""
    return web.json_response(
        {
            "queue_stats": {
                "high_priority_count": high_priority_queue.qsize(),
                "low_priority_count": low_priority_queue.qsize(),
                "total_queued": high_priority_queue.qsize() + low_priority_queue.qsize(),
            },
            "routing_config": {
                "wait_thresholds": router.wait_thresholds,
                "round_robin_counter": router.round_robin_counter,
            },
            "executors": {
                "edge": edge,
                "cloud": cloud,
            }
        }
    )

async def init_app():
    app = web.Application()
    app.router.add_post("/", handle_post)
    app.router.add_get("/", handle_get)
    return app

async def main():
    app = await init_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HOST, PORT)
    await site.start()

    print(f"🌐 Smart routing server running at http://{HOST}:{PORT}/")
    print("🎯 Using wait-time-based SmartRequestRouter for low priority requests")
    print("Press Ctrl+C to stop the server")

    # Start workers
    workers = [
        asyncio.create_task(request_worker_high()),
        asyncio.create_task(request_worker_low()),
    ]

    try:
        await asyncio.Future()  # run forever
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        for w in workers:
            w.cancel()
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())

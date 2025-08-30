#!/usr/bin/env python3
import asyncio
from aiohttp import web, ClientSession
import json
from datetime import datetime, timezone
import psutil
from enum import Enum
from dataclasses import dataclass
import random

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

@dataclass
class SystemMetrics:
    cpu_percentage: float = 0.0
    memory_percentage: float = 0.0
    active_requests: int = 0
    timestamp: datetime = None

class SmartRequestRouter:
    def __init__(self):
        # Available executors
        self.executors = {
            ExecutorType.EDGE: Executor("edge-1", edge, ExecutorType.EDGE),
            ExecutorType.CLOUD: Executor("cloud-1", cloud, ExecutorType.CLOUD)
        }
        
        self.system_metrics = SystemMetrics()
        
        # Configurable thresholds (matching original logic but improved)
        self.cpu_thresholds = {
            'low': 50.0,      # Under 50% - prefer edge (original < 50)
            'medium': 80.0,   # 50-80% - balanced approach (original 50-80 range)
            'high': 80.0      # Over 80% - prefer cloud (original > 80)
        }
        
        # For round-robin when CPU is in medium range (50-80%)
        self.round_robin_counter = 0
        self.lock = asyncio.Lock()
    
    def update_system_metrics(self, cpu_percent: float):
        """Update system metrics for routing decisions."""
        self.system_metrics.cpu_percentage = cpu_percent
        self.system_metrics.timestamp = datetime.now(timezone.utc)
    
    async def route_request(self) -> str:
        """
        Smart request routing that mimics original logic but with improvements.
        
        Original Logic:
        - CPU < 50%: edge
        - CPU 50-80% with alternating: edge (but broken alternation)
        - CPU > 80%: cloud
        
        Improved Logic:
        - CPU < 50%: edge (same as original)
        - CPU 50-80%: proper round-robin between edge and cloud
        - CPU > 80%: cloud (same as original)
        """
        cpu = self.system_metrics.cpu_percentage
        
        async with self.lock:  # Thread safety for round-robin counter
            if cpu < self.cpu_thresholds['low']:
                # Low CPU - use edge (matches original logic)
                selected_executor = self.executors[ExecutorType.EDGE].address
                reasoning = f"CPU {cpu:.1f}% < {self.cpu_thresholds['low']}% -> Edge"
                
            elif cpu < self.cpu_thresholds['medium']:
                # Medium CPU - proper round-robin (fixes original broken logic)
                if self.round_robin_counter % 2 == 0:
                    selected_executor = self.executors[ExecutorType.EDGE].address
                    reasoning = f"CPU {cpu:.1f}% in medium range -> Edge (round-robin)"
                else:
                    selected_executor = self.executors[ExecutorType.CLOUD].address
                    reasoning = f"CPU {cpu:.1f}% in medium range -> Cloud (round-robin)"
                
                self.round_robin_counter += 1
                
            else:
                # High CPU - use cloud (matches original logic)
                selected_executor = self.executors[ExecutorType.CLOUD].address
                reasoning = f"CPU {cpu:.1f}% >= {self.cpu_thresholds['medium']}% -> Cloud"
        
        print(f"🎯 Routing decision: {reasoning}")
        return selected_executor

# Global instances
router = SmartRequestRouter()

# State variables
cpu_percentage = 0

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
    print(f"   CPU Percentage: {cpu_percentage}")

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

async def cpu_monitor():
    """Background task to monitor CPU usage and update router."""
    global cpu_percentage
    while True:
        try:
            cpu_percentage = psutil.cpu_percent(interval=None)
            # Update router with current CPU metrics
            router.update_system_metrics(cpu_percentage)
        except Exception as e:
            print(f"Error getting CPU usage: {e}")
        await asyncio.sleep(1)

async def request_worker_high():
    """Worker for high priority requests (always edge)."""
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
    """Improved worker for low priority requests using SmartRequestRouter."""
    while True:
        req = await low_priority_queue.get()
        
        try:
            # Use SmartRequestRouter to decide executor
            selected_executor = await router.route_request()
            req["executor"] = selected_executor
            
            # Create async task to serve the request
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
            # Fallback to edge in case of routing error
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
                "total_queued": high_priority_queue.qsize()
                + low_priority_queue.qsize(),
            },
            "system_metrics": {
                "cpu_percentage": cpu_percentage,
                "timestamp": router.system_metrics.timestamp.isoformat() if router.system_metrics.timestamp else None,
            },
            "routing_config": {
                "cpu_thresholds": router.cpu_thresholds,
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
    print("🎯 Using SmartRequestRouter for low priority requests")
    print("Press Ctrl+C to stop the server")

    # Start workers
    workers = [
        asyncio.create_task(request_worker_high()),
        asyncio.create_task(request_worker_low()),
    ]
    cpu_task = asyncio.create_task(cpu_monitor())

    try:
        await asyncio.Future()  # run forever
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        for w in workers:
            w.cancel()
        cpu_task.cancel()
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
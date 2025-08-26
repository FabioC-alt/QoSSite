#!/usr/bin/env python3
from aiohttp import web
import json
import asyncio
from datetime import datetime, timezone
import psutil

# Configuration
PORT = 8000
HOST = "0.0.0.0"

# Storage for requests
high_priority_requests = []
low_priority_requests = []

# Lock for concurrency
storage_lock = asyncio.Lock()

async def serve_request(request_number, priority, executor, queue_timestamp):
    """Simulate serving a request by printing its number."""
    start_time = datetime.now(timezone.utc).isoformat()
    
    # Calculate queue wait time
    queue_time = datetime.fromisoformat(queue_timestamp.replace('Z', '+00:00'))
    wait_time = datetime.now(timezone.utc) - queue_time
    
    print(f"🚀 Serving request #{request_number} (priority={priority}), executor={executor}")
    print(f"   Queued at: {queue_timestamp}")
    print(f"   Wait time: {wait_time.total_seconds():.2f} seconds")
    print(f"   Cpu Percent: {getNodeForExecution()}")
    
    # simulate some work
    await asyncio.sleep(0.5)
    
    end_time = datetime.now(timezone.utc).isoformat()
    print(f"✅ Completed request #{request_number} at {end_time}")

def getNodeForExecution():
    """Get CPU usage percentage for node execution decision"""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        return cpu_percent
    except Exception as e:
        print(f"Error getting CPU usage: {e}")
        return None

async def request_processor():
    """Background task that always serves high priority requests first."""
    while True:
        await asyncio.sleep(0.1)  # avoid busy-looping
        
        async with storage_lock:
            if high_priority_requests:
                req = high_priority_requests.pop(0)
                req["executor"] = 1
            elif low_priority_requests:
                req = low_priority_requests.pop(0)
                req["executor"] = 1
            else:
                req = None
        
        if req:
            await serve_request(
                req["request_number"], 
                req["priority"], 
                req["executor"],
                req["QueueTimeStamp"]
            )

async def handle_post(request):
    try:
        data = await request.json()
        request_number = data.get("request_number")
        priority = data.get("priority")
        
        print(f"Received request #{request_number} with priority: {priority}")
        
        # Create timestamp in ISO format for JSON serialization
        timestamp = datetime.now(timezone.utc).isoformat()
        
        async with storage_lock:
            request_data = {
                "request_number": request_number,
                "priority": priority,  # Don't forget to store priority!
                "QueueTimeStamp": timestamp
            }
            
            if priority == "high":
                high_priority_requests.append(request_data)
            elif priority == "low":
                low_priority_requests.append(request_data)
            else:
                return web.json_response(
                    {"status": "error", "message": "Priority must be 'high' or 'low'"},
                    status=400,
                )
        
        return web.json_response({"status": "success", "queued_at": timestamp})
        
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        return web.json_response(
            {"status": "error", "message": "Invalid JSON format or missing fields"},
            status=400,
        )

async def handle_get(request):
    async with storage_lock:
        return web.json_response({
            "high_priority_requests": high_priority_requests,
            "low_priority_requests": low_priority_requests,
            "queue_stats": {
                "high_priority_count": len(high_priority_requests),
                "low_priority_count": len(low_priority_requests),
                "total_queued": len(high_priority_requests) + len(low_priority_requests)
            }
        })

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
    
    print(f"Async server running at http://{HOST}:{PORT}/")
    print("Press Ctrl+C to stop the server")
    
    # Start background processor
    processor_task = asyncio.create_task(request_processor())
    
    try:
        await asyncio.Future()  # run forever
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        processor_task.cancel()
        try:
            await processor_task
        except asyncio.CancelledError:
            pass
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
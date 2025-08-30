#!/usr/bin/env python3
import asyncio
from aiohttp import web, ClientSession
import json
from datetime import datetime, timezone

# Configuration
PORT = 8000
HOST = "0.0.0.0"

# Only one executor (high-priority FaaS = edge)
EDGE_EXECUTOR = "192.168.17.115"

# Queue for requests
request_queue = asyncio.Queue()

async def serve_request(request_number, priority, queue_timestamp):
    """Send request to the high-priority (edge) FaaS."""
    start_time = datetime.now(timezone.utc).isoformat()

    # Calculate wait time
    queue_time = datetime.fromisoformat(queue_timestamp.replace("Z", "+00:00"))
    wait_time = datetime.now(timezone.utc) - queue_time

    print(f"🚀 Serving request #{request_number} (priority={priority})")
    print(f"   Queued at: {queue_timestamp}, Waited {wait_time.total_seconds():.2f}s")
    print(f"   Executor: {EDGE_EXECUTOR}")

    url = f"http://{EDGE_EXECUTOR}"
    host_header = f"{priority}priorityfunc.default.{EDGE_EXECUTOR}.sslip.io"

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

async def request_worker():
    """Worker that processes queued requests (always to edge)."""
    while True:
        req = await request_queue.get()
        asyncio.create_task(
            serve_request(
                req["request_number"],
                req["priority"],
                req["QueueTimeStamp"],
            )
        )
        request_queue.task_done()

async def handle_post(request):
    """Handle incoming POST requests to queue new tasks."""
    try:
        data = await request.json()
        request_number = data.get("request_number")
        priority = data.get("priority", "high")

        timestamp = datetime.now(timezone.utc).isoformat()
        request_data = {
            "request_number": request_number,
            "priority": priority,
            "QueueTimeStamp": timestamp,
        }

        await request_queue.put(request_data)

        print(f"📥 Received request #{request_number}, priority={priority}")
        return web.json_response({"status": "queued", "queued_at": timestamp})

    except (json.JSONDecodeError, KeyError, TypeError):
        return web.json_response(
            {"status": "error", "message": "Invalid JSON format or missing fields"},
            status=400,
        )

async def handle_get(request):
    """Return queue status."""
    return web.json_response(
        {
            "queue_stats": {"count": request_queue.qsize()},
            "executor": EDGE_EXECUTOR,
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

    print(f"🌐 Server running at http://{HOST}:{PORT}/ (edge only)")
    print("Press Ctrl+C to stop")

    worker = asyncio.create_task(request_worker())

    try:
        await asyncio.Future()  # run forever
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        worker.cancel()
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())

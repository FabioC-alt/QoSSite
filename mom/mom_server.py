from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from collections import defaultdict
from queue import Queue, Empty
import threading
import uuid

app = FastAPI()

# In-memory queues and acknowledgment tracking
topics = defaultdict(Queue)  # topic -> Queue[(msg_id, message)]
pending_acks = defaultdict(dict)  # topic -> {msg_id: message}

# Publisher endpoint
@app.post("/publish/{topic}")
async def publish(topic: str, request: Request):
    body = await request.json()
    message = body.get("message")
    if not message:
        return JSONResponse(status_code=400, content={"error": "Missing message"})
    
    msg_id = str(uuid.uuid4())
    topics[topic].put((msg_id, message))
    pending_acks[topic][msg_id] = message

    return {"status": "Message published", "topic": topic, "message_id": msg_id}

# Subscriber endpoint
@app.get("/subscribe/{topic}")
def subscribe(topic: str):
    q = topics[topic]
    try:
        msg_id, message = q.get(timeout=5)
        return {"message_id": msg_id, "message": message}
    except Empty:
        return {"message": None}

# Acknowledge delivery
@app.post("/ack/{topic}")
async def acknowledge(topic: str, request: Request):
    body = await request.json()
    msg_id = body.get("message_id")
    if msg_id and msg_id in pending_acks[topic]:
        del pending_acks[topic][msg_id]
        return {"status": "Acknowledged", "message_id": msg_id}
    return JSONResponse(status_code=404, content={"error": "Message ID not found"})

# Optional: Check message status
@app.get("/status/{topic}")
def status(topic: str):
    return {"pending_acks": list(pending_acks[topic].keys())}


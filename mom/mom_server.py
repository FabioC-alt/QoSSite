from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from collections import defaultdict
from queue import Queue
import threading

app = FastAPI()
topics = defaultdict(Queue)

@app.post("/publish/{topic}")
async def publish(topic: str, request: Request):
    body = await request.json()
    message = body.get("message")
    if not message:
        return JSONResponse(status_code=400, content={"error": "Missing message"})
    topics[topic].put(message)
    return {"status": "Message published", "topic": topic}

@app.get("/subscribe/{topic}")
def subscribe(topic: str):
    q = topics[topic]
    try:
        message = q.get(timeout=5)  # Wait up to 5 seconds
        return {"message": message}
    except:
        return {"message": None}


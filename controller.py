import threading
import requests
import json
from collections import defaultdict
from flask import Flask, request

# Counter dictionary to track messages sent per topic
message_counter = defaultdict(int)

# Flask app for receiving acks
app = Flask(__name__)

@app.route('/ack/<topic>', methods=['POST'])
def ack(topic):
    if message_counter[topic] > 0:
        message_counter[topic] -= 1
        return f"Ack received for topic '{topic}'. Remaining: {message_counter[topic]}", 200
    else:
        return f"No outstanding messages for topic '{topic}'", 400

def run_ack_server():
    app.run(host='0.0.0.0', port=5000, debug=False)

# Function to send a message
def send_message(topic, message):
    url = f"http://mom:8000/publish/{topic}"
    headers = {"Content-Type": "application/json"}
    data = {"message": message}

    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        if response.status_code == 200:
            message_counter[topic] += 1
            print(f"[SENT] Message to '{topic}': {message}")
            print(f"[INFO] Total sent (pending ack) for '{topic}': {message_counter[topic]}")
        else:
            print(f"[ERROR] Failed to send message. Status code: {response.status_code}")
    except requests.RequestException as e:
        print(f"[ERROR] Exception during request: {e}")

# Main interactive loop
if __name__ == "__main__":
    # Start ack server in a background thread
    threading.Thread(target=run_ack_server, daemon=True).start()
    print("Ack server running at http://localhost:5000/ack/<topic>\n")

    while True:
        topic = input("Enter topic (or 'exit' to quit): ").strip()
        if topic.lower() == 'exit':
            break
        message = input("Enter message: ").strip()
        send_message(topic, message)


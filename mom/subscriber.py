import requests
import time

broker_url = "http://mom:8000"

def subscribe(topic):
    while True:
        res = requests.get(f"{broker_url}/subscribe/{topic}")
        data = res.json()
        if data["message"]:
            print(f"Received: {data['message']}")
        time.sleep(1)

if __name__ == "__main__":
    subscribe("chat")


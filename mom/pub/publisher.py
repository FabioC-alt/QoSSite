import requests
import time

broker_url = "http://mom:8000"  # Replace with Service name in K8s

def publish(topic, message):
    res = requests.post(f"{broker_url}/publish/{topic}", json={"message": message})
    print(res.json())

if __name__ == "__main__":
    for i in range(5):
        publish("chat", f"Hello #{i}")
        time.sleep(1)


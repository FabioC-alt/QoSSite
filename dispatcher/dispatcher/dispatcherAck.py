import requests
import time

broker_url = "http://mom:8000"
ack_url = "http://10.244.0.15:5000/ack/fabio"

def subscribe(topic):
    while True:
        try:
            res = requests.get(f"{broker_url}/subscribe/{topic}")
            data = res.json()
            if data["message"]:
                print(f"Received: {data['message']}")
                # Send acknowledgment
                try:
                    ack_res = requests.post(ack_url, json={"status": "received"})
                    if ack_res.ok:
                        print("ACK sent successfully.")
                    else:
                        print(f"ACK failed with status code: {ack_res.status_code}")
                except requests.RequestException as e:
                    print(f"Error sending ACK: {e}")
        except requests.RequestException as e:
            print(f"Error subscribing: {e}")
        time.sleep(1)

if __name__ == "__main__":
    subscribe("fabio")


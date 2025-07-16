from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import requests

HOST = '0.0.0.0'
PORT = 8080

# Kubernetes service DNS for the controller
CONTROLLER_URL_BASE = "http://controller-service.default.svc.cluster.local"  # change 'default' if needed

def trigger_action(level):
    if level not in ('low', 'high'):
        print(f"Unknown trigger level: {level}")
        return

    # Construct the forwarding URL
    url = f"{CONTROLLER_URL_BASE}/trigger?level={level}"
    try:
        response = requests.get(url, timeout=2)
        print(f"Forwarded to controller: {response.status_code} - {response.text}")
    except requests.RequestException as e:
        print(f"Error forwarding to controller: {e}")

class TriggerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)
        level = query_params.get('level', [None])[0]

        if level in ('low', 'high'):
            trigger_action(level)
            response = f"Trigger received for level: {level}\n"
        else:
            response = "Please provide 'level' as either 'low' or 'high'\n"

        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(response.encode())

def run_server():
    server_address = (HOST, PORT)
    httpd = HTTPServer(server_address, TriggerHandler)
    print(f'Serving HTTP trigger on http://{HOST}:{PORT}')
    httpd.serve_forever()

if __name__ == "__main__":
    run_server()


from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse
import requests

HOST = '0.0.0.0'
PORT = 8000
MOM_BASE_URL = 'http://mom:8000/publish'  # Base MOM URL

ALLOWED_LEVELS = {'high', 'low'}

class ControllerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urlparse(self.path)
        path_parts = parsed_url.path.strip("/").split("/")

        if len(path_parts) == 1 and path_parts[0] in ALLOWED_LEVELS:
            level = path_parts[0]
            print(f"Received trigger with level: {level}")

            try:
                mom_url = f"{MOM_BASE_URL}/{level}"
                payload = {'message': level}  # <-- Changed here to 'message'
                mom_response = requests.post(mom_url, json=payload)
                mom_response.raise_for_status()
                response = f"Level '{level}' forwarded to MOM at {mom_url}\n"
                self.send_response(200)
            except requests.exceptions.RequestException as e:
                print(f"Error posting to MOM: {e}")
                response = f"Failed to post to MOM: {e}\n"
                self.send_response(502)
        else:
            response = "Invalid or missing priority level. Use /high or /low\n"
            self.send_response(400)

        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(response.encode())

def run_server():
    server_address = (HOST, PORT)
    httpd = HTTPServer(server_address, ControllerHandler)
    print(f"Controller listening on http://{HOST}:{PORT}")
    httpd.serve_forever()

if __name__ == "__main__":
    run_server()


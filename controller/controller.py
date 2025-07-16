from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

HOST = '0.0.0.0'
PORT = 8000  # Change as needed

class ControllerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)
        level = query_params.get('level', [None])[0]

        if level:
            print(f"Received trigger with level: {level}")
            response = f"Level received: {level}\n"
            self.send_response(200)
        else:
            response = "Missing 'level' parameter\n"
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


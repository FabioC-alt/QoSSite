import asyncio
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from nats.aio.client import Client as NATS

HOST = '0.0.0.0'
PORT = 8000
NATS_URL = "nats://my-nats:4222"
ALLOWED_LEVELS = {'high', 'low'}
NUM_CHANNELS = 3  # Number of balanced channels

# Dynamically generate channel names: channel1, channel2, ...
CHANNELS = [f"channel{i+1}" for i in range(NUM_CHANNELS)]

nc = NATS()
loop = None

request_counts = {ch: {'high': 0, 'low': 0} for ch in CHANNELS}


class ControllerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urlparse(self.path)
        path_parts = parsed_url.path.strip("/").split("/")

        if len(path_parts) == 1 and path_parts[0] in ALLOWED_LEVELS:
            level = path_parts[0]

            try:
                channel = min(CHANNELS, key=lambda ch: request_counts[ch][level])
                subject = f"{channel}.{level}"

                asyncio.run_coroutine_threadsafe(
                    nc.publish(subject, level.encode()),
                    loop
                ).result()

                request_counts[channel][level] += 1

                response = (
                    f"Level '{level}' published to least loaded channel '{channel}' "
                    f"on subject '{subject}'\n"
                )
                self.send_response(200)
            except Exception as e:
                print(f"Error publishing to NATS: {e}")
                response = f"Failed to publish to NATS: {e}\n"
                self.send_response(502)
        else:
            response = "Invalid or missing priority level. Use /high or /low\n"
            self.send_response(400)

        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(response.encode())


async def print_request_counts():
    while True:
        await asyncio.sleep(5)
        print("Request counts per channel:")
        for ch in CHANNELS:
            counts = request_counts[ch]
            print(f"  {ch}: high={counts['high']}, low={counts['low']}")


async def main():
    global loop
    loop = asyncio.get_running_loop()

    await nc.connect(servers=[NATS_URL])
    server = ThreadingHTTPServer((HOST, PORT), ControllerHandler)
    print(f"Controller listening on http://{HOST}:{PORT}")

    asyncio.create_task(print_request_counts())

    await loop.run_in_executor(None, server.serve_forever)


if __name__ == "__main__":
    asyncio.run(main())


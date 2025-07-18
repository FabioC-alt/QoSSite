import asyncio
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import aio_pika

HOST = '0.0.0.0'
PORT = 8000
RABBITMQ_URL = "amqp://myuser:mypassword@my-rabbitmq:5672/"
ALLOWED_LEVELS = {'high', 'low'}
NUM_CHANNELS = 1  # Number of balanced channels

# Dynamically generate channel names: channel1, channel2, ...
CHANNELS = [f"channel{i}" for i in range(NUM_CHANNELS)]

# Track message counts per channel and level
request_counts = {ch: {'high': 0, 'low': 0} for ch in CHANNELS}

# Global variables for RabbitMQ connection and channel
connection = None
channel = None
exchange = None
loop = None


class ControllerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urlparse(self.path)
        path_parts = parsed_url.path.strip("/").split("/")

        if len(path_parts) == 1 and path_parts[0] in ALLOWED_LEVELS:
            level = path_parts[0]

            try:
                # Find least loaded channel for this level
                channel_name = min(CHANNELS, key=lambda ch: request_counts[ch][level])
                routing_key = f"{channel_name}.{level}"

                # Publish message asynchronously
                asyncio.run_coroutine_threadsafe(
                    publish_message(routing_key, level.encode()),
                    loop
                ).result()

                # Update request counts
                request_counts[channel_name][level] += 1

                response = (
                    f"Level '{level}' published to least loaded channel '{channel_name}' "
                    f"with routing key '{routing_key}'\n"
                )
                self.send_response(200)
            except Exception as e:
                print(f"Error publishing to RabbitMQ: {e}")
                response = f"Failed to publish to RabbitMQ: {e}\n"
                self.send_response(502)
        else:
            response = "Invalid or missing priority level. Use /high or /low\n"
            self.send_response(400)

        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(response.encode())

    def do_POST(self):
        parsed_url = urlparse(self.path)
        if parsed_url.path == "/decrement":
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"No JSON body provided\n")
                return

            body = self.rfile.read(content_length)
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Invalid JSON\n")
                return

            channel = data.get("channel")
            level = data.get("level")

            if channel not in CHANNELS:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(f"Invalid channel: {channel}\n".encode())
                return

            if level not in ALLOWED_LEVELS:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(f"Invalid level: {level}\n".encode())
                return

            # Decrement safely (not below zero)
            if request_counts[channel][level] > 0:
                request_counts[channel][level] -= 1
                self.send_response(200)
                response = f"Decremented count for {channel} at level {level}\n"
            else:
                self.send_response(200)
                response = f"Count already zero for {channel} at level {level}\n"

            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(response.encode())

        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Unknown POST endpoint\n")

async def publish_message(routing_key: str, message_body: bytes):
    # Publish a persistent message to the exchange with the routing key
    await exchange.publish(
        aio_pika.Message(body=message_body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
        routing_key=routing_key
    )


async def print_request_counts():
    while True:
        await asyncio.sleep(5)
        print("Request counts per channel:")
        for ch in CHANNELS:
            counts = request_counts[ch]
            print(f"  {ch}: high={counts['high']}, low={counts['low']}")


async def main():
    global loop, connection, channel, exchange
    loop = asyncio.get_running_loop()

    # Connect to RabbitMQ
    connection = await aio_pika.connect_robust(RABBITMQ_URL, loop=loop)
    channel = await connection.channel()

    # Declare a direct exchange for routing messages based on routing key
    exchange = await channel.declare_exchange('levels_exchange', aio_pika.ExchangeType.DIRECT, durable=True)

    # Optionally, declare queues and bind to exchange for each channel and level
    for ch in CHANNELS:
        for level in ALLOWED_LEVELS:
            queue_name = f"{ch}.{level}"
            queue = await channel.declare_queue(queue_name, durable=True)
            await queue.bind(exchange, routing_key=queue_name)

    server = ThreadingHTTPServer((HOST, PORT), ControllerHandler)
    print(f"Controller listening on http://{HOST}:{PORT}")

    asyncio.create_task(print_request_counts())

    await loop.run_in_executor(None, server.serve_forever)


if __name__ == "__main__":
    asyncio.run(main())


import asyncio
import json
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import aio_pika
from threading import Lock
import time
from opentelemetry import trace
from opentelemetry.context import attach, detach
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

# Config
HOST = '0.0.0.0'
PORT = 8000
RABBITMQ_URL = "amqp://myuser:mypassword@my-rabbitmq:5672/"
ALLOWED_LEVELS = {'high', 'low'}
NUM_CHANNELS = 1
CHANNELS = [f"channel{i}" for i in range(NUM_CHANNELS)]
request_counts = {ch: {'high': 0, 'low': 0} for ch in CHANNELS}
counts_lock = Lock()

# Tracing setup
trace.set_tracer_provider(
    TracerProvider(resource=Resource.create({SERVICE_NAME: "controller"}))
)
tracer = trace.get_tracer("controller")
jaeger_exporter = JaegerExporter(
    collector_endpoint="http://jaeger.observability.svc.cluster.local:14268/api/traces"
)
trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(jaeger_exporter))

# Globals for async RabbitMQ
connection = None
channel = None
exchange = None
loop = None

class ControllerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        carrier = dict(self.headers)
        ctx = TraceContextTextMapPropagator().extract(carrier)
        token = attach(ctx)

        with tracer.start_as_current_span("handle_GET") as span:
            parsed_url = urlparse(self.path)
            path_parts = parsed_url.path.strip("/").split("/")

            if len(path_parts) == 1 and path_parts[0] in ALLOWED_LEVELS:
                level = path_parts[0]
                span.set_attribute("request.level", level)

                try:
                    with counts_lock:
                        channel_name = min(CHANNELS, key=lambda ch: request_counts[ch][level])
                        request_counts[channel_name][level] += 1
                    routing_key = f"{channel_name}.{level}"
                    span.set_attribute("request.channel", channel_name)
                    span.set_attribute("request.routing_key", routing_key)

                    future = asyncio.run_coroutine_threadsafe(
                        publish_message(routing_key, level.encode()),
                        loop
                    )
                    future.result()

                    response = (
                        f"Level '{level}' published to channel '{channel_name}' "
                        f"with routing key '{routing_key}'\n"
                    )
                    self.send_response(200)
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(trace.status.Status(trace.status.StatusCode.ERROR, str(e)))
                    response = f"Failed to publish to RabbitMQ: {e}\n"
                    self.send_response(502)
            else:
                response = "Invalid level. Use /high or /low\n"
                self.send_response(400)

            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(response.encode())

        detach(token)

    def do_POST(self):
        carrier = dict(self.headers)
        ctx = TraceContextTextMapPropagator().extract(carrier)
        token = attach(ctx)

        with tracer.start_as_current_span("handle_POST") as span:
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
                except json.JSONDecodeError as e:
                    span.record_exception(e)
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Invalid JSON\n")
                    return

                channel_name = data.get("channel")
                level = data.get("level")

                span.set_attribute("decrement.channel", channel_name)
                span.set_attribute("decrement.level", level)

                if channel_name not in CHANNELS or level not in ALLOWED_LEVELS:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Invalid channel or level\n")
                    return

                with counts_lock:
                    if request_counts[channel_name][level] > 0:
                        request_counts[channel_name][level] -= 1
                        response = f"Decremented count for {channel_name} at level {level}\n"
                    else:
                        response = f"Count already zero for {channel_name} at level {level}\n"

                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(response.encode())
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Unknown POST endpoint\n")

        detach(token)

async def publish_message(routing_key: str, message_body: bytes):
    with tracer.start_as_current_span("publish_message") as span:
        span.set_attribute("publish.routing_key", routing_key)

        # Inject trace context into RabbitMQ message headers
        headers = {}
        TraceContextTextMapPropagator().inject(headers)
        
        headers["send_ts"] = str(time.time())
        
        
        message = aio_pika.Message(
            body=message_body,
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            headers=headers
        )

        await exchange.publish(message, routing_key=routing_key)

async def print_request_counts():
    while True:
        await asyncio.sleep(5)
        print("Request counts per channel:")
        with counts_lock:
            for ch in CHANNELS:
                counts = request_counts[ch]
                print(f"  {ch}: high={counts['high']}, low={counts['low']}")

async def main():
    global loop, connection, channel, exchange
    loop = asyncio.get_running_loop()

    connection = await aio_pika.connect_robust(RABBITMQ_URL, loop=loop)
    channel = await connection.channel()

    exchange = await channel.declare_exchange('levels_exchange', aio_pika.ExchangeType.DIRECT, durable=True)

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


import asyncio
import aio_pika
import aiohttp
import logging
import signal
import sys
import json
import time

from opentelemetry import trace, context
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

rabbitmq_host = "my-rabbitmq.default.svc.cluster.local"
rabbitmq_port = 5672
username = "myuser"
password = "mypassword"

stop_event = asyncio.Event()

curl_target_url = "http://192.168.17.121:30081/decrement"
ip_executor = "192.168.17.118"

# OpenTelemetry setup
trace.set_tracer_provider(
    TracerProvider(resource=Resource.create({SERVICE_NAME: "dispatcher"}))
)
tracer = trace.get_tracer("dispatcher")
jaeger_exporter = JaegerExporter(
    collector_endpoint="http://jaeger.observability.svc.cluster.local:14268/api/traces"
)
trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(jaeger_exporter))

def shutdown():
    logging.info("Shutdown signal received. Stopping consumer...")
    stop_event.set()

async def consume_queue(queue_name, channel):
    queue = await channel.declare_queue(queue_name, durable=True)
    logging.info(f"Waiting for messages on queue '{queue_name}'...")

    async with queue.iterator() as queue_iter, aiohttp.ClientSession() as session:
        async for message in queue_iter:
            if stop_event.is_set():
                break

            # Extract trace context from message headers
            headers = {}
            if message.headers:
                # RabbitMQ headers can be nested or byte encoded, normalize if needed
                for k, v in message.headers.items():
                    if isinstance(v, bytes):
                        headers[k] = v.decode()
                    else:
                        headers[k] = str(v)

            ctx = TraceContextTextMapPropagator().extract(headers)
            
            token = context.attach(ctx)
            
            send_ts = float(headers.get("send_ts", 0))  # This is the sender's time.time()
            recv_ts = time.time()                      # This is now

            latency = recv_ts - send_ts

            logging.info(f"Latency: {latency:.6f} seconds")
            try:
                async with message.process():
                    decoded = message.body.decode()
                    logging.info(f"[{queue_name}] Received message: {decoded}")

                    with tracer.start_as_current_span(f"process_message_{queue_name}") as span:
                        span.set_attribute("messaging.system", "rabbitmq")
                        span.set_attribute("messaging.destination", queue_name)
                        span.set_attribute("messaging.message_payload_size_bytes", len(message.body))
                        if queue_name == "channel0.high":
                            headers = {
                                "Host": f"highpriorityfunc.default.{ip_executor}.sslip.io"
                            }
                            url = f"http://{ip_executor}"
                            priority = "high"
                        else:
                            headers = {
                                "Host": f"lowpriorityfunc.default.{ip_executor}.sslip.io"
                            }
                            url = f"http://{ip_executor}"
                            priority = "low"

                        # Inject current trace context into HTTP headers for downstream propagation
                        http_headers = {}
                        TraceContextTextMapPropagator().inject(http_headers)
                        # Merge with your custom headers for the request
                        http_headers.update(headers)

                        # Send GET request with tracing headers
                        with tracer.start_as_current_span(f"FaaS_calling_{priority}") as span:
                            span.set_attribute("faas.system", "knative")

                            async with session.get(url, headers=http_headers) as resp:
                                resp_text = await resp.text()
                                logging.info(f"[{queue_name}] HTTP {resp.status}: {resp_text}")
                                span.set_attribute("http.status_code", resp.status)

                        channel_base = queue_name.split('.')[0]

                        # Prepare JSON data to POST (tracing context injected here too)
                        json_data = {
                            "channel": channel_base,
                            "level": priority,
                        }

                        # For POST also propagate trace context
                        post_headers = {}
                        TraceContextTextMapPropagator().inject(post_headers)

                        async with session.post(curl_target_url, json=json_data, headers=post_headers) as post_resp:
                            post_resp_text = await post_resp.text()
                            logging.info(f"[{queue_name}] POST {post_resp.status}: {post_resp_text}")
                            span.set_attribute("http.post_status_code", post_resp.status)

            except Exception as e:
                logging.error(f"[{queue_name}] Failed to process message: {e}")
            finally:
                context.detach(token)


async def main():
    try:
        connection = await aio_pika.connect_robust(
            host=rabbitmq_host,
            port=rabbitmq_port,
            login=username,
            password=password,
        )
        logging.info(f"Connected to RabbitMQ at {rabbitmq_host}:{rabbitmq_port}")

        channel = await connection.channel()
        await channel.set_qos(prefetch_count=1)

        # High priority: 5 workers
        high_priority_tasks = [
            asyncio.create_task(consume_queue("channel0.high", channel))
            for _ in range(5)
        ]

        # Low priority: 1 worker
        low_priority_tasks = [
            asyncio.create_task(consume_queue("channel0.low", channel))
        ]

        tasks = high_priority_tasks + low_priority_tasks

        await stop_event.wait()

        # Cancel all running tasks on shutdown
        for task in tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logging.info("Consumer task cancelled.")

        await connection.close()
        logging.info("Connection closed gracefully.")
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Interrupted by user.")


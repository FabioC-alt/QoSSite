import asyncio
import aio_pika
import aiohttp
import logging
import signal
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

rabbitmq_host = "my-rabbitmq.default.svc.cluster.local"
rabbitmq_port = 5672
username = "myuser"
password = "mypassword"

queue_names = ["channel0.high", "channel0.low"]
stop_event = asyncio.Event()


def shutdown():
    logging.info("Shutdown signal received. Stopping consumer...")
    stop_event.set()


async def consume_queue(queue_name, channel):
    queue = await channel.declare_queue(queue_name, durable=True)
    logging.info(f"Waiting for messages on queue '{queue_name}'...")

    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            if stop_event.is_set():
                break
            async with message.process():
                decoded = message.body.decode()
                logging.info(f"[{queue_name}] Received message: {decoded}")

                if queue_name == "channel0.high":
                    # Send HTTP request when high priority message is received
                    async with aiohttp.ClientSession() as session:
                        try:
                            headers = {
                                "Host": "highpriorityfunc.default.192.168.17.118.sslip.io"
                            }
                            url = "http://192.168.17.118"
                            async with session.get(url, headers=headers) as resp:
                                resp_text = await resp.text()
                                logging.info(f"[{queue_name}] HTTP {resp.status}: {resp_text}")
                        except Exception as e:
                            logging.error(f"[{queue_name}] Failed to send HTTP request: {e}")


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

        # Start consumers
        tasks = [asyncio.create_task(consume_queue(q, channel)) for q in queue_names]

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


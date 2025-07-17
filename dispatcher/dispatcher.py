import asyncio
import aio_pika
import logging
import signal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

rabbitmq_host = "my-rabbitmq.default.svc.cluster.local"
rabbitmq_port = 5672
username = "myuser"
password = "mypassword"

queue_names = ["channel0.high", "channel0.low"]

stop_event = asyncio.Event()
loop = asyncio.get_event_loop()

def shutdown():
    logging.info("Shutdown signal received. Stopping consumer...")
    loop.call_soon_threadsafe(stop_event.set)

async def consume_queue(queue_name, channel):
    queue = await channel.declare_queue(queue_name, durable=True)
    logging.info(f"Waiting for messages on queue '{queue_name}'...")

    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            if stop_event.is_set():
                break
            async with message.process():
                logging.info(f"[{queue_name}] Received message: {message.body.decode()}")

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

        # Start a consumer task for each queue
        tasks = [asyncio.create_task(consume_queue(q, channel)) for q in queue_names]

        # Wait until stop_event is set
        await stop_event.wait()

        # Cancel consumer tasks on shutdown
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

if __name__ == "__main__":
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown)

    try:
        loop.run_until_complete(main())
    finally:
        loop.close()


import asyncio
import aio_pika
import aiohttp
import logging
import signal
import sys
import json

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

rabbitmq_host = "my-rabbitmq.default.svc.cluster.local"
rabbitmq_port = 5672
username = "myuser"
password = "mypassword"

stop_event = asyncio.Event()

# Replace this with your actual endpoint when ready
curl_target_url = "http://192.168.17.121:30081/decrement"



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
            async with message.process():
                decoded = message.body.decode()
                logging.info(f"[{queue_name}] Received message: {decoded}")

                try:
                    if queue_name == "channel0.high":
                        headers = {
                            "Host": "highpriorityfunc.default.192.168.17.118.sslip.io"
                        }
                        url = "http://192.168.17.118"
                        priority = "high"
                    else:
                        headers = {
                            "Host": "lowpriorityfunc.default.192.168.17.118.sslip.io"
                        }
                        url = "http://192.168.17.118"
                        priority = "low"

                    # Send GET request to the function endpoint
                    async with session.get(url, headers=headers) as resp:
                        resp_text = await resp.text()
                        logging.info(f"[{queue_name}] HTTP {resp.status}: {resp_text}")

                    channel_base = queue_name.split('.')[0]
                    
                    # Prepare and send JSON data via POST
                    json_data = {
                        "channel": channel_base,
                        "level": priority,
                    }

                    async with session.post(curl_target_url, json=json_data) as post_resp:
                        post_resp_text = await post_resp.text()
                        logging.info(f"[{queue_name}] POST {post_resp.status}: {post_resp_text}")

                except Exception as e:
                    logging.error(f"[{queue_name}] Failed to process message: {e}")


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


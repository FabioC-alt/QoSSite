import asyncio
import aio_pika
import sys

RABBITMQ_URL = "amqp://myuser:mypassword@my-rabbitmq:5672/"
ALLOWED_LEVELS = {'high', 'low'}

async def on_message(message: aio_pika.IncomingMessage):
    async with message.process():
        print(f"[{message.routing_key}] Received: {message.body.decode()}")

async def run_dispatcher(channel_name: str):
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    channel = await connection.channel()

    exchange = await channel.declare_exchange('levels_exchange', aio_pika.ExchangeType.DIRECT, durable=True)

    for level in ALLOWED_LEVELS:
        queue_name = f"{channel_name}.{level}"
        queue = await channel.declare_queue(queue_name, durable=True)
        await queue.bind(exchange, routing_key=queue_name)
        await queue.consume(on_message)

    print(f"Dispatcher for '{channel_name}' is listening on '{channel_name}.high' and '{channel_name}.low' queues...")
    await asyncio.Future()  # Run forever

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python dispatcher.py <channel_name>")
        print("Example: python dispatcher.py channel1")
        sys.exit(1)

    channel_to_listen = sys.argv[1]
    asyncio.run(run_dispatcher(channel_to_listen))


import asyncio
from nats.aio.client import Client as NATS

async def main():
    print("Script Started")
    nc = NATS()

    await nc.connect("nats://10.43.34.220:4222")  # Use your service name if in K8s

    async def handle_high(msg):
        print("🔴 High priority task received")

    async def handle_medium(msg):
        print("🟡 Medium priority task received")

    async def handle_low(msg):
        print("🟢 Low priority task received")

    # Subscribe to each subject
    await nc.subscribe("priority.high", cb=handle_high)
    await nc.subscribe("priority.medium", cb=handle_medium)
    await nc.subscribe("priority.low", cb=handle_low)

    print("🟢 Listening for messages on priority.high|medium|low...")

    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())


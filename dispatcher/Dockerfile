FROM python:3.11-slim
WORKDIR /app
COPY dispatcher.py .
RUN pip install aio-pika
RUN pip install aiohttp

CMD ["python", "dispatcher.py"]



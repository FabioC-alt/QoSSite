FROM python:3.11-slim
WORKDIR /app
COPY dispatcher.py .
RUN pip install aio-pika
CMD ["python", "dispatcher.py"]


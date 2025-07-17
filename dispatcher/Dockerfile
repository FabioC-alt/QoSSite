# Use official Python image
FROM python:3.11-slim

# Set working directory inside the container
WORKDIR /app

# Copy your dispatcher script into the container
COPY dispatcher.py .

# Install dependencies
RUN pip install --no-cache-dir aio-pika

# Set default command: you must specify channel as argument when running container
ENTRYPOINT ["python", "dispatcher.py"]


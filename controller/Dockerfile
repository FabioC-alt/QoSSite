FROM python:3.11-slim

WORKDIR /app

RUN pip install requests
RUN pip install nats-py

COPY controller.py .

EXPOSE 8000

CMD ["python","-u", "controller.py"]


FROM python:3.11-slim

WORKDIR /app

RUN pip install requests
RUN pip install aio-pika 

COPY controller.py .

EXPOSE 8000

CMD ["python","-u", "controller.py"]


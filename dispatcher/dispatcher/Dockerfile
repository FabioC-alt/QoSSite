FROM python:3.12-alpine

RUN pip install --no-cache-dir nats-py

COPY dispatcher.py /dispatcher.py

CMD ["python", "/dispatcher.py"]


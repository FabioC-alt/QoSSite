FROM python:3.11-slim

WORKDIR /app
COPY trigger.py .

RUN pip install requests

EXPOSE 8080

CMD ["python", "trigger.py"]


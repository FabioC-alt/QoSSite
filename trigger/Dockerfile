FROM python:3.11-slim

WORKDIR /app
COPY trigger.py .
COPY requirements.txt .

RUN pip install -r requirements.txt 

EXPOSE 8080

CMD ["python", "trigger.py"]


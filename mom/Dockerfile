FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install fastapi uvicorn requests
CMD ["uvicorn", "mom_server:app", "--host", "0.0.0.0", "--port", "8000"]


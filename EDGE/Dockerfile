# Use a slim Python image
FROM python:3.11-slim

# Set working directory inside the container
WORKDIR /app

# Copy dependencies file if you have one
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy your server code
COPY edge.py .

# Expose the port your server uses
EXPOSE 8000

# Set environment variable to bind to all interfaces
ENV HOST=0.0.0.0
ENV PORT=8000

# Run the server
CMD ["python","-u", "edge.py"]


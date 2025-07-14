# Usa un'immagine Python ufficiale come base
FROM python:3.11-slim

# Imposta la working directory
WORKDIR /app

# Copia il file dello script nella working directory
COPY agent.py .

# Installa la libreria requests
RUN pip install --no-cache-dir requests

# Comando di default per eseguire lo script
CMD ["python", "-u", "agent.py"]


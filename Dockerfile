FROM python:3.12-slim-bookworm

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy server file
COPY server.py .

# Run the server
CMD ["python", "server.py"]
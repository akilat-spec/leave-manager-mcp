# Dockerfile

FROM python:3.11-slim

WORKDIR /app

# Install build tools if needed
RUN apt-get update && apt-get install -y build-essential --no-install-recommends && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Use environment variables for DB settings
ENV MYSQL_HOST=localhost
ENV MYSQL_USER=root
ENV MYSQL_PASSWORD=
ENV MYSQL_DB=leave_db

# Default command
CMD ["python", "server.py"]

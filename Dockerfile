# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# system deps (if any native libs required by python-levenshtein)
RUN apt-get update && apt-get install -y build-essential libffi-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

# default to HTTP transport (streamable-http)
ENV MCP_TRANSPORT=streamable-http
ENV PORT=8080

CMD ["python", "main.py"]

FROM python:3.12-slim-bookworm

WORKDIR /app

# Copy only necessary files

COPY requirements.txt server.py ./
# COPY requirements.txt .
# COPY server.py .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Run the server directly
CMD ["python", "server.py"]
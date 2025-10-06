# # Use slim Python image
# FROM python:3.12-slim-bookworm

# # Set working directory
# WORKDIR /app

# # Copy project files
# COPY . .

# # Install venv and create virtual environment
# RUN python -m venv .venv
# RUN . .venv/bin/activate && pip install --upgrade pip setuptools wheel

# # Install dependencies using uv or pip
# RUN . .venv/bin/activate && pip install -r requirements.txt

# # Set environment variables
# ENV PATH="/app/.venv/bin:$PATH"

# # Expose port (if needed)
# EXPOSE 8000

# # Run your MCP server
# CMD ["python", "server.py"]


# Base Python image
FROM python:3.12-slim-bookworm

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Upgrade pip and install dependencies
RUN pip install --upgrade pip setuptools wheel \
    && pip install -r requirements.txt \
    && pip install python-levenshtein fastmcp mysql-connector-python

# Expose port (MCP transport doesn't need HTTP, but if you want it via HTTP use 8000)
EXPOSE 8000

# Run the MCP server
CMD ["python", "server.py"]


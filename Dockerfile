FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc-dev \
    libffi-dev \
    net-tools \
    iputils-ping \
    iproute2 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Optional: Install netifaces for better network interface detection
RUN pip install --no-cache-dir netifaces

# Create necessary directories
RUN mkdir -p /app/uploads /app/logs /app/config /app/backups /app/data

# Copy application code
COPY . .

# Set environment variables
ENV PORT=54780
ENV HOST=0.0.0.0
ENV DEBUG=false
ENV DISCOVERY_TIMEOUT=3

# Expose the application port
EXPOSE 54780

# Run the application
ENTRYPOINT ["python", "main.py", "run"]
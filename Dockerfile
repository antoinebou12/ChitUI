FROM python:3.12-alpine

WORKDIR /app

# Install build dependencies for gevent
RUN apk add --no-cache gcc musl-dev python3-dev libffi-dev

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create necessary directories
RUN mkdir -p /app/uploads /app/logs /app/config

# Copy application code
COPY . .

# Set environment variables
ENV PORT=54780
ENV HOST=0.0.0.0
ENV DEBUG=false

# Expose the application port
EXPOSE 54780

# Run the application
ENTRYPOINT ["python", "main.py"]
# Dockerfile for Mercari Bargain Hunter
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies needed by psycopg2 and Playwright browsers
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        wget curl gnupg2 ca-certificates libpq-dev gcc && \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /etc/apt/keyrings/googlechrome-keyring.gpg && \
    echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/googlechrome-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers for headless browsing
RUN playwright install chromium

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p data logs tests

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Run the application
CMD ["python", "main.py"]

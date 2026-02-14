FROM python:3.13-slim

# Install Node.js (for Jin10 scraper) and other system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends nodejs npm && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium browser
RUN playwright install --with-deps chromium

# Copy application code
COPY . .

# Ensure output directory exists
RUN mkdir -p output

EXPOSE 8000

CMD ["python", "server.py"]

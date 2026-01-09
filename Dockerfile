# Single Unified Dockerfile for WatchVine WhatsApp Bot
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
# gcc, g++ for compiling some python libs
# supervisor for managing multiple processes
# curl for healthchecks
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    build-essential \
    wget \
    curl \
    git \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
# Installing numpy first to avoid conflicts with faiss
RUN pip install --no-cache-dir "numpy<2"
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories for logs and temp files
RUN mkdir -p /app/logs /app/temp_images

# Ensure startup scripts are executable

COPY entrypoint.sh /app/entrypoint.sh

RUN chmod +x /app/entrypoint.sh && \

    sed -i 's/\r$//' /app/entrypoint.sh



# ----------------------------------------------------------------------------

# Supervisor Configuration

# ----------------------------------------------------------------------------

# We write the supervisor configuration directly here to ensure it's always up to date

RUN echo '[supervisord]\n\tnodaemon=true\n\tlogfile=/app/logs/supervisord.log\n\tpidfile=/var/run/supervisord.pid\n\n\t[program:main_flask]\n\tcommand=python main.py\n\tdirectory=/app\n\tautostart=true\n\tautorestart=true\n\tstderr_logfile=/app/logs/main.err.log\n\tstdout_logfile=/app/logs/main.out.log\n\tenvironment=PYTHONUNBUFFERED=1\n\tstartsecs=10\n\n\t[program:text_search_api]\n\tcommand=python text_search_api.py\n\tdirectory=/app\n\tautostart=true\n\tautorestart=true\n\tstderr_logfile=/app/logs/text_search_api.err.log\n\tstdout_logfile=/app/logs/text_search_api.out.log\n\tenvironment=PYTHONUNBUFFERED=1\n\tstartsecs=10\n\n\t[program:image_identifier_api]\n\tcommand=python api.py\n\tdirectory=/app\n\tautostart=true\n\tautorestart=true\n\tstderr_logfile=/app/logs/image_identifier_api.err.log\n\tstdout_logfile=/app/logs/image_identifier_api.out.log\n\tenvironment=PYTHONUNBUFFERED=1\n\tstartsecs=10\n\n\t[program:nightly_scraper]\n\tcommand=python nightly_scraper_scheduler.py\n\tdirectory=/app\n\tautostart=true\n\tautorestart=true\n\tstderr_logfile=/app/logs/nightly_scraper.err.log\n\tstdout_logfile=/app/logs/nightly_scraper.out.log\n\tenvironment=PYTHONUNBUFFERED=1\n\tstartsecs=10' > /etc/supervisor/conf.d/supervisord.conf



# Expose ports

# 5000: Main Flask App (Webhook Receiver)

# 8001: Text Search API

# 8002: Image Identifier API

EXPOSE 5000 8001 8002



# Health check (checks the main flask app)

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \

    CMD curl -f http://localhost:5000/health || exit 1



# Start via entrypoint script to handle initial setup (scraping/indexing) if needed

CMD ["/app/entrypoint.sh"]

FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install dependencies (excluding the local sandbox package)
RUN pip install --no-cache-dir fastapi uvicorn pydantic requests boto3 websockets

# Copy agent code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 agent && \
    chown -R agent:agent /app
USER agent

# Expose port
EXPOSE 8002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8002/health')" || exit 1

# Run with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "1"]

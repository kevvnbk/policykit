FROM python:3.11-slim

WORKDIR /app/sandboxengine

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY sandboxengine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY sandboxengine/ .

# Copy docs directory (needed for api_reference.md at runtime)
# Place it at /app/docs so it matches the Path(__file__).parent.parent.parent structure
COPY docs/ /app/docs/

# Create non-root user
RUN useradd -m -u 1000 sandbox && \
    chown -R sandbox:sandbox /app
USER sandbox

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8001/health || exit 1

# Run with uvicorn
CMD ["uvicorn", "sandboxengine.urls:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]

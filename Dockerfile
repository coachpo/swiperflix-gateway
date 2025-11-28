FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install build tools needed for uvicorn[standard] native extensions, then remove them to keep the image slim
COPY pyproject.toml README.md ./
COPY app ./app
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && pip install --no-cache-dir . \
    && apt-get purge -y build-essential \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Copy remaining project files (entrypoint, config samples, etc.)
COPY . .

# Ensure entrypoint is executable
RUN chmod +x entrypoint.sh

ENV HOST=0.0.0.0 \
    PORT=8000

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]

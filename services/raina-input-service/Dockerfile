# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps (add build-essential if you later need compiled deps)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

# Copy only the project metadata first to leverage layer caching
COPY services/raina-input-service/pyproject.toml /app/pyproject.toml

# Install runtime dependencies declared in pyproject (no packaging needed)
RUN pip install --no-cache-dir --upgrade pip && \
    python -m pip install --no-cache-dir "fastapi==0.115.0" "uvicorn[standard]==0.30.6"

# Copy app source
COPY services/raina-input-service/app /app/app

# Expose & run
ENV APP_PORT=9023
EXPOSE 9023

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9023"]
FROM public.ecr.aws/docker/library/python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates git && \
    rm -rf /var/lib/apt/lists/*

# 1) Install shared libs (astra_common)
COPY libs/pyproject.toml /tmp/libs/pyproject.toml
COPY libs /tmp/libs/libs
RUN pip install --no-cache-dir -e /tmp/libs

# 2) Install astra-models (shared domain models)
COPY libs/astra-models /tmp/astra-models
RUN pip install --no-cache-dir /tmp/astra-models

# 3) Install conductor-core (provides MCPConnection + MCPTransportConfig)
COPY libs/conductor-core /tmp/conductor-core
RUN pip install --no-cache-dir /tmp/conductor-core

# 4) Install service dependencies
COPY services/capability-onboarding-service/pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir .

# 5) Copy service code
COPY services/capability-onboarding-service/app /app/app

EXPOSE 9026
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9026"]

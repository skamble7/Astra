FROM public.ecr.aws/docker/library/python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      git \
    && rm -rf /var/lib/apt/lists/*

# --- Install shared libs (editable) -----------------------------------------
COPY libs/pyproject.toml /tmp/libs/pyproject.toml
COPY libs /tmp/libs/libs
RUN pip install -e /tmp/libs

# --- Install conductor-core --------------------------------------------------
COPY libs/conductor-core /tmp/conductor-core
RUN pip install /tmp/conductor-core

# --- Copy service source BEFORE pip install . --------------------------------
COPY services/planner-service/pyproject.toml /app/pyproject.toml
COPY services/planner-service/README.md /app/README.md
COPY services/planner-service/app /app/app

RUN pip install .

EXPOSE 9025
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9025"]

FROM public.ecr.aws/docker/library/python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# 1) Install shared libs (editable)
COPY libs/pyproject.toml /tmp/libs/pyproject.toml
COPY libs /tmp/libs/libs
RUN pip install --no-cache-dir -e /tmp/libs

# Optional sanity check
RUN python - <<'PY'
import importlib
m = importlib.import_module("libs.astra_common.events")
print("OK shared libs:", m.__file__)
PY

# 2) Install service deps
COPY services/conductor-service/pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir .

# 3) Copy service code
COPY services/conductor-service/app /app/app

# 4) Run (port 9022)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9022"]
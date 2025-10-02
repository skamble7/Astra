FROM public.ecr.aws/docker/library/python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Optional: where workflows may mount a shared workspace volume
    WORKSPACE_FOLDER=/workspace \
    WORKSPACE_MOUNT=/workspace

WORKDIR /app

# --- System deps (certs for HTTPS, keep image slim) -------------------------
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# --- Prepare a writable workspace path (bind-mounted by docker-compose) -----
# Still create it so `cwd: /workspace` is valid even without a mount.
RUN mkdir -p /workspace && chmod 777 /workspace

# --- Install shared libs (editable) -----------------------------------------
# If your monorepo has a local "libs" package used by the service, keep this.
COPY libs/pyproject.toml /tmp/libs/pyproject.toml
COPY libs /tmp/libs/libs
RUN pip install -e /tmp/libs

# Optional sanity check for shared libs
RUN python - <<'PY'
import importlib
m = importlib.import_module("libs.astra_common.events")
print("OK shared libs:", m.__file__)
PY

# --- Copy service source BEFORE pip install . --------------------------------
COPY services/conductor-service/pyproject.toml /app/pyproject.toml
COPY services/conductor-service/README.md /app/README.md
COPY services/conductor-service/app /app/app

# --- Install service only (no bundled MCP servers) --------------------------
# Any MCP client libs should be declared in this service's pyproject.toml.
RUN pip install .

# --- Runtime -----------------------------------------------------------------
EXPOSE 9022
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9022"]
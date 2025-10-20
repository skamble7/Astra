from fastapi import FastAPI
from fastapi import Path as PathParam
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pathlib import Path as FsPath
import json
import os

app = FastAPI(title="Raina Input Service", version="0.1.0")

# ---- CORS (optional via env) ----
allow_origins_env = os.getenv("CORS_ALLOW_ORIGINS", "*")
allow_origins = (
    ["*"] if allow_origins_env.strip() == "*" else [o.strip() for o in allow_origins_env.split(",")]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Load static JSON once ----
DATA_PATH = FsPath(__file__).parent / "data" / "raina_input.json"
with DATA_PATH.open("r", encoding="utf-8") as f:
    RAINA_INPUT = json.load(f)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/raina-input/{pack_id}")
def get_raina_input(
    pack_id: str = PathParam(..., description="Capability pack ID (accepted but not used)")
):
    # Intentionally ignoring pack_id to return the exact provided JSON
    return JSONResponse(content=RAINA_INPUT)
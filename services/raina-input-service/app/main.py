from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path as FsPath
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi import Path as PathParam
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field


# ------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------
MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://host.docker.internal:27017",
)
MONGO_DB = os.getenv("MONGO_DB", "raina_inputs_db")
COLLECTION = os.getenv("MONGO_COLLECTION", "projects")  # optional override

DEFAULT_PROJECT_NAME = os.getenv("DEFAULT_PROJECT_NAME", "Rail Freight Billing Demo")


# ------------------------------------------------------------------------------
# Models (API)
# ------------------------------------------------------------------------------
class ProjectOut(BaseModel):
    project_id: str
    project_name: str
    isActive: bool


class ProjectsListResponse(BaseModel):
    projects: List[ProjectOut]


class ActivateResponse(BaseModel):
    active_project_id: str


class CreateProjectRequest(BaseModel):
    project_name: str = Field(..., min_length=1, max_length=200)
    raina_input: Dict[str, Any] = Field(
        ...,
        description="Must match the existing raina_input.json schema, e.g. {'inputs': {...}}",
    )


class CreateProjectResponse(BaseModel):
    project_id: str
    project_name: str
    isActive: bool


# ------------------------------------------------------------------------------
# App
# ------------------------------------------------------------------------------
app = FastAPI(title="Raina Input Service", version="0.2.0")

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

mongo_client: Optional[AsyncIOMotorClient] = None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _data_path() -> FsPath:
    return FsPath(__file__).parent / "data" / "raina_input.json"


async def get_collection():
    if mongo_client is None:
        raise RuntimeError("Mongo client not initialized")
    return mongo_client[MONGO_DB][COLLECTION]


async def ensure_indexes() -> None:
    """
    Index strategy:
    - Unique project_id
    - Enforce only ONE active project using a partial unique index on isActive=True
    """
    col = await get_collection()
    await col.create_index("project.project_id", unique=True, name="ux_project_id")

    # At most one doc can have project.isActive = true
    await col.create_index(
        "project.isActive",
        unique=True,
        name="ux_single_active_project",
        partialFilterExpression={"project.isActive": True},
    )


async def seed_if_empty() -> None:
    """
    If collection is empty, seed a single active project from the existing JSON file.
    """
    col = await get_collection()
    count = await col.count_documents({})
    if count > 0:
        return

    dp = _data_path()
    with dp.open("r", encoding="utf-8") as f:
        raina_input = json.load(f)

    doc = {
        "project": {
            "project_id": str(uuid.uuid4()),
            "project_name": DEFAULT_PROJECT_NAME,
            "isActive": True,
        },
        "raina_input": raina_input,  # MUST MATCH the existing JSON schema
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    await col.insert_one(doc)


@app.on_event("startup")
async def on_startup() -> None:
    global mongo_client
    mongo_client = AsyncIOMotorClient(MONGO_URI)
    await ensure_indexes()
    await seed_if_empty()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    global mongo_client
    if mongo_client is not None:
        mongo_client.close()
        mongo_client = None


# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/raina-input/{pack_id}")
async def get_raina_input(
    pack_id: str = PathParam(..., description="Capability pack ID (accepted but not used)"),
):
    """
    Backward-compatible endpoint:
    - Ignores pack_id (same as current service)
    - Returns only the ACTIVE project's raina_input
    - Response schema is IDENTICAL to the old JSON file, i.e. {"inputs": {...}}
    """
    col = await get_collection()
    doc = await col.find_one({"project.isActive": True}, {"_id": 0, "raina_input": 1})

    if not doc or "raina_input" not in doc:
        raise HTTPException(status_code=404, detail="No active project configured")

    # Must return the exact JSON structure as before (raina_input contains {"inputs": ...})
    return JSONResponse(content=doc["raina_input"])


@app.post("/projects", response_model=CreateProjectResponse, status_code=201)
async def create_project(payload: CreateProjectRequest):
    """
    Register a new project.

    - project_id is auto generated (uuid)
    - isActive defaults to False
    - payload.raina_input must match the existing schema (e.g. contains top-level 'inputs')
    """
    if not isinstance(payload.raina_input, dict) or "inputs" not in payload.raina_input:
        raise HTTPException(
            status_code=422,
            detail="Invalid raina_input: expected an object with top-level key 'inputs'.",
        )

    col = await get_collection()

    new_id = str(uuid.uuid4())
    now = utc_now()

    doc = {
        "project": {
            "project_id": new_id,
            "project_name": payload.project_name,
            "isActive": False,
        },
        "raina_input": payload.raina_input,
        "created_at": now,
        "updated_at": now,
    }

    try:
        await col.insert_one(doc)
    except Exception as e:
        raise HTTPException(status_code=409, detail=f"Could not create project: {str(e)}") from e

    return CreateProjectResponse(project_id=new_id, project_name=payload.project_name, isActive=False)


@app.put("/projects/{project_id}/activate", response_model=ActivateResponse)
async def activate_project(
    project_id: str = PathParam(..., description="Project UUID to set as active"),
):
    """
    Sets exactly one project active:
    - First sets all projects to inactive
    - Then sets the specified project to active

    A partial unique index on project.isActive=True enforces single-active invariant.
    """
    col = await get_collection()

    # Ensure project exists
    existing = await col.find_one({"project.project_id": project_id}, {"_id": 1})
    if not existing:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    # Step 1: deactivate all
    await col.update_many(
        {"project.isActive": True},
        {"$set": {"project.isActive": False, "updated_at": utc_now()}},
    )

    # Step 2: activate requested project
    try:
        res = await col.update_one(
            {"project.project_id": project_id},
            {"$set": {"project.isActive": True, "updated_at": utc_now()}},
        )
    except Exception as e:
        # If the partial unique index is violated for any reason, surface a clean error
        raise HTTPException(status_code=409, detail=f"Could not activate project: {str(e)}") from e

    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    return ActivateResponse(active_project_id=project_id)


@app.get("/projects", response_model=ProjectsListResponse)
async def list_projects():
    """
    Lists all projects (metadata only).
    """
    col = await get_collection()

    cursor = col.find({}, {"_id": 0, "project": 1}).sort("project.project_name", 1)
    projects: List[ProjectOut] = []
    async for doc in cursor:
        p = doc.get("project") or {}
        projects.append(
            ProjectOut(
                project_id=str(p.get("project_id", "")),
                project_name=str(p.get("project_name", "")),
                isActive=bool(p.get("isActive", False)),
            )
        )

    return ProjectsListResponse(projects=projects)
from __future__ import annotations

import logging

from fastapi import APIRouter

from app.models.mcp_onboarding_models import (
    CapabilityOnboardingDoc,
    RegisterRequest,
    RegisterResponse,
    ResolveRequest,
)
from app.services.mcp_inspector import MCPInspector
from app.services.registrar import Registrar

logger = logging.getLogger("app.routers.mcp_onboarding")

router = APIRouter(prefix="/onboarding", tags=["mcp-onboarding"])


@router.post("/resolve", response_model=CapabilityOnboardingDoc)
async def resolve(req: ResolveRequest) -> CapabilityOnboardingDoc:
    """
    Connect to an MCP server, discover its tools, and run LLM inference on the
    selected tool to populate capability + artifact kind metadata.

    **Two-call flow for multi-tool servers:**
    1. POST without `tool_name` → returns `status="discovered"` with `available_tools`
       for the UI to present a tool picker.
    2. POST with `tool_name` set → returns `status="inferred"` with all metadata populated.

    **Single-tool servers:** One call is sufficient — inference runs automatically.
    """
    inspector = MCPInspector()
    return await inspector.resolve(server=req.server, tool_name=req.tool_name)


@router.post("/register", response_model=RegisterResponse)
async def register(req: RegisterRequest) -> RegisterResponse:
    """
    Register the capability (and any new artifact kinds) in ASTRA.

    Expects `doc.status == 'inferred'`. The `doc.inferred` block may have been
    edited by the user on the Review & Edit screen before submitting.

    - New artifact kinds are created in artifact-service (best-effort; existing kinds are skipped).
    - The capability is created in capability-service.
    - Returns `doc` updated to `status="registered"` with the registered IDs.
    """
    reg = Registrar()
    return await reg.register(req.doc, dry_run=req.dry_run)

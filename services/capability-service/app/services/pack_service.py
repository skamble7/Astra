# services/capability-service/app/services/pack_service.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.dal.capability_dal import CapabilityDAL
from app.dal.pack_dal import PackDAL
from app.events import get_bus
from app.models import (
    CapabilityPack,
    CapabilityPackCreate,
    CapabilityPackUpdate,
    ResolvedPackView,
    ResolvedPlaybook,
    ResolvedPlaybookStep,
    GlobalCapability,
)
from app.services.validation import ensure_pack_capabilities_exist, ensure_playbook_inputs_valid

# resolve registered pack input definitions
try:
    from app.dal.pack_input_dal import PackInputDAL
except Exception:  # pragma: no cover
    PackInputDAL = None  # type: ignore


class PackService:
    def __init__(self) -> None:
        self.packs = PackDAL()
        self.caps = CapabilityDAL()
        self.inputs = PackInputDAL() if PackInputDAL is not None else None

    # ─────────────────────────────────────────────────────────────
    # CRUD
    # ─────────────────────────────────────────────────────────────
    async def create(self, payload: CapabilityPackCreate, *, actor: Optional[str] = None) -> CapabilityPack:
        pack = await self.packs.create(payload, created_by=actor)
        await get_bus().publish(
            service="capability",
            event="pack.created",
            payload={"pack_id": pack.id, "key": pack.key, "version": pack.version, "by": actor},
        )
        return pack

    async def get(self, pack_id: str) -> Optional[CapabilityPack]:
        return await self.packs.get(pack_id)

    async def get_by_key_version(self, key: str, version: str) -> Optional[CapabilityPack]:
        return await self.packs.get_by_key_version(key, version)

    async def update(self, pack_id: str, patch: CapabilityPackUpdate, *, actor: Optional[str] = None) -> Optional[CapabilityPack]:
        pack = await self.packs.update(pack_id, patch, updated_by=actor)
        if pack:
            await get_bus().publish(
                service="capability",
                event="pack.updated",
                payload={"pack_id": pack.id, "key": pack.key, "version": pack.version, "by": actor},
            )
        return pack

    async def delete(self, pack_id: str, *, actor: Optional[str] = None) -> bool:
        ok = await self.packs.delete(pack_id)
        if ok:
            await get_bus().publish(
                service="capability",
                event="pack.deleted",
                payload={"pack_id": pack_id, "by": actor},
            )
        return ok

    # ─────────────────────────────────────────────────────────────
    # Publish (status-only)
    # ─────────────────────────────────────────────────────────────
    async def publish(self, pack_id: str, *, actor: Optional[str] = None) -> Optional[CapabilityPack]:
        published = await self.packs.publish(pack_id)
        if published:
            await get_bus().publish(
                service="capability",
                event="pack.published",
                payload={"pack_id": published.id, "key": published.key, "version": published.version, "by": actor},
            )
        return published

    # ─────────────────────────────────────────────────────────────
    # Search / listing
    # ─────────────────────────────────────────────────────────────
    async def search(self, *, key: Optional[str] = None, version: Optional[str] = None, status: Optional[str] = None,
                     q: Optional[str] = None, limit: int = 50, offset: int = 0):
        return await self.packs.search(key=key, version=version, status=status, q=q, limit=limit, offset=offset)

    async def list_versions(self, key: str) -> List[str]:
        return await self.packs.list_versions(key)

    # ─────────────────────────────────────────────────────────────
    # Resolved view: full capability docs for playbook + agent scopes
    # ─────────────────────────────────────────────────────────────
    async def resolved_view(self, pack_id: str) -> Optional[ResolvedPackView]:
        pack = await self.packs.get(pack_id)
        if not pack:
            return None

        # Validate referenced capabilities and playbook input membership
        all_ids = await self.caps.list_all_ids()
        ensure_pack_capabilities_exist(pack, all_ids)
        ensure_playbook_inputs_valid(pack)

        # Step-bound capability docs (ordered)
        capability_ids: List[str] = pack.capability_ids or []
        capabilities: List[GlobalCapability] = await self.caps.get_many(capability_ids)

        # Agent-scoped capability docs (ordered)
        agent_capability_ids: List[str] = getattr(pack, "agent_capability_ids", None) or []
        agent_capabilities: List[GlobalCapability] = await self.caps.get_many(agent_capability_ids) if agent_capability_ids else []

        # Optional: resolve the registered pack input definitions (plural)
        pack_inputs = []
        if getattr(pack, "pack_input_ids", None) and self.inputs is not None:
            for pid in pack.pack_input_ids:
                try:
                    pi = await self.inputs.get(pid)
                    if pi:
                        pack_inputs.append(pi)
                except Exception:
                    # ignore missing individual inputs to keep view resilient
                    pass

        # Fast lookup for step projection
        by_id: Dict[str, GlobalCapability] = {c.id: c for c in capabilities}

        resolved_playbooks: List[ResolvedPlaybook] = []
        for pb in pack.playbooks:
            steps: List[ResolvedPlaybookStep] = []
            for step in pb.steps:
                cap = by_id.get(step.capability_id)
                if cap:
                    mode = getattr(cap.execution, "mode", "llm")
                    produces = cap.produces_kinds or []
                    tool_calls = getattr(cap.execution, "tool_calls", None) if mode == "mcp" else None
                else:
                    mode = "llm"
                    produces = []
                    tool_calls = None

                steps.append(
                    ResolvedPlaybookStep(
                        id=step.id,
                        name=step.name,
                        capability_id=step.capability_id,
                        execution_mode=mode,        # "mcp" | "llm"
                        produces_kinds=produces,
                        required_kinds=[],          # reserved for learning-service
                        tool_calls=tool_calls,
                    )
                )

            resolved_playbooks.append(
                ResolvedPlaybook(
                    id=pb.id,
                    name=pb.name,
                    description=pb.description,
                    input_id=getattr(pb, "input_id", None),
                    steps=steps,
                )
            )

        return ResolvedPackView(
            pack_id=pack.id,
            key=pack.key,
            version=pack.version,
            title=pack.title,
            description=pack.description,
            pack_input_ids=list(getattr(pack, "pack_input_ids", []) or []),
            pack_inputs=pack_inputs,
            capability_ids=capability_ids,
            agent_capability_ids=agent_capability_ids,
            capabilities=capabilities,
            agent_capabilities=agent_capabilities,
            playbooks=resolved_playbooks,
        )
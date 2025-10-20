# services/capability-service/app/services/validation.py
from __future__ import annotations
from typing import List
from app.models import CapabilityPack

def ensure_pack_capabilities_exist(pack: CapabilityPack, existing_capability_ids: List[str]) -> None:
    """
    Invariant: all referenced capability ids (both step-bound and agent-scoped)
    should exist in the capability registry.
    """
    step_refs = list(pack.capability_ids or [])
    agent_refs = list(getattr(pack, "agent_capability_ids", []) or [])
    missing_steps = [cid for cid in step_refs if cid not in existing_capability_ids]
    missing_agent = [cid for cid in agent_refs if cid not in existing_capability_ids]
    missing = missing_steps + missing_agent
    if missing:
        raise ValueError(f"Unknown capability ids in pack: {missing}")


def ensure_playbook_inputs_valid(pack: CapabilityPack) -> None:
    """
    Invariant: if a playbook specifies input_id, it MUST be a member of pack.pack_input_ids.
    """
    allowed = set(getattr(pack, "pack_input_ids", []) or [])
    if not pack.playbooks:
        return
    for pb in pack.playbooks:
        if getattr(pb, "input_id", None) and pb.input_id not in allowed:
            raise ValueError(
                f"Playbook '{pb.name}' input_id '{pb.input_id}' is not in pack_input_ids {sorted(allowed)}"
            )
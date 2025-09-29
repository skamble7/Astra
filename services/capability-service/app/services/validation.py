# services/capability-service/app/services/validation.py
from __future__ import annotations
from typing import List
from app.models import CapabilityPack

def ensure_pack_capabilities_exist(pack: CapabilityPack, existing_capability_ids: List[str]) -> None:
    """
    Invariant: all referenced capability_ids should exist.
    """
    missing = [cid for cid in (pack.capability_ids or []) if cid not in existing_capability_ids]
    if missing:
        raise ValueError(f"Unknown capability ids in pack: {missing}")
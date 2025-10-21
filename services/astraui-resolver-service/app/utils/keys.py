# services/astraui-resolver-service/app/utils/keys.py
from __future__ import annotations

def build_composite_key(pack_id: str, region_key: str) -> str:
    return f"{pack_id.strip()}::{region_key.strip()}".lower()
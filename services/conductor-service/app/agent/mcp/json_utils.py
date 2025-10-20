# app/agent/mcp/json_utils.py
from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Tuple


def try_parse_json(text_or_obj: Any) -> Any:
    """
    Accepts JSON string or already-parsed object. Returns parsed object or the original value.
    """
    if isinstance(text_or_obj, (dict, list)):
        return text_or_obj
    if isinstance(text_or_obj, str):
        s = text_or_obj.strip()
        if not s:
            return s
        try:
            return json.loads(s)
        except Exception:
            return text_or_obj
    return text_or_obj


def get_by_dotted_path(obj: Any, path: str) -> Any:
    """
    Very small dotted-path extractor: e.g., "data.items[0].artifacts".
    Supports simple [index] on lists and dot keys on dicts.
    """
    cur = obj
    if not path:
        return cur

    parts = path.replace("]", "").split(".")
    for part in parts:
        if not part:
            continue
        if "[" in part:
            name, idx_str = part.split("[", 1)
            if name:
                if not isinstance(cur, dict) or name not in cur:
                    return None
                cur = cur.get(name)
            try:
                i = int(idx_str)
                if not isinstance(cur, list) or i >= len(cur):
                    return None
                cur = cur[i]
            except Exception:
                return None
        else:
            if not isinstance(cur, dict) or part not in cur:
                return None
            cur = cur.get(part)
    return cur


def coerce_list(x: Any) -> List[Any]:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]
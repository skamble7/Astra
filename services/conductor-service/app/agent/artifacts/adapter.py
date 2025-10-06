# services/conductor-service/app/agent/artifacts/adapter.py
from __future__ import annotations

import functools
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

import fastjsonschema

logger = logging.getLogger("app.agent.artifacts.adapter")

# ---------------------------
# Schema registry (pulls from Artifact Service)
# ---------------------------
class KindSchemaRegistry:
    def __init__(self, art_client_getter: Callable[[], Any]):
        """
        art_client_getter: function returning an ArtifactServiceClient (already configured)
        """
        self._get_client = art_client_getter
        self._compiled: Dict[Tuple[str, str], Callable[[Any], None]] = {}
        self._latest_version: Dict[str, str] = {}
        self._raw_schema: Dict[Tuple[str, str], Dict[str, Any]] = {}

    async def get_latest_version(self, kind: str, correlation_id: Optional[str]) -> str:
        if kind in self._latest_version:
            return self._latest_version[kind]
        async with self._get_client() as c:
            spec = await c.get_kind(kind, correlation_id=correlation_id)
            version = (spec or {}).get("latest_schema_version") or "1.0.0"
            self._latest_version[kind] = version
            return version

    async def get_validator(self, kind: str, version: Optional[str], correlation_id: Optional[str]) -> Callable[[Any], None]:
        ver = version or await self.get_latest_version(kind, correlation_id)
        key = (kind, ver)
        if key in self._compiled:
            return self._compiled[key]
        # fetch schema
        async with self._get_client() as c:
            schema = await c.get_kind_schema(kind, ver, correlation_id=correlation_id)
        self._raw_schema[key] = schema
        try:
            validator = fastjsonschema.compile(schema)
        except Exception as e:
            logger.warning("[adapter] failed to compile schema %s@%s: %s; falling back to no-op validator", kind, ver, e)
            def _noop(_data: Any) -> None: ...
            validator = _noop
        self._compiled[key] = validator
        return validator

# ---------------------------
# Declarative adapter primitives
# ---------------------------
AdapterFn = Callable[[Dict[str, Any]], Dict[str, Any]]

def drop_if_none(keys: List[str]) -> AdapterFn:
    def _f(d: Dict[str, Any]) -> Dict[str, Any]:
        for k in keys:
            if k in d and d[k] is None:
                d.pop(k, None)
        return d
    return _f

def drop_empty_strings(keys: List[str]) -> AdapterFn:
    def _f(d: Dict[str, Any]) -> Dict[str, Any]:
        for k in keys:
            if isinstance(d.get(k), str) and not d[k].strip():
                d.pop(k, None)
        return d
    return _f

def rename_key(old: str, new: str) -> AdapterFn:
    def _f(d: Dict[str, Any]) -> Dict[str, Any]:
        if old in d and new not in d:
            d[new] = d.pop(old)
        else:
            d.pop(old, None)
        return d
    return _f

def map_list(key: str, item_fn: AdapterFn) -> AdapterFn:
    def _f(d: Dict[str, Any]) -> Dict[str, Any]:
        val = d.get(key)
        if isinstance(val, list):
            d[key] = [item_fn(x) if isinstance(x, dict) else x for x in val]
        return d
    return _f

def recurse_children_to_items(key_children="children", key_items="items") -> AdapterFn:
    """Recursively rename children→items and sanitize inner nodes."""
    def _fix(node: Dict[str, Any]) -> Dict[str, Any]:
        j = dict(node)
        # local cleans
        if j.get("occurs", ...) is None:
            j.pop("occurs", None)
        if isinstance(j.get("picture"), str) and not j["picture"].strip():
            j.pop("picture", None)

        # children -> items
        if key_children in j:
            ch = j.pop(key_children)
            if isinstance(ch, list):
                j[key_items] = [_fix(c) for c in ch if isinstance(c, dict)]

        # recurse into any pre-existing items
        if isinstance(j.get(key_items), list):
            j[key_items] = [_fix(c) if isinstance(c, dict) else c for c in j[key_items]]
        return j

    def _f(d: Dict[str, Any]) -> Dict[str, Any]:
        if "items" in d and isinstance(d["items"], list):
            d["items"] = [_fix(x) if isinstance(x, dict) else x for x in d["items"]]
        elif key_children in d and isinstance(d[key_children], list):
            d["items"] = [_fix(x) if isinstance(x, dict) else x for x in d[key_children]]
            d.pop(key_children, None)
        return d
    return _f

def deep_strip_nones(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: deep_strip_nones(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [deep_strip_nones(v) for v in obj]
    return obj

# ---------------------------
# Adapter registry
# ---------------------------
class KindAdapterRegistry:
    def __init__(self):
        self._fns: Dict[str, List[AdapterFn]] = {}

    def register(self, kind: str, *fns: AdapterFn):
        if kind not in self._fns:
            self._fns[kind] = []
        self._fns[kind].extend(fns)

    def build(self, kind: str) -> AdapterFn:
        fns = self._fns.get(kind, [])
        def _pipeline(d: Dict[str, Any]) -> Dict[str, Any]:
            out = dict(d)
            for fn in fns:
                try:
                    out = fn(out) or out
                except Exception as e:
                    logger.warning("[adapter] adapter step failed for kind=%s: %s", kind, e)
            return out
        return _pipeline

# Default adapters we know today. Users can add more at runtime.
adapters = KindAdapterRegistry()
# cam.asset.source_index: drop optional nulls inside files
adapters.register(
    "cam.asset.source_index",
    map_list("files", drop_if_none(["language_hint", "encoding", "program_id_guess"]))
)
# cam.cobol.copybook: normalize tree structure
adapters.register(
    "cam.cobol.copybook",
    recurse_children_to_items(),
)

# ---------------------------
# Orchestrator
# ---------------------------
class ArtifactAdapter:
    def __init__(self, schema_registry: KindSchemaRegistry):
        self._schemas = schema_registry

    async def coerce_and_validate(
        self,
        *,
        kind: str,
        data: Dict[str, Any],
        schema_version: Optional[str],
        correlation_id: Optional[str],
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Returns (adapted_data, errors). If errors is empty, data validated.
        """
        # 1) generic cleanup
        working = deep_strip_nones(data)

        # 2) per-kind pipeline
        pipeline = adapters.build(kind)
        working = pipeline(working)

        # 3) validate
        errors: List[str] = []
        validator = await self._schemas.get_validator(kind, schema_version, correlation_id)
        try:
            validator(working)
        except fastjsonschema.exceptions.JsonSchemaException as e:
            # collect path and message
            path = getattr(e, "path", None)
            path_str = "/".join(map(str, path)) if path else ""
            msg = f"{e.message} at '{path_str}'"
            errors.append(msg)
        except Exception as e:
            errors.append(str(e))

        return working, errors
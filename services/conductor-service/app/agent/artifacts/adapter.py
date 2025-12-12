# services/conductor-service/app/agent/artifacts/adapter.py
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple, cast

import fastjsonschema

logger = logging.getLogger("app.agent.artifacts.adapter")

# ---------------------------
# Schema registry (pulls from Artifact Service)
# ---------------------------
class KindSchemaRegistry:
    def __init__(self, art_client_getter):
        """
        art_client_getter: async context manager factory returning an ArtifactServiceClient.
                           Usage: "async with self._get_client() as c: ..."
        """
        self._get_client = art_client_getter
        self._compiled: Dict[Tuple[str, str], Callable[[Any], None]] = {}
        self._latest_version: Dict[str, str] = {}
        self._raw_schema: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._kind_specs: Dict[str, Dict[str, Any]] = {}

    async def get_kind_spec(self, kind: str, correlation_id: Optional[str]) -> Dict[str, Any]:
        if kind in self._kind_specs:
            return self._kind_specs[kind]
        async with self._get_client() as c:
            spec = await c.get_kind(kind, correlation_id=correlation_id)
        spec = spec or {}
        self._kind_specs[kind] = spec
        return spec

    async def get_latest_version(self, kind: str, correlation_id: Optional[str]) -> str:
        if kind in self._latest_version:
            return self._latest_version[kind]
        spec = await self.get_kind_spec(kind, correlation_id)
        version = (spec or {}).get("latest_schema_version") or "1.0.0"
        self._latest_version[kind] = version
        return version

    async def get_schema_entry(self, kind: str, version: Optional[str], correlation_id: Optional[str]) -> Optional[Dict[str, Any]]:
        spec = await self.get_kind_spec(kind, correlation_id)
        target_ver = version or (spec or {}).get("latest_schema_version")
        versions = (spec or {}).get("schema_versions") or []
        if target_ver:
            for v in versions:
                if v.get("version") == target_ver:
                    return v
        return versions[0] if versions else None

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
        g = dict(d)
        for k in keys:
            if k in g and g[k] is None:
                g.pop(k, None)
        return g
    return _f

def drop_empty_strings(keys: List[str]) -> AdapterFn:
    def _f(d: Dict[str, Any]) -> Dict[str, Any]:
        g = dict(d)
        for k in keys:
            if isinstance(g.get(k), str) and not (g[k] or "").strip():
                g.pop(k, None)
        return g
    return _f

def rename_key(old: str, new: str) -> AdapterFn:
    def _f(d: Dict[str, Any]) -> Dict[str, Any]:
        g = dict(d)
        if old in g:
            if new not in g:
                g[new] = g.pop(old)
            else:
                g.pop(old, None)
        return g
    return _f

def map_list(key: str, item_fn: AdapterFn) -> AdapterFn:
    def _f(d: Dict[str, Any]) -> Dict[str, Any]:
        g = dict(d)
        val = g.get(key)
        if isinstance(val, list):
            g[key] = [item_fn(x) if isinstance(x, dict) else x for x in val]
        return g
    return _f

def recurse_children_to_items(key_children="children", key_items="items") -> AdapterFn:
    """Recursively rename children→items and sanitize inner nodes."""
    def _fix(node: Dict[str, Any]) -> Dict[str, Any]:
        j = dict(node)
        # local cleans
        if j.get("occurs", ...) is None:
            j.pop("occurs", None)
        if isinstance(j.get("picture"), str) and not (j["picture"] or "").strip():
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
        g = dict(d)
        if "items" in g and isinstance(g["items"], list):
            g["items"] = [_fix(x) if isinstance(x, dict) else x for x in g["items"]]
        elif key_children in g and isinstance(g[key_children], list):
            g["items"] = [_fix(x) if isinstance(x, dict) else x for x in g[key_children]]
            g.pop(key_children, None)
        return g
    return _f

def deep_strip_nones(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: deep_strip_nones(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [deep_strip_nones(v) for v in obj]
    return obj


# ---------------------------
# Dynamic adapter registry (driven by registry "adapter_steps")
# ---------------------------
class KindAdapterRegistry:
    """
    Builds pipelines dynamically from kind spec's latest schema version:

    schema_versions[].adapter_steps ::= [
      {"op":"drop_if_none","keys":["language_hint","encoding"]},
      {"op":"drop_empty_strings","keys":["picture"]},
      {"op":"rename_key","old":"children","new":"items"},
      {"op":"map_list","key":"files","steps":[{"op":"drop_if_none","keys":["encoding"]}]},
      {"op":"recurse_children_to_items"}
    ]
    """
    def __init__(self, schema_registry: KindSchemaRegistry):
        self._schemas = schema_registry
        self._pipelines: Dict[Tuple[str, str], List[AdapterFn]] = {}

    def _compile_step(self, spec: Dict[str, Any]) -> AdapterFn:
        op = (spec or {}).get("op")
        if op == "drop_if_none":
            return drop_if_none(list(spec.get("keys") or []))
        if op == "drop_empty_strings":
            return drop_empty_strings(list(spec.get("keys") or []))
        if op == "rename_key":
            return rename_key(str(spec.get("old")), str(spec.get("new")))
        if op == "recurse_children_to_items":
            return recurse_children_to_items(
                key_children=str(spec.get("key_children") or "children"),
                key_items=str(spec.get("key_items") or "items"),
            )
        if op == "map_list":
            key = str(spec.get("key"))
            inner_steps = list(spec.get("steps") or [])
            inner_fns = [self._compile_step(s) for s in inner_steps if isinstance(s, dict)]
            def _chain(x: Dict[str, Any]) -> Dict[str, Any]:
                out = dict(x)
                for fn in inner_fns:
                    try:
                        out = fn(out) or out
                    except Exception as e:
                        logger.warning("[adapter] map_list inner step failed: %s", e)
                return out
            return map_list(key, _chain)
        # Unknown op → no-op
        logger.warning("[adapter] unknown adapter op=%s; ignoring", op)
        return lambda d: d

    async def build(self, kind: str, version: Optional[str], correlation_id: Optional[str]) -> List[AdapterFn]:
        ver = version or await self._schemas.get_latest_version(kind, correlation_id)
        key = (kind, ver)
        if key in self._pipelines:
            return self._pipelines[key]

        entry = await self._schemas.get_schema_entry(kind, ver, correlation_id)
        steps = (entry or {}).get("adapter_steps") or []
        fns: List[AdapterFn] = []
        for s in steps:
            try:
                if isinstance(s, dict):
                    fns.append(self._compile_step(s))
            except Exception as e:
                logger.warning("[adapter] failed to compile step for %s@%s: %s", kind, ver, e)
        self._pipelines[key] = fns
        return fns


# ---------------------------
# Orchestrator
# ---------------------------
class ArtifactAdapter:
    def __init__(self, schema_registry: KindSchemaRegistry):
        self._schemas = schema_registry
        self._dyn = KindAdapterRegistry(schema_registry)

    async def adapt_only(
        self,
        *,
        kind: str,
        data: Dict[str, Any],
        schema_version: Optional[str],
        correlation_id: Optional[str],
    ) -> Dict[str, Any]:
        """
        Run per-kind pipeline ONLY (no validation). Returns adapted data.
        """
        working = deep_strip_nones(data or {})
        fns = await self._dyn.build(kind, schema_version, correlation_id)
        for fn in fns:
            try:
                working = fn(working) or working
            except Exception as e:
                logger.warning("[adapter] adapter step failed for kind=%s: %s", kind, e)
        return working

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
        # 1) run dynamic pipeline
        working = await self.adapt_only(
            kind=kind,
            data=data or {},
            schema_version=schema_version,
            correlation_id=correlation_id,
        )

        # 2) validate
        errors: List[str] = []
        validator = await self._schemas.get_validator(kind, schema_version, correlation_id)
        try:
            validator(working)
        except fastjsonschema.exceptions.JsonSchemaException as e:
            path = getattr(e, "path", None)
            path_str = "/".join(map(str, path)) if path else ""
            msg = f"{e.message} at '{path_str}'"
            errors.append(msg)
        except Exception as e:
            errors.append(str(e))

        return working, errors
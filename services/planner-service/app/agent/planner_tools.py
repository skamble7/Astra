# services/planner-service/app/agent/planner_tools.py
"""
LangChain tools for the ASTRA planner agent.

Tools close over a ManifestCache instance (for capability lookups) and a
mutable state_ref dict that update_plan() writes into — the calling node reads
the final draft_plan from state_ref after the agent loop completes.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List
from uuid import uuid4

from langchain_core.tools import tool

from app.cache.manifest_cache import ManifestCache

logger = logging.getLogger("app.agent.planner_tools")


def make_planner_tools(cache: ManifestCache, state_ref: Dict[str, Any]) -> list:
    """
    Return the list of LangChain tools for the planner agent.

    state_ref must contain:
      "draft_plan"    — initialised with the current session plan (may be empty list)
    """

    @tool
    async def search_capabilities(query: str) -> str:
        """Search ASTRA registered capabilities by keyword, description, or domain.
        Use this to discover which capabilities are relevant to the user's goal.
        Returns a markdown list of matching capabilities with their IDs and descriptions."""
        try:
            all_caps = await cache.get_all_capabilities()
        except Exception as e:
            logger.warning("[search_capabilities] cache fetch failed: %s", e)
            return "Could not load capabilities. Please try again."

        q = query.lower()
        matches = [
            c for c in all_caps
            if q in (c.get("title") or c.get("name") or "").lower()
            or q in (c.get("description") or "").lower()
            or any(q in tag.lower() for tag in (c.get("tags") or []))
        ]

        if not matches:
            return f"No capabilities found matching **{query}**. Try `list_all_capabilities` to see everything available."

        lines = [f"## Capabilities matching \"{query}\"\n"]
        for cap in matches[:20]:
            cap_id = cap.get("id", "")
            title = cap.get("title") or cap.get("name") or cap_id
            desc = cap.get("description") or ""
            modes = []
            exec_cfg = cap.get("execution") or {}
            if isinstance(exec_cfg, dict):
                mode = exec_cfg.get("mode")
                if mode:
                    modes.append(mode)
            produces = cap.get("produces_kinds") or []
            produces_str = ", ".join(f"`{k}`" for k in produces) if produces else "—"
            lines.append(f"- **{title}** (`{cap_id}`): {desc}")
            if produces:
                lines.append(f"  - Produces: {produces_str}")

        if len(matches) > 20:
            lines.append(f"\n_…and {len(matches) - 20} more. Refine your query to narrow results._")

        return "\n".join(lines)

    @tool
    async def get_capability_details(cap_id: str) -> str:
        """Get full details about a specific ASTRA capability by its ID.
        Returns what the capability does, the inputs it requires, and the artifact kinds it produces.
        Use this when the user asks about a specific capability."""
        try:
            cap = await cache.get_capability(cap_id)
        except Exception as e:
            logger.warning("[get_capability_details] cache fetch failed cap=%s: %s", cap_id, e)
            return f"Could not fetch capability `{cap_id}`. Please try again."

        if not cap:
            # Try to find by name (case-insensitive)
            try:
                all_caps = await cache.get_all_capabilities()
                cap = next(
                    (c for c in all_caps if (c.get("title") or c.get("name") or "").lower() == cap_id.lower()),
                    None,
                )
            except Exception:
                pass

        if not cap:
            return f"Capability `{cap_id}` not found. Use `search_capabilities` to find the correct ID."

        title = cap.get("title") or cap.get("name") or cap_id
        desc = cap.get("description") or "No description available."
        produces = cap.get("produces_kinds") or []
        tags = cap.get("tags") or []

        exec_cfg = cap.get("execution") or {}
        mode = exec_cfg.get("mode", "unknown") if isinstance(exec_cfg, dict) else "unknown"

        lines = [
            f"## {title} (`{cap_id}`)\n",
            f"{desc}\n",
            f"**Execution mode:** `{mode}`",
        ]

        if tags:
            lines.append(f"**Tags:** {', '.join(tags)}")

        if produces:
            lines.append(f"\n### Artifact outputs (produces_kinds)")
            for kind in produces:
                lines.append(f"- `{kind}`")

        # Input contract
        io = exec_cfg.get("io") or {} if isinstance(exec_cfg, dict) else {}
        if isinstance(io, dict):
            input_contract = io.get("input_contract") or {}
            if input_contract:
                lines.append(f"\n### Required inputs")
                if isinstance(input_contract, dict):
                    props = input_contract.get("properties") or input_contract
                    for field_name, field_def in props.items():
                        if isinstance(field_def, dict):
                            field_type = field_def.get("type", "string")
                            field_desc = field_def.get("description") or field_def.get("title") or ""
                            required_mark = ""
                            required_list = input_contract.get("required") or []
                            if field_name in required_list:
                                required_mark = " *(required)*"
                            lines.append(f"- **{field_name}** ({field_type}){required_mark}: {field_desc}")

            output_contract = io.get("output_contract") or {}
            if output_contract and isinstance(output_contract, dict):
                lines.append(f"\n### Output contract")
                out_kind = output_contract.get("kind") or output_contract.get("type") or ""
                if out_kind:
                    lines.append(f"- Kind: `{out_kind}`")

        # MCP tool calls
        tool_calls = exec_cfg.get("tool_calls") or [] if isinstance(exec_cfg, dict) else []
        if tool_calls:
            lines.append(f"\n### MCP tool calls")
            for tc in tool_calls:
                if isinstance(tc, dict):
                    tc_name = tc.get("tool", "")
                    tc_kinds = tc.get("output_kinds") or []
                    kinds_str = ", ".join(f"`{k}`" for k in tc_kinds) if tc_kinds else "—"
                    lines.append(f"- `{tc_name}` → {kinds_str}")

        return "\n".join(lines)

    @tool
    async def list_all_capabilities() -> str:
        """List all registered ASTRA capabilities, grouped by tag.
        Use this when the user wants to browse everything available."""
        try:
            all_caps = await cache.get_all_capabilities()
        except Exception as e:
            logger.warning("[list_all_capabilities] cache fetch failed: %s", e)
            return "Could not load capabilities. Please try again."

        if not all_caps:
            return "No capabilities are currently registered in ASTRA."

        # Group by first tag
        groups: Dict[str, list] = {}
        for cap in all_caps:
            tags = cap.get("tags") or []
            group = tags[0] if tags else "General"
            groups.setdefault(group, []).append(cap)

        lines = ["## All Registered ASTRA Capabilities\n"]
        for group, caps in sorted(groups.items()):
            lines.append(f"\n### {group}")
            for cap in caps:
                cap_id = cap.get("id", "")
                title = cap.get("title") or cap.get("name") or cap_id
                desc = (cap.get("description") or "")[:120]
                if len(cap.get("description") or "") > 120:
                    desc += "…"
                lines.append(f"- **{title}** (`{cap_id}`): {desc}")

        lines.append(f"\n_Total: {len(all_caps)} capabilities_")
        return "\n".join(lines)

    @tool
    async def update_plan(steps: List[Dict[str, Any]]) -> str:
        """Create or replace the current execution plan with the provided ordered list of steps.
        Call this whenever the user wants to build a new plan or modify the existing one.

        Each step must include:
          - capability_id: str  — the registered capability ID (e.g. "cap.cobol.parse")
          - title: str          — human-readable step name
          - description: str    — what this step does
          - inputs: dict        — pre-filled input values (empty dict if unknown)
          - order: int          — execution order (1-indexed)
        """
        if not steps:
            state_ref["draft_plan"] = []
            return "Plan cleared (0 steps)."

        normalized = []
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            normalized.append({
                "step_id": f"step-{uuid4().hex[:8]}",
                "capability_id": step.get("capability_id", ""),
                "title": step.get("title", f"Step {i + 1}"),
                "description": step.get("description", ""),
                "inputs": step.get("inputs") or {},
                "run_inputs": step.get("inputs") or {},
                "order": step.get("order", i + 1),
                "enabled": True,
            })

        state_ref["draft_plan"] = normalized
        logger.info("[update_plan] plan updated with %d steps", len(normalized))
        return f"Plan updated with {len(normalized)} step(s)."

    return [search_capabilities, get_capability_details, list_all_capabilities, update_plan]

# app/agent/nodes/capability_executor.py
from __future__ import annotations
from typing import Any, Dict, List
from uuid import UUID
from datetime import datetime, timezone
import logging

from typing_extensions import Literal
from langgraph.types import Command
from app.db.run_repository import RunRepository

logger = logging.getLogger("app.agent.nodes.capability_executor")

def capability_executor_node(*, runs_repo: RunRepository):
    async def _node(state: Dict[str, Any]) -> Command[Literal["mcp_input_resolver", "llm_execution", "capability_executor"]] | Dict[str, Any]:
        logs: List[str] = state.get("logs", [])
        request: Dict[str, Any] = state["request"]
        run_doc: Dict[str, Any] = state["run"]
        pack: Dict[str, Any] = state.get("pack") or {}

        run_uuid = UUID(run_doc["run_id"])
        playbook_id = request["playbook_id"]
        step_idx = int(state.get("step_idx", 0))

        if not state.get("inputs_valid", False):
            if step_idx == 0:
                pb = next((p for p in (pack.get("playbooks") or []) if p.get("id") == playbook_id), None)
                if pb:
                    for s in pb.get("steps", []) or []:
                        await runs_repo.step_skipped(run_uuid, s["id"], reason="inputs_invalid")
            return {"logs": logs, "completed_at": datetime.now(timezone.utc).isoformat()}

        pb = next((p for p in (pack.get("playbooks") or []) if p.get("id") == playbook_id), None)
        if not pb:
            logs.append(f"Playbook '{playbook_id}' not found during execution.")
            return {"logs": logs}

        steps = pb.get("steps", []) or []
        if step_idx >= len(steps):
            return {"logs": logs, "completed_at": datetime.now(timezone.utc).isoformat()}

        step = steps[step_idx]
        step_id = step["id"]
        cap_id = step["capability_id"]
        caps = {c.get("id"): c for c in (pack.get("capabilities") or [])}
        cap = caps.get(cap_id)
        if not cap:
            await runs_repo.step_failed(run_uuid, step_id, error=f"Capability '{cap_id}' not found in pack.")
            return Command(goto="capability_executor", update={"step_idx": step_idx + 1})

        mode = (cap.get("execution") or {}).get("mode")
        await runs_repo.step_started(run_uuid, step_id)

        update = {
            "step_idx": step_idx,  # execution node will increment
            "current_step_id": step_id,
            "dispatch": {
                "capability": cap,
                "step": step,
            },
        }

        if mode == "mcp":
            # NEW: route to input resolver first
            return Command(goto="mcp_input_resolver", update=update)
        elif mode == "llm":
            return Command(goto="llm_execution", update=update)
        else:
            await runs_repo.step_failed(run_uuid, step_id, error=f"Unsupported mode '{mode}'")
            return Command(goto="capability_executor", update={"step_idx": step_idx + 1})

    return _node
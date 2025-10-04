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
    async def _node(
        state: Dict[str, Any]
    ) -> Command[Literal["mcp_input_resolver", "llm_execution", "capability_executor"]] | Dict[str, Any]:
        logs: List[str] = state.get("logs", [])
        request: Dict[str, Any] = state["request"]
        run_doc: Dict[str, Any] = state["run"]
        pack: Dict[str, Any] = state.get("pack") or {}

        run_uuid = UUID(run_doc["run_id"])
        playbook_id = request["playbook_id"]
        step_idx = int(state.get("step_idx", 0))

        # Sole writer policy: only this node writes current_step_id/step_idx advancement.
        current_step_id = state.get("current_step_id")
        last_mcp = state.get("last_mcp_summary") or {}
        last_mcp_error = state.get("last_mcp_error")

        # Terminate on executor-reported failure
        if last_mcp_error:
            logs.append(f"MCP failure: {last_mcp_error}")
            return {
                "logs": logs,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                # Clear stale execution context on terminal exit
                "current_step_id": None,
                "dispatch": {},
                "last_mcp_summary": {},
                # Keep last_mcp_error as-is in state for auditing/visibility
            }

        # Consume completion breadcrumb inline (no extra tick that re-writes the same key)
        if current_step_id and last_mcp.get("completed_step_id") == current_step_id:
            step_idx += 1
            current_step_id = None
            last_mcp = {}  # consumed

        # Guard invalid inputs (terminal)
        if not state.get("inputs_valid", False):
            if step_idx == 0:
                pb = next((p for p in (pack.get("playbooks") or []) if p.get("id") == playbook_id), None)
                if pb:
                    for s in pb.get("steps", []) or []:
                        await runs_repo.step_skipped(run_uuid, s["id"], reason="inputs_invalid")
            return {
                "logs": logs,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "current_step_id": None,
                "dispatch": {},
                "last_mcp_summary": {},
                "last_mcp_error": None,
            }

        # Playbook/steps
        pb = next((p for p in (pack.get("playbooks") or []) if p.get("id") == playbook_id), None)
        if not pb:
            logs.append(f"Playbook '{playbook_id}' not found during execution.")
            return {
                "logs": logs,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "current_step_id": None,
                "dispatch": {},
                "last_mcp_summary": {},
                "last_mcp_error": None,
            }

        steps = pb.get("steps", []) or []
        if step_idx >= len(steps):
            # Finished all steps (terminal)
            return {
                "logs": logs,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "current_step_id": None,
                "dispatch": {},
                "last_mcp_summary": {},
                "last_mcp_error": None,
            }

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

        # Only this node writes current_step_id
        base_update = {
            "step_idx": step_idx,
            "current_step_id": step_id,
            "dispatch": {
                "capability": cap,
                "step": step,
            },
            # clear any consumed flags
            "last_mcp_summary": {},
            "last_mcp_error": None,
        }

        if mode == "mcp":
            return Command(goto="mcp_input_resolver", update=base_update)
        elif mode == "llm":
            return Command(goto="llm_execution", update=base_update)
        else:
            await runs_repo.step_failed(run_uuid, step_id, error=f"Unsupported mode '{mode}'")
            return Command(goto="capability_executor", update={"step_idx": step_idx + 1})

    return _node
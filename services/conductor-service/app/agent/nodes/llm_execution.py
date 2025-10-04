# app/agent/nodes/llm_execution.py
from __future__ import annotations
from typing import Any, Dict
from datetime import datetime, timezone
from uuid import UUID
import json, logging

from typing_extensions import Literal
from langgraph.types import Command
from app.db.run_repository import RunRepository
from app.models.run_models import StepAudit, ToolCallAudit

logger = logging.getLogger("app.agent.nodes.llm_execution")

def llm_execution_node(*, runs_repo: RunRepository):
    async def _node(
        state: Dict[str, Any]
    ) -> Command[Literal["capability_executor"]] | Dict[str, Any]:
        run = state["run"]
        run_uuid = UUID(run["run_id"])
        step_idx = int(state.get("step_idx", 0))
        step = state["dispatch"]["step"]
        step_id = step["id"]
        cap = state["dispatch"]["capability"]
        cap_id = cap["id"]
        params = step.get("params") or {}
        started = datetime.now(timezone.utc)

        # Log the entire dispatch object (capability + step) for debugging
        try:
            logger.info(
                "[LLM] Received dispatch from capability_executor: %s",
                json.dumps(state.get("dispatch", {}), ensure_ascii=False, default=str)[:2000],
            )
        except Exception:
            logger.exception("[LLM] Failed to serialize dispatch for logging")

        logger.info("[LLM] Placeholder invoked for capability=%s params=%s", cap_id, params)

        await runs_repo.append_step_audit(
            run_uuid,
            StepAudit(
                step_id=step_id,
                capability_id=cap_id,
                mode="llm",
                inputs_preview={"params": params},
                calls=[
                    ToolCallAudit(
                        system_prompt=None,
                        user_prompt=f"[placeholder invocation for {cap_id}]",
                        llm_config=cap.get("execution", {}).get("llm_config"),
                        raw_output_sample=json.dumps(
                            {"invoked": True, "mode": "llm"}
                        )[:200],
                        status="ok",
                    )
                ],
            ),
        )
        await runs_repo.step_completed(
            run_uuid,
            step_id,
            metrics={
                "mode": "llm",
                "duration_ms": int(
                    (datetime.now(timezone.utc) - started).total_seconds() * 1000
                ),
            },
        )

        cmd = Command(
            goto="capability_executor",
            update={"step_idx": step_idx + 1, "current_step_id": None},
        )

        # Log the Command being returned
        logger.info("[LLM] Returning Command: %s", cmd)

        return cmd

    return _node
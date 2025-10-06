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

    def _log_terminal_state(state: Dict[str, Any], update: Dict[str, Any], reason: str) -> None:
        """
        Merge current state with the terminal update and log a compact summary.
        Never mutates the passed-in state.
        """
        try:
            merged = dict(state)
            merged.update(update or {})
            staged = merged.get("staged_artifacts") or []
            logger.info(
                "[capability_executor] TERMINAL reason=%s staged_artifacts_count=%d",
                reason,
                len(staged),
            )
        except Exception:
            logger.exception("[capability_executor] Failed to log terminal summary (%s).", reason)

    async def _node(
        state: Dict[str, Any]
    ) -> Command[Literal["mcp_input_resolver", "llm_execution", "diagram_enrichment", "capability_executor", "persist_run"]] | Dict[str, Any]:
        logs: List[str] = state.get("logs", [])
        request: Dict[str, Any] = state["request"]
        run_doc: Dict[str, Any] = state["run"]
        pack: Dict[str, Any] = state.get("pack") or {}

        run_uuid = UUID(run_doc["run_id"])
        playbook_id = request["playbook_id"]
        step_idx = int(state.get("step_idx", 0))

        # Two-phase step: discover -> enrich
        phase = state.get("phase") or "discover"

        # Sole writer policy: only this node writes current_step_id/step_idx/phase advancement.
        current_step_id = state.get("current_step_id")
        last_mcp = state.get("last_mcp_summary") or {}
        last_mcp_error = state.get("last_mcp_error")
        last_enrich = state.get("last_enrichment_summary") or {}
        last_enrich_error = state.get("last_enrichment_error")

        # Terminate on executor-reported discovery failure -> persist_run
        if last_mcp_error:
            logs.append(f"MCP failure: {last_mcp_error}")
            term_update = {
                "logs": logs,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "current_step_id": None,
                "dispatch": {},
                "last_mcp_summary": {},
                # keep last_mcp_error for visibility (persist_run can incorporate it)
            }
            _log_terminal_state(state, term_update, reason="mcp_error")
            return Command(goto="persist_run", update=term_update)

        # Enrichment error policy (soft-continue)
        if last_enrich_error:
            logs.append(f"Enrichment warning (soft-continue): {last_enrich_error}")

        # Consume completion breadcrumbs depending on phase
        if phase == "discover" and current_step_id and last_mcp.get("completed_step_id") == current_step_id:
            # Discovery done for this step -> switch to enrichment phase
            logger.info(
                "[capability_executor] phase_transition discover->enrich step_id=%s",
                current_step_id,
            )
            phase = "enrich"
            state_breadcrumb_clear = {"last_mcp_summary": {}}
            base_update = {
                "step_idx": step_idx,
                "current_step_id": current_step_id,
                "phase": phase,
                "dispatch": state.get("dispatch") or {},
                **state_breadcrumb_clear,
                "last_mcp_error": None,
            }
            return Command(goto="diagram_enrichment", update=base_update)

        if phase == "enrich" and current_step_id and last_enrich.get("completed_step_id") == current_step_id:
            # Enrichment done for this step -> advance to next step (reset to discover)
            step_idx += 1
            current_step_id = None
            phase = "discover"
            last_enrich = {}  # consumed
            logger.info("[capability_executor] enrichment_complete advancing_to_step_idx=%d", step_idx)

        # Guard invalid inputs -> persist_run
        if not state.get("inputs_valid", False):
            if step_idx == 0:
                pb = next((p for p in (pack.get("playbooks") or []) if p.get("id") == playbook_id), None)
                if pb:
                    for s in pb.get("steps", []) or []:
                        await runs_repo.step_skipped(run_uuid, s["id"], reason="inputs_invalid")
            term_update = {
                "logs": logs,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "current_step_id": None,
                "dispatch": {},
                "last_mcp_summary": {},
                "last_mcp_error": None,
                "phase": "discover",
                "last_enrichment_summary": {},
                "last_enrichment_error": None,
            }
            _log_terminal_state(state, term_update, reason="inputs_invalid")
            return Command(goto="persist_run", update=term_update)

        # Playbook/steps
        pb = next((p for p in (pack.get("playbooks") or []) if p.get("id") == playbook_id), None)
        if not pb:
            logs.append(f"Playbook '{playbook_id}' not found during execution.")
            term_update = {
                "logs": logs,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "current_step_id": None,
                "dispatch": {},
                "last_mcp_summary": {},
                "last_mcp_error": None,
                "phase": "discover",
                "last_enrichment_summary": {},
                "last_enrichment_error": None,
            }
            _log_terminal_state(state, term_update, reason="playbook_not_found")
            return Command(goto="persist_run", update=term_update)

        steps = pb.get("steps", []) or []
        if step_idx >= len(steps):
            # Finished all steps -> persist_run
            term_update = {
                "logs": logs,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "current_step_id": None,
                "dispatch": {},
                "last_mcp_summary": {},
                "last_mcp_error": None,
                "phase": "discover",
                "last_enrichment_summary": {},
                "last_enrichment_error": None,
            }
            _log_terminal_state(state, term_update, reason="all_steps_completed")
            return Command(goto="persist_run", update=term_update)

        # If we arrive here with phase="enrich" but no enrichment breadcrumb yet, dispatch enrichment
        if phase == "enrich" and current_step_id:
            logger.info("[capability_executor] dispatch_enrichment step_id=%s", current_step_id)
            return Command(
                goto="diagram_enrichment",
                update={
                    "step_idx": step_idx,
                    "current_step_id": current_step_id,
                    "phase": "enrich",
                    "dispatch": state.get("dispatch") or {},
                    "last_enrichment_summary": {},
                    "last_enrichment_error": None,
                },
            )

        # Otherwise we're in discovery phase; (re)start the step if needed
        step = steps[step_idx]
        step_id = step["id"]
        cap_id = step["capability_id"]
        caps = {c.get("id"): c for c in (pack.get("capabilities") or [])}
        cap = caps.get(cap_id)
        if not cap:
            await runs_repo.step_failed(run_uuid, step_id, error=f"Capability '{cap_id}' not found in pack.")
            logger.info(
                "[capability_executor] step_skipped_missing_cap step_idx=%d step_id=%s cap_id=%s",
                step_idx,
                step_id,
                cap_id,
            )
            return Command(
                goto="capability_executor",
                update={
                    "step_idx": step_idx + 1,
                    "phase": "discover",
                    "current_step_id": None,
                    "last_enrichment_summary": {},
                    "last_enrichment_error": None,
                },
            )

        mode = (cap.get("execution") or {}).get("mode")
        logger.info(
            "[capability_executor] dispatch step_idx=%d step_id=%s cap_id=%s mode=%s",
            step_idx,
            step_id,
            cap_id,
            mode,
        )

        # Start step only when (re)entering discovery for this step
        await runs_repo.step_started(run_uuid, step_id)

        # Only this node writes current_step_id and phase
        base_update = {
            "step_idx": step_idx,
            "current_step_id": step_id,
            "phase": "discover",
            "dispatch": {
                "capability": cap,
                "step": step,
            },
            # clear any consumed flags
            "last_mcp_summary": {},
            "last_mcp_error": None,
            "last_enrichment_summary": {},
            "last_enrichment_error": None,
        }

        if mode == "mcp":
            return Command(goto="mcp_input_resolver", update=base_update)
        elif mode == "llm":
            return Command(goto="llm_execution", update=base_update)
        else:
            await runs_repo.step_failed(run_uuid, step_id, error=f"Unsupported mode '{mode}'")
            logger.info(
                "[capability_executor] step_failed_unsupported_mode step_idx=%d step_id=%s mode=%s",
                step_idx,
                step_id,
                mode,
            )
            return Command(
                goto="capability_executor",
                update={
                    "step_idx": step_idx + 1,
                    "phase": "discover",
                    "current_step_id": None,
                },
            )

    return _node
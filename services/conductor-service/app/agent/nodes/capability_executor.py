from __future__ import annotations
from typing import Any, Dict, List
from uuid import UUID
from datetime import datetime, timezone
import logging

from typing_extensions import Literal
from langgraph.types import Command
from app.db.run_repository import RunRepository
from app.events.rabbit import get_bus, EventPublisher  # NEW

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
        workspace_id = run_doc["workspace_id"]
        playbook_id = request["playbook_id"]
        step_idx = int(state.get("step_idx", 0))
        strategy = (run_doc.get("strategy") or "").lower() or None
        correlation_id = state.get("correlation_id")

        publisher = EventPublisher(bus=get_bus())

        # Two-phase step: discover -> enrich
        phase = state.get("phase") or "discover"

        # Sole writer policy: only this node writes current_step_id/step_idx/phase advancement.
        current_step_id = state.get("current_step_id")
        last_mcp = state.get("last_mcp_summary") or {}
        last_mcp_error = state.get("last_mcp_error")
        last_enrich = state.get("last_enrichment_summary") or {}
        last_enrich_error = state.get("last_enrichment_error")

        # Terminate on executor-reported discovery failure -> persist_run
        if last_mcp_error and current_step_id:
            logs.append(f"MCP failure: {last_mcp_error}")
            # Emit step.failed (discover)
            await publisher.publish_once(
                runs_repo=runs_repo,
                run_id=run_uuid,
                event="step.failed",
                payload={
                    "run_id": str(run_uuid),
                    "workspace_id": workspace_id,
                    "playbook_id": playbook_id,
                    "step": {"id": current_step_id},
                    "phase": "discover",
                    "ended_at": datetime.now(timezone.utc).isoformat(),
                    "error": str(last_mcp_error),
                    "status": "failed",
                },
                workspace_id=workspace_id,
                playbook_id=playbook_id,
                step_id=current_step_id,
                phase="discover",
                strategy=strategy,
                emitter="capability_executor",
                correlation_id=correlation_id,
            )
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
            # Discovery done for this step -> emit discovery_completed, then switch to enrichment phase
            await publisher.publish_once(
                runs_repo=runs_repo,
                run_id=run_uuid,
                event="step.discovery_completed",
                payload={
                    "run_id": str(run_uuid),
                    "workspace_id": workspace_id,
                    "playbook_id": playbook_id,
                    "step": {"id": current_step_id},
                    "phase": "discover",
                    "ended_at": datetime.now(timezone.utc).isoformat(),
                    "status": "discovery_completed",
                },
                workspace_id=workspace_id,
                playbook_id=playbook_id,
                step_id=current_step_id,
                phase="discover",
                strategy=strategy,
                emitter="capability_executor",
                correlation_id=correlation_id,
            )

            logger.info("[capability_executor] phase_transition discover->enrich step_id=%s", current_step_id)
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
            # Now enrichment starts
            await publisher.publish_once(
                runs_repo=runs_repo,
                run_id=run_uuid,
                event="step.enrichment_started",
                payload={
                    "run_id": str(run_uuid),
                    "workspace_id": workspace_id,
                    "playbook_id": playbook_id,
                    "step": {"id": current_step_id},
                    "phase": "enrich",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "status": "enrichment_started",
                },
                workspace_id=workspace_id,
                playbook_id=playbook_id,
                step_id=current_step_id,
                phase="enrich",
                strategy=strategy,
                emitter="capability_executor",
                correlation_id=correlation_id,
            )
            return Command(goto="diagram_enrichment", update=base_update)

        if phase == "enrich" and current_step_id and last_enrich.get("completed_step_id") == current_step_id:
            # Enrichment done for this step -> emit enrichment_completed and step.completed, then advance
            await publisher.publish_once(
                runs_repo=runs_repo,
                run_id=run_uuid,
                event="step.enrichment_completed",
                payload={
                    "run_id": str(run_uuid),
                    "workspace_id": workspace_id,
                    "playbook_id": playbook_id,
                    "step": {"id": current_step_id},
                    "phase": "enrich",
                    "ended_at": datetime.now(timezone.utc).isoformat(),
                    "status": "enrichment_completed",
                },
                workspace_id=workspace_id,
                playbook_id=playbook_id,
                step_id=current_step_id,
                phase="enrich",
                strategy=strategy,
                emitter="capability_executor",
                correlation_id=correlation_id,
            )
            await publisher.publish_once(
                runs_repo=runs_repo,
                run_id=run_uuid,
                event="step.completed",
                payload={
                    "run_id": str(run_uuid),
                    "workspace_id": workspace_id,
                    "playbook_id": playbook_id,
                    "step": {"id": current_step_id},
                    "ended_at": datetime.now(timezone.utc).isoformat(),
                    "status": "completed",
                },
                workspace_id=workspace_id,
                playbook_id=playbook_id,
                step_id=current_step_id,
                strategy=strategy,
                emitter="capability_executor",
                correlation_id=correlation_id,
            )

            step_idx += 1
            current_step_id = None
            phase = "discover"
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
            # Emit step.failed (discover)
            await publisher.publish_once(
                runs_repo=runs_repo,
                run_id=run_uuid,
                event="step.failed",
                payload={
                    "run_id": str(run_uuid),
                    "workspace_id": workspace_id,
                    "playbook_id": playbook_id,
                    "step": {"id": step_id},
                    "phase": "discover",
                    "ended_at": datetime.now(timezone.utc).isoformat(),
                    "error": f"Capability '{cap_id}' not found in pack.",
                    "status": "failed",
                },
                workspace_id=workspace_id,
                playbook_id=playbook_id,
                step_id=step_id,
                phase="discover",
                strategy=strategy,
                emitter="capability_executor",
                correlation_id=correlation_id,
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

        # Emit step.started (once per step)  — NOTE: params removed from payload
        await publisher.publish_once(
            runs_repo=runs_repo,
            run_id=run_uuid,
            event="step.started",
            payload={
                "run_id": str(run_uuid),
                "workspace_id": workspace_id,
                "playbook_id": playbook_id,
                "step": {"id": step_id, "capability_id": cap_id, "name": step.get("name")},
                "produces_kinds": (cap.get("produces_kinds") or []),
                "started_at": datetime.now(timezone.utc).isoformat(),
                "status": "started",
            },
            workspace_id=workspace_id,
            playbook_id=playbook_id,
            step_id=step_id,
            strategy=strategy,
            emitter="capability_executor",
            correlation_id=correlation_id,
        )

        # Emit discovery_started
        await publisher.publish_once(
            runs_repo=runs_repo,
            run_id=run_uuid,
            event="step.discovery_started",
            payload={
                "run_id": str(run_uuid),
                "workspace_id": workspace_id,
                "playbook_id": playbook_id,
                "step": {"id": step_id},
                "phase": "discover",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "status": "discovery_started",
            },
            workspace_id=workspace_id,
            playbook_id=playbook_id,
            step_id=step_id,
            phase="discover",
            strategy=strategy,
            emitter="capability_executor",
            correlation_id=correlation_id,
        )

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
            # Emit step.failed (discover)
            await publisher.publish_once(
                runs_repo=runs_repo,
                run_id=run_uuid,
                event="step.failed",
                payload={
                    "run_id": str(run_uuid),
                    "workspace_id": workspace_id,
                    "playbook_id": playbook_id,
                    "step": {"id": step_id},
                    "phase": "discover",
                    "ended_at": datetime.now(timezone.utc).isoformat(),
                    "error": f"Unsupported mode '{mode}'",
                    "status": "failed",
                },
                workspace_id=workspace_id,
                playbook_id=playbook_id,
                step_id=step_id,
                phase="discover",
                strategy=strategy,
                emitter="capability_executor",
                correlation_id=correlation_id,
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
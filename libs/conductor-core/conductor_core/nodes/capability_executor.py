# conductor_core/nodes/capability_executor.py
from __future__ import annotations

from typing import Any, Dict, List
from uuid import UUID
from datetime import datetime, timezone
import logging

from typing_extensions import Literal
from langgraph.types import Command

from conductor_core.protocols.repositories import (
    RunRepositoryProtocol as RunRepository,
    EventPublisherProtocol as EventPublisher,
)

logger = logging.getLogger("conductor_core.nodes.capability_executor")


def capability_executor_node(*, runs_repo: RunRepository, publisher: EventPublisher, skip_diagram: bool = False, skip_narrative: bool = False):

    def _log_terminal_state(state: Dict[str, Any], update: Dict[str, Any], reason: str) -> None:
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
    ) -> Command[Literal["mcp_input_resolver", "llm_execution", "diagram_enrichment", "narrative_enrichment", "capability_executor", "persist_run"]] | Dict[str, Any]:
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

        # Three-phase step: discover -> enrich (diagram) -> narrative_enrich
        phase = state.get("phase") or "discover"

        # Sole writer policy: only this node writes current_step_id/step_idx/phase advancement.
        current_step_id = state.get("current_step_id")
        last_mcp = state.get("last_mcp_summary") or {}
        last_mcp_error = state.get("last_mcp_error")
        last_enrich = state.get("last_enrichment_summary") or {}
        last_enrich_error = state.get("last_enrichment_error")
        last_narrative = state.get("last_narrative_summary") or {}
        last_narrative_error = state.get("last_narrative_error")

        # Terminate on executor-reported discovery failure -> persist_run
        if last_mcp_error and current_step_id:
            logs.append(f"MCP failure: {last_mcp_error}")

            pb = next((p for p in (pack.get("playbooks") or []) if p.get("id") == playbook_id), None)
            current_step = None
            if pb:
                current_step = next((s for s in pb.get("steps", []) if s.get("id") == current_step_id), None)

            await publisher.publish_once(
                runs_repo=runs_repo,
                run_id=run_uuid,
                event="step.failed",
                payload={
                    "run_id": str(run_uuid),
                    "workspace_id": workspace_id,
                    "playbook_id": playbook_id,
                    "step": {
                        "id": current_step_id,
                        "name": current_step.get("name") if current_step else None,
                        "description": current_step.get("description") if current_step else None,
                    },
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
                "last_enrichment_summary": {},
                "last_enrichment_error": None,
                "last_narrative_summary": {},
                "last_narrative_error": None,
            }
            _log_terminal_state(state, term_update, reason="mcp_error")
            return Command(goto="persist_run", update=term_update)

        # Enrichment error policy (soft-continue)
        if last_enrich_error:
            logs.append(f"Enrichment warning (soft-continue): {last_enrich_error}")

        # Narrative enrichment error policy (soft-continue)
        if last_narrative_error:
            logs.append(f"Narrative enrichment warning (soft-continue): {last_narrative_error}")

        # Consume completion breadcrumbs depending on phase
        if phase == "discover" and current_step_id and last_mcp.get("completed_step_id") == current_step_id:
            pb = next((p for p in (pack.get("playbooks") or []) if p.get("id") == playbook_id), None)
            current_step = None
            if pb:
                current_step = next((s for s in pb.get("steps", []) if s.get("id") == current_step_id), None)

            await publisher.publish_once(
                runs_repo=runs_repo,
                run_id=run_uuid,
                event="step.discovery_completed",
                payload={
                    "run_id": str(run_uuid),
                    "workspace_id": workspace_id,
                    "playbook_id": playbook_id,
                    "step": {
                        "id": current_step_id,
                        "name": current_step.get("name") if current_step else None,
                        "description": current_step.get("description") if current_step else None,
                    },
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

            if skip_diagram and skip_narrative:
                # Skip both enrichment phases: emit step.completed and advance immediately
                logger.info("[capability_executor] skip_diagram+skip_narrative step_id=%s", current_step_id)
                await publisher.publish_once(
                    runs_repo=runs_repo,
                    run_id=run_uuid,
                    event="step.completed",
                    payload={
                        "run_id": str(run_uuid),
                        "workspace_id": workspace_id,
                        "playbook_id": playbook_id,
                        "step": {
                            "id": current_step_id,
                            "name": current_step.get("name") if current_step else None,
                            "description": current_step.get("description") if current_step else None,
                        },
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
                return Command(
                    goto="capability_executor",
                    update={
                        "step_idx": step_idx + 1,
                        "current_step_id": None,
                        "phase": "discover",
                        "last_mcp_summary": {},
                        "last_mcp_error": None,
                        "last_enrichment_summary": {},
                        "last_enrichment_error": None,
                        "last_narrative_summary": {},
                        "last_narrative_error": None,
                    },
                )
            elif skip_diagram:
                # Skip diagram only: jump straight to narrative_enrich phase
                logger.info("[capability_executor] skip_diagram->narrative_enrich step_id=%s", current_step_id)
                return Command(
                    goto="narrative_enrichment",
                    update={
                        "step_idx": step_idx,
                        "current_step_id": current_step_id,
                        "phase": "narrative_enrich",
                        "last_mcp_summary": {},
                        "last_mcp_error": None,
                        "last_enrichment_summary": {},
                        "last_enrichment_error": None,
                        "last_narrative_summary": {},
                        "last_narrative_error": None,
                    },
                )

            logger.info("[capability_executor] phase_transition discover->enrich step_id=%s", current_step_id)
            phase = "enrich"
            await publisher.publish_once(
                runs_repo=runs_repo,
                run_id=run_uuid,
                event="step.enrichment_started",
                payload={
                    "run_id": str(run_uuid),
                    "workspace_id": workspace_id,
                    "playbook_id": playbook_id,
                    "step": {
                        "id": current_step_id,
                        "name": current_step.get("name") if current_step else None,
                        "description": current_step.get("description") if current_step else None,
                    },
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
            return Command(
                goto="diagram_enrichment",
                update={
                    "step_idx": step_idx,
                    "current_step_id": current_step_id,
                    "phase": phase,
                    "dispatch": state.get("dispatch") or {},
                    "last_mcp_summary": {},
                    "last_mcp_error": None,
                },
            )

        if phase == "enrich" and current_step_id and last_enrich.get("completed_step_id") == current_step_id:
            pb = next((p for p in (pack.get("playbooks") or []) if p.get("id") == playbook_id), None)
            current_step = None
            if pb:
                current_step = next((s for s in pb.get("steps", []) if s.get("id") == current_step_id), None)

            await publisher.publish_once(
                runs_repo=runs_repo,
                run_id=run_uuid,
                event="step.enrichment_completed",
                payload={
                    "run_id": str(run_uuid),
                    "workspace_id": workspace_id,
                    "playbook_id": playbook_id,
                    "step": {
                        "id": current_step_id,
                        "name": current_step.get("name") if current_step else None,
                        "description": current_step.get("description") if current_step else None,
                    },
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
            if skip_narrative:
                # Skip narrative enrichment: emit step.completed and advance immediately
                logger.info("[capability_executor] skip_narrative step_id=%s", current_step_id)
                pb2 = next((p for p in (pack.get("playbooks") or []) if p.get("id") == playbook_id), None)
                cs2 = None
                if pb2:
                    cs2 = next((s for s in pb2.get("steps", []) if s.get("id") == current_step_id), None)
                await publisher.publish_once(
                    runs_repo=runs_repo,
                    run_id=run_uuid,
                    event="step.completed",
                    payload={
                        "run_id": str(run_uuid),
                        "workspace_id": workspace_id,
                        "playbook_id": playbook_id,
                        "step": {
                            "id": current_step_id,
                            "name": cs2.get("name") if cs2 else None,
                            "description": cs2.get("description") if cs2 else None,
                        },
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
                return Command(
                    goto="capability_executor",
                    update={
                        "step_idx": step_idx + 1,
                        "current_step_id": None,
                        "phase": "discover",
                        "last_enrichment_summary": {},
                        "last_enrichment_error": None,
                        "last_narrative_summary": {},
                        "last_narrative_error": None,
                    },
                )

            logger.info("[capability_executor] phase_transition enrich->narrative_enrich step_id=%s", current_step_id)
            return Command(
                goto="narrative_enrichment",
                update={
                    "step_idx": step_idx,
                    "current_step_id": current_step_id,
                    "phase": "narrative_enrich",
                    "dispatch": state.get("dispatch") or {},
                    "last_enrichment_summary": {},
                    "last_enrichment_error": None,
                    "last_narrative_summary": {},
                    "last_narrative_error": None,
                },
            )

        if phase == "narrative_enrich" and current_step_id and last_narrative.get("completed_step_id") == current_step_id:
            pb = next((p for p in (pack.get("playbooks") or []) if p.get("id") == playbook_id), None)
            current_step = None
            if pb:
                current_step = next((s for s in pb.get("steps", []) if s.get("id") == current_step_id), None)

            await publisher.publish_once(
                runs_repo=runs_repo,
                run_id=run_uuid,
                event="step.completed",
                payload={
                    "run_id": str(run_uuid),
                    "workspace_id": workspace_id,
                    "playbook_id": playbook_id,
                    "step": {
                        "id": current_step_id,
                        "name": current_step.get("name") if current_step else None,
                        "description": current_step.get("description") if current_step else None,
                    },
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
            logger.info("[capability_executor] narrative_enrich_complete advancing_to_step_idx=%d", step_idx)

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
                "last_narrative_summary": {},
                "last_narrative_error": None,
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
                "last_narrative_summary": {},
                "last_narrative_error": None,
            }
            _log_terminal_state(state, term_update, reason="playbook_not_found")
            return Command(goto="persist_run", update=term_update)

        steps = pb.get("steps", []) or []
        if step_idx >= len(steps):
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
                "last_narrative_summary": {},
                "last_narrative_error": None,
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

        # If we arrive here with phase="narrative_enrich" but no narrative breadcrumb yet
        if phase == "narrative_enrich" and current_step_id:
            logger.info("[capability_executor] dispatch_narrative_enrichment step_id=%s", current_step_id)
            return Command(
                goto="narrative_enrichment",
                update={
                    "step_idx": step_idx,
                    "current_step_id": current_step_id,
                    "phase": "narrative_enrich",
                    "dispatch": state.get("dispatch") or {},
                    "last_narrative_summary": {},
                    "last_narrative_error": None,
                },
            )

        # Discovery phase: dispatch next step
        step = steps[step_idx]
        step_id = step["id"]
        cap_id = step["capability_id"]
        caps = {c.get("id"): c for c in (pack.get("capabilities") or [])}
        cap = caps.get(cap_id)
        if not cap:
            await runs_repo.step_failed(run_uuid, step_id, error=f"Capability '{cap_id}' not found in pack.")
            logger.info(
                "[capability_executor] step_skipped_missing_cap step_idx=%d step_id=%s cap_id=%s",
                step_idx, step_id, cap_id,
            )
            await publisher.publish_once(
                runs_repo=runs_repo,
                run_id=run_uuid,
                event="step.failed",
                payload={
                    "run_id": str(run_uuid),
                    "workspace_id": workspace_id,
                    "playbook_id": playbook_id,
                    "step": {"id": step_id, "name": step.get("name"), "description": step.get("description")},
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
                update={"step_idx": step_idx + 1, "phase": "discover", "current_step_id": None,
                        "last_enrichment_summary": {}, "last_enrichment_error": None},
            )

        mode = (cap.get("execution") or {}).get("mode")
        logger.info(
            "[capability_executor] dispatch step_idx=%d step_id=%s cap_id=%s mode=%s",
            step_idx, step_id, cap_id, mode,
        )

        await runs_repo.step_started(run_uuid, step_id)

        await publisher.publish_once(
            runs_repo=runs_repo,
            run_id=run_uuid,
            event="step.started",
            payload={
                "run_id": str(run_uuid),
                "workspace_id": workspace_id,
                "playbook_id": playbook_id,
                "step": {"id": step_id, "capability_id": cap_id, "name": step.get("name"), "description": step.get("description")},
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

        await publisher.publish_once(
            runs_repo=runs_repo,
            run_id=run_uuid,
            event="step.discovery_started",
            payload={
                "run_id": str(run_uuid),
                "workspace_id": workspace_id,
                "playbook_id": playbook_id,
                "step": {"id": step_id, "name": step.get("name"), "description": step.get("description")},
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

        base_update = {
            "step_idx": step_idx,
            "current_step_id": step_id,
            "phase": "discover",
            "dispatch": {"capability": cap, "step": step},
            "last_mcp_summary": {},
            "last_mcp_error": None,
            "last_enrichment_summary": {},
            "last_enrichment_error": None,
            "last_narrative_summary": {},
            "last_narrative_error": None,
        }

        if mode == "mcp":
            return Command(goto="mcp_input_resolver", update=base_update)
        elif mode == "llm":
            return Command(goto="llm_execution", update=base_update)
        else:
            await runs_repo.step_failed(run_uuid, step_id, error=f"Unsupported mode '{mode}'")
            logger.info(
                "[capability_executor] step_failed_unsupported_mode step_idx=%d step_id=%s mode=%s",
                step_idx, step_id, mode,
            )
            await publisher.publish_once(
                runs_repo=runs_repo,
                run_id=run_uuid,
                event="step.failed",
                payload={
                    "run_id": str(run_uuid),
                    "workspace_id": workspace_id,
                    "playbook_id": playbook_id,
                    "step": {"id": step_id, "name": step.get("name"), "description": step.get("description")},
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
                update={"step_idx": step_idx + 1, "phase": "discover", "current_step_id": None},
            )

    return _node

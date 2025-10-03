# services/conductor-service/app/agent/graph.py
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, TypedDict

from langgraph.graph import StateGraph
from langgraph.graph.state import END

from app.clients.artifact_service import ArtifactServiceClient
from app.clients.capability_service import CapabilityServiceClient
from app.db.run_repository import RunRepository
from app.models.run_models import PlaybookRun

from app.agent.nodes.input_resolver import input_resolver_node


# ─────────────────────────────────────────────────────────────
# Graph state definition (what flows between nodes)
# Keep only what downstream nodes need; the DB stores step state, etc.
# ─────────────────────────────────────────────────────────────

class GraphState(TypedDict, total=False):
    # Request & run
    request: Dict[str, Any]                  # StartRunRequest as dict
    run: Dict[str, Any]                      # PlaybookRun as dict (used for run_id, etc.)

    # Resolved pack & metadata
    pack: Dict[str, Any]                     # resolved pack document (includes pack_input, capabilities, playbooks)
    artifact_kinds: Dict[str, Dict[str, Any]]  # resolved kind specs (pack holds only IDs)

    # Validated inputs + fingerprint
    inputs_valid: bool
    input_errors: list[str]
    input_fingerprint: Optional[str]

    # Logs & validations
    logs: list[str]
    validations: list[Dict[str, Any]]

    # Timeline
    started_at: str
    completed_at: Optional[str]


# ─────────────────────────────────────────────────────────────
# Helper: canonical JSON + fingerprint
# ─────────────────────────────────────────────────────────────

def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def sha256_fingerprint(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


# ─────────────────────────────────────────────────────────────
# Graph builder
# ─────────────────────────────────────────────────────────────

@dataclass
class ConductorGraph:
    """
    Thin wrapper that compiles a LangGraph with injected service clients
    and repository handles. Keeps graph wiring in one place.
    """
    runs_repo: RunRepository
    cap_client: CapabilityServiceClient
    art_client: ArtifactServiceClient

    def build(self):
        graph = StateGraph(GraphState)

        # Single node for now
        graph.add_node(
            "input_resolver",
            input_resolver_node(
                runs_repo=self.runs_repo,
                cap_client=self.cap_client,
                art_client=self.art_client,
                sha256_fingerprint=sha256_fingerprint,
            ),
        )

        # Entry → input_resolver → END
        graph.set_entry_point("input_resolver")
        graph.add_edge("input_resolver", END)

        return graph.compile()


# ─────────────────────────────────────────────────────────────
# Public entry (used by API): run single-node graph
# ─────────────────────────────────────────────────────────────

async def run_input_bootstrap(
    *,
    runs_repo: RunRepository,
    cap_client: CapabilityServiceClient,
    art_client: ArtifactServiceClient,
    start_request: Dict[str, Any],
    run_doc: PlaybookRun,
) -> GraphState:
    """
    Executes the single-node graph (input_resolver) to:
    - resolve pack, collect kinds, validate inputs,
    - initialize run steps (in DB).
    Returns the final graph state for diagnostics / API response.
    """
    compiled = ConductorGraph(
        runs_repo=runs_repo,
        cap_client=cap_client,
        art_client=art_client,
    ).build()

    now = datetime.now(timezone.utc).isoformat()

    initial_state: GraphState = {
        "request": start_request,
        "run": run_doc.model_dump(mode="json"),
        "artifact_kinds": {},
        "inputs_valid": False,
        "input_errors": [],
        "input_fingerprint": None,
        "logs": [],
        "validations": [],
        "started_at": now,
        "completed_at": None,
    }

    # .ainvoke returns the terminal state
    final_state: GraphState = await compiled.ainvoke(initial_state)
    return final_state
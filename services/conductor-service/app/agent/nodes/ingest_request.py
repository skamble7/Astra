# services/conductor-service/app/agent/nodes/ingest_request.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Dict

from app.db.mongodb import get_client
from app.db.run_repository import RunRepository
from app.models.run_models import PlaybookRun, RunStatus, StartRunRequest, StepState

logger = logging.getLogger("app.agent.nodes.ingest")


async def ingest_request(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize request and create an initial run document in Mongo (status=created).
    """
    req_dict = state["request"]
    req = StartRunRequest.model_validate(req_dict)

    # Fingerprint inputs for provenance
    canonical_inputs = json.dumps(req.inputs or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    input_fingerprint = "sha256:" + sha256(canonical_inputs.encode("utf-8")).hexdigest()

    run = PlaybookRun(
        workspace_id=req.workspace_id,
        pack_id=req.pack_id,
        playbook_id=req.playbook_id,
        inputs=req.inputs or {},
        input_fingerprint=input_fingerprint,
        status=RunStatus.CREATED,
        title=req.title,
        description=req.description,
    )

    client = get_client()
    repo = RunRepository(client, db_name=client.get_default_database().name)
    await repo.ensure_indexes()
    await repo.create(run)

    state["run"] = {
        "run_id": str(run.run_id),
        "workspace_id": str(run.workspace_id),
        "pack_id": run.pack_id,
        "playbook_id": run.playbook_id,
        "title": run.title,
        "description": run.description,
        "strategy": None,  # decided later
        "started_at": None,
        "completed_at": None,
    }
    state["inputs"] = {
        "raw": req.inputs or {},
        "fingerprint": input_fingerprint,
        "validation": {"ok": None, "errors": []},
    }
    state["pack"] = {}
    state["registry"] = {"kinds_by_id": {}}
    state["mcp"] = {"clients": {}, "discovery_reports": {}}
    state["steps"] = {"current_index": 0, "results": []}
    state["aggregates"] = {"run_artifacts": [], "validations": [], "logs": []}
    state["persistence"] = {"artifact_ids": [], "artifact_failures": []}
    state["timers"] = {"t0": datetime.now(timezone.utc).isoformat()}

    logger.info("Run created: run_id=%s", state["run"]["run_id"])
    return state
# services/conductor-service/app/core/validation.py
from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from app.clients.artifact_service import ArtifactServiceClient
from app.models.run_models import ArtifactEnvelope, ValidationIssue

logger = logging.getLogger("app.core.validation")


async def validate_artifacts(items: List[ArtifactEnvelope]) -> Tuple[List[ValidationIssue], List[ArtifactEnvelope]]:
    """
    Validate each artifact with artifact-service /registry/validate.
    Returns (issues, valid_items). For now we drop invalids (strict).
    """
    svc = ArtifactServiceClient()
    issues: List[ValidationIssue] = []
    valids: List[ArtifactEnvelope] = []
    for a in items:
        try:
            await svc.registry_validate(kind=a.kind_id, data=a.data, version=a.schema_version)
            valids.append(a)
        except Exception as e:
            issues.append(
                ValidationIssue(
                    artifact_key={"kind_id": a.kind_id, "identity": a.identity},
                    severity="high",
                    message=str(e),
                )
            )
    return issues, valids
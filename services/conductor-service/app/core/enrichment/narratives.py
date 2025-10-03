# services/conductor-service/app/core/enrichment/narratives.py
from __future__ import annotations

from typing import Dict, List

from app.models.run_models import ArtifactEnvelope


async def enrich_narratives(items: List[ArtifactEnvelope], kinds_by_id: Dict[str, dict]) -> List[ArtifactEnvelope]:
    """
    Minimal enrichment: add a short markdown explainer if missing.
    """
    out: List[ArtifactEnvelope] = []
    for a in items:
        if not a.narratives:
            a.narratives = [
                {
                    "id": "auto-summary",
                    "title": "Auto Summary",
                    "format": "markdown",
                    "locale": "en-US",
                    "audience": "developer",
                    "tone": "explanatory",
                    "body": f"# {a.kind_id}\n\nAuto-generated narrative.\n",
                }
            ]
        out.append(a)
    return out
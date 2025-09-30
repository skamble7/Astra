# services/conductor-service/app/core/enrichment/diagrams.py
from __future__ import annotations

from typing import Dict, List

from app.models.run_models import ArtifactEnvelope


async def enrich_diagrams(items: List[ArtifactEnvelope], kinds_by_id: Dict[str, dict]) -> List[ArtifactEnvelope]:
    """
    Minimal enrichment: if an artifact has no diagrams and the kind has a diagram recipe hint,
    attach a stub mermaid block so downstream UIs have something to render.
    """
    out: List[ArtifactEnvelope] = []
    for a in items:
        if not a.diagrams:
            a.diagrams = [
                {
                    "recipe_id": "auto.stub",
                    "view": "flowchart",
                    "language": "mermaid",
                    "instructions": "flowchart TD\n  A[Artifact] --> B[Produced]\n",
                    "renderer_hints": {"wrap": True},
                }
            ]
        out.append(a)
    return out
# services/artifact-service/app/models/artifact.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict

# ─────────────────────────────────────────────────────────────
# Types
# ─────────────────────────────────────────────────────────────
ArtifactKind = str


class Provenance(BaseModel):
    run_id: Optional[str] = None
    playbook_id: Optional[str] = None
    model_id: Optional[str] = None
    step: Optional[str] = None
    pack_key: Optional[str] = None
    pack_version: Optional[str] = None
    inputs_fingerprint: Optional[str] = None
    author: Optional[str] = None
    agent: Optional[str] = None
    reason: Optional[str] = None
    source_repo: Optional[str] = None
    source_ref: Optional[str] = None
    source_commit: Optional[str] = None


class WorkspaceSnapshot(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    id: str = Field(..., alias="_id")
    name: str
    description: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class Lineage(BaseModel):
    first_seen_run_id: Optional[str] = None
    last_seen_run_id: Optional[str] = None
    supersedes: List[str] = Field(default_factory=list)
    superseded_by: Optional[str] = None


# ─────────────────────────────────────────────────────────────
# Diagrams
# ─────────────────────────────────────────────────────────────
class DiagramInstance(BaseModel):
    recipe_id: Optional[str] = Field(default=None)
    view: Optional[str] = Field(default=None)
    language: str = Field(default="mermaid")
    instructions: str
    renderer_hints: Optional[Dict[str, Any]] = None
    generated_from_fingerprint: Optional[str] = None
    prompt_rev: Optional[int] = None
    provenance: Optional[Provenance] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────────────────────
# Narratives  (NEW)
# ─────────────────────────────────────────────────────────────
class NarrativeInstance(BaseModel):
    """
    Human-readable explanation for an artifact instance (e.g., Markdown).
    Multiple variants allowed for audience/locale/tone.
    """
    id: Optional[str] = None                         # stable within artifact
    title: Optional[str] = None                      # e.g., "Architect view"
    format: str = Field(default="markdown")          # markdown | asciidoc
    locale: str = Field(default="en-US")
    audience: Optional[str] = None                   # architect | developer | ...
    tone: Optional[str] = None                       # explanatory | concise | ...
    body: str                                        # the narrative text
    renderer_hints: Optional[Dict[str, Any]] = None

    generated_from_fingerprint: Optional[str] = None
    prompt_rev: Optional[int] = None
    provenance: Optional[Provenance] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ArtifactItem(BaseModel):
    """Embedded artifact stored inside the per-workspace parent document."""
    artifact_id: str = Field(default_factory=lambda: str(uuid4()))
    kind: ArtifactKind
    name: str
    data: Dict[str, Any]

    # Diagrams & Narratives
    diagrams: List[DiagramInstance] = Field(default_factory=list)
    narratives: List[NarrativeInstance] = Field(default_factory=list)   # NEW

    # Identity & versioning
    natural_key: Optional[str] = None
    fingerprint: Optional[str] = None              # data-only
    diagram_fingerprint: Optional[str] = None
    narrative_fingerprint: Optional[str] = None    # NEW: narratives array
    version: int = 1
    lineage: Optional[Lineage] = None

    # Timestamps / status
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    deleted_at: Optional[datetime] = None

    provenance: Optional[Provenance] = None


class ArtifactItemCreate(BaseModel):
    """Write payload used by learning-service (or UI) to add/upsert artifacts."""
    kind: ArtifactKind
    name: str
    data: Dict[str, Any]
    diagrams: Optional[List[DiagramInstance]] = None
    narratives: Optional[List[NarrativeInstance]] = None               # NEW
    natural_key: Optional[str] = None
    fingerprint: Optional[str] = None
    provenance: Optional[Provenance] = None


class ArtifactItemReplace(BaseModel):
    data: Optional[Dict[str, Any]] = None
    diagrams: Optional[List[DiagramInstance]] = None
    narratives: Optional[List[NarrativeInstance]] = None               # NEW
    provenance: Optional[Provenance] = None


class ArtifactItemPatchIn(BaseModel):
    patch: List[Dict[str, Any]]
    provenance: Optional[Provenance] = None


class WorkspaceArtifactsDoc(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    workspace_id: str
    workspace: WorkspaceSnapshot

    baseline: Dict[str, Any] = Field(default_factory=dict)
    baseline_fingerprint: Optional[str] = None
    baseline_version: int = 1
    last_promoted_run_id: Optional[str] = None

    artifacts: List[ArtifactItem] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

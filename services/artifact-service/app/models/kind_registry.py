# services/artifact-service/app/models/kind_registry.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

# ─────────────────────────────────────────────────────────────
# Prompt specs
# ─────────────────────────────────────────────────────────────

class PromptVariantSpec(BaseModel):
    name: str
    when: Optional[Dict[str, Any]] = None
    system: Optional[str] = None
    user_template: Optional[str] = None


class PromptSpec(BaseModel):
    system: str
    user_template: Optional[str] = None
    variants: List[PromptVariantSpec] = Field(default_factory=list)
    io_hints: Optional[Dict[str, Any]] = None
    strict_json: bool = True
    prompt_rev: int = 1


# ─────────────────────────────────────────────────────────────
# Diagram generation specs
# ─────────────────────────────────────────────────────────────

DiagramLanguage = Literal["mermaid", "plantuml", "graphviz", "d2", "nomnoml", "dot"]
DiagramView = Literal[
    "sequence", "flowchart", "class", "component", "deployment",
    "state", "activity", "mindmap", "er", "gantt", "timeline", "journey",
]

class DiagramPromptSpec(BaseModel):
    system: str
    user_template: Optional[str] = None
    variants: List[PromptVariantSpec] = Field(default_factory=list)
    strict_text: bool = True
    prompt_rev: int = 1
    io_hints: Optional[Dict[str, Any]] = None

class DiagramRecipeSpec(BaseModel):
    id: str
    title: str
    view: DiagramView
    language: DiagramLanguage = "mermaid"
    description: Optional[str] = None
    template: Optional[str] = None
    prompt: Optional[DiagramPromptSpec] = None
    renderer_hints: Optional[Dict[str, Any]] = None
    examples: List[Dict[str, Any]] = Field(default_factory=list)
    depends_on: Optional["DependsOnSpec"] = None


# ─────────────────────────────────────────────────────────────
# Narratives spec (NEW, schema-level constraints)
# ─────────────────────────────────────────────────────────────

class NarrativesSpec(BaseModel):
    allowed_formats: List[str] = Field(default_factory=lambda: ["markdown", "asciidoc"])
    default_format: str = "markdown"
    max_length_chars: int = 20000
    allowed_locales: List[str] = Field(default_factory=lambda: ["en-US"])
    renderer_hints: Optional[Dict[str, Any]] = None


# ─────────────────────────────────────────────────────────────
# Identity / adapters / migrators
# ─────────────────────────────────────────────────────────────

class IdentitySpec(BaseModel):
    natural_key: Optional[Any] = None
    summary_rule: Optional[str] = None           # kept for backward compat; unused now
    category: Optional[str] = None


class AdapterSpec(BaseModel):
    type: Literal["builtin", "dsl"] = "builtin"
    ref: Optional[str] = None
    dsl: Optional[Dict[str, Any]] = None


class MigratorSpec(BaseModel):
    from_version: str
    to_version: str
    type: Literal["builtin", "dsl"] = "builtin"
    ref: Optional[str] = None
    dsl: Optional[Dict[str, Any]] = None


# ─────────────────────────────────────────────────────────────
# Dependencies
# ─────────────────────────────────────────────────────────────

class DependsOnSpec(BaseModel):
    hard: List[str] = Field(default_factory=list)
    soft: List[str] = Field(default_factory=list)
    context_hint: Optional[str] = None

    @field_validator("hard", "soft", mode="before")
    @classmethod
    def _coerce_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            return [str(x) for x in v if x]
        return []


# ─────────────────────────────────────────────────────────────
# Versioned schema entry for a kind
# ─────────────────────────────────────────────────────────────

class SchemaVersionSpec(BaseModel):
    version: str
    json_schema: Dict[str, Any]
    additional_props_policy: Literal["forbid", "allow"] = "forbid"

    # Data-generation prompt (JSON)
    prompt: PromptSpec

    # Diagram recipes for this schema version
    diagram_recipes: List[DiagramRecipeSpec] = Field(default_factory=list)

    # NEW: narratives spec (constraints & defaults for instance narratives)
    narratives_spec: Optional[NarrativesSpec] = None

    identity: Optional[IdentitySpec] = None
    adapters: List[AdapterSpec] = Field(default_factory=list)
    migrators: List[MigratorSpec] = Field(default_factory=list)
    examples: List[Dict[str, Any]] = Field(default_factory=list)

    depends_on: Optional[DependsOnSpec] = None

    @field_validator("depends_on", mode="before")
    @classmethod
    def _normalize_depends_on(cls, v):
        if v is None:
            return None
        if isinstance(v, list):
            return DependsOnSpec(soft=[str(x) for x in v if x])
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            return DependsOnSpec(soft=[v])
        return None


# ─────────────────────────────────────────────────────────────
# Kind registry documents
# ─────────────────────────────────────────────────────────────

class KindRegistryDoc(BaseModel):
    id: str = Field(alias="_id")
    title: Optional[str] = None
    # REMOVED: summary
    category: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    status: Literal["active", "deprecated"] = "active"

    latest_schema_version: str
    schema_versions: List[SchemaVersionSpec]

    policies: Optional[Dict[str, Any]] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RegistryMetaDoc(BaseModel):
    id: str = Field(alias="_id")
    etag: str
    registry_version: int = 1
    updated_at: datetime

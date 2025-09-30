from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from .capability_models import ToolCallSpec, GlobalCapability
from .pack_input_models import PackInput  # ← registered input definition (id, name, json_schema, ...)

ExecutionMode = Literal["mcp", "llm"]


class ResolvedPlaybookStep(BaseModel):
    """
    A step annotated with execution mode, produced kinds, and (for MCP) tool_calls.
    """
    id: str
    name: str
    capability_id: str
    params: dict = Field(default_factory=dict)

    execution_mode: ExecutionMode
    produces_kinds: List[str] = Field(default_factory=list)
    required_kinds: List[str] = Field(default_factory=list)  # reserved for learning-service enrichment
    tool_calls: Optional[List[ToolCallSpec]] = None          # only for MCP


class ResolvedPlaybook(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    steps: List[ResolvedPlaybookStep] = Field(default_factory=list)


class ResolvedPackView(BaseModel):
    """
    Full resolved view for executors/UI:
      - pack header
      - pack_input_id (declares which registered input shape can trigger this pack)
      - pack_input (full PackInput definition; optional if not found)
      - capability_ids (as stored on the pack)
      - capabilities: full GlobalCapability documents for those ids (ordered)
      - playbooks: steps annotated with execution metadata derived from capabilities
    """
    pack_id: str
    key: str
    version: str
    title: str
    description: str

    pack_input_id: Optional[str] = None
    pack_input: Optional[PackInput] = None

    capability_ids: List[str] = Field(default_factory=list)
    capabilities: List[GlobalCapability] = Field(default_factory=list)
    playbooks: List[ResolvedPlaybook] = Field(default_factory=list)
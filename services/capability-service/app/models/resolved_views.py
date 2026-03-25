# services/capability-service/app/models/resolved_views.py
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from .capability_models import GlobalCapability

ExecutionMode = Literal["mcp", "llm"]


class ResolvedPlaybookStep(BaseModel):
    """
    A step annotated with execution mode, produced kinds, and (for MCP) the tool name.
    """
    id: str
    name: str
    capability_id: str

    execution_mode: ExecutionMode
    produces_kinds: List[str] = Field(default_factory=list)
    required_kinds: List[str] = Field(default_factory=list)  # reserved for learning-service enrichment
    tool_name: Optional[str] = None  # only for MCP


class ResolvedPlaybook(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    steps: List[ResolvedPlaybookStep] = Field(default_factory=list)


class ResolvedPackView(BaseModel):
    """
    Full resolved view for executors/UI:
      - pack header
      - capability_ids (as stored on the pack; used by playbook steps)
      - agent_capability_ids (ids of capabilities the agent may use outside steps)
      - capabilities: full GlobalCapability documents for capability_ids (ordered)
      - agent_capabilities: full GlobalCapability documents for agent_capability_ids (ordered)
      - playbooks: steps annotated with execution metadata derived from capabilities
    """
    pack_id: str
    key: str
    version: str
    title: str
    description: str

    capability_ids: List[str] = Field(default_factory=list)
    agent_capability_ids: List[str] = Field(default_factory=list)

    capabilities: List[GlobalCapability] = Field(default_factory=list)
    agent_capabilities: List[GlobalCapability] = Field(default_factory=list)

    playbooks: List[ResolvedPlaybook] = Field(default_factory=list)
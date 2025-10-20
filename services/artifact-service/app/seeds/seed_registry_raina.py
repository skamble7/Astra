# services/artifact-service/app/seeds/seed_registry_raina.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from app.dal.kind_registry_dal import upsert_kind

LATEST = "1.0.0"

DEFAULT_NARRATIVES_SPEC: Dict[str, Any] = {
    "allowed_formats": ["markdown", "asciidoc"],
    "default_format": "markdown",
    "max_length_chars": 20000,
    "allowed_locales": ["en-US"],
}

NOW = datetime.utcnow()

def make_kind_doc(
    *,
    _id: str,
    title: str,
    category: str,
    json_schema: Dict[str, Any],
    prompt_system: str,
    aliases: Optional[List[str]] = None,
    depends_on: Optional[Dict[str, Any]] = None,
    identity: Optional[Dict[str, Any]] = None,
    examples: Optional[List[Dict[str, Any]]] = None,
    diagram_recipes: Optional[List[Dict[str, Any]]] = None,
    status: str = "active",
) -> Dict[str, Any]:
    return {
        "_id": _id,
        "title": title,
        "category": category,
        "aliases": aliases or [],
        "status": status,
        "latest_schema_version": LATEST,
        "schema_versions": [{
            "version": LATEST,
            "json_schema": json_schema,
            "additional_props_policy": "allow",
            "prompt": {
                "system": prompt_system,
                "strict_json": True
            },
            **({"depends_on": depends_on} if depends_on else {}),
            **({"identity": identity} if identity else {}),
            **({"examples": examples} if examples else {}),
            **({"diagram_recipes": diagram_recipes} if diagram_recipes else {}),
            "narratives_spec": DEFAULT_NARRATIVES_SPEC,
        }],
        "policies": {},
        "created_at": NOW,
        "updated_at": NOW,
    }

# ---------------------------------------------------------------------------
# Helpers for concise schema shapes (Astra prefers relaxed/allow)
# ---------------------------------------------------------------------------
def obj(props: Dict[str, Any], *, req: Optional[List[str]] = None, addl: bool = True) -> Dict[str, Any]:
    return {"type": "object", "additionalProperties": addl, "properties": props, "required": req or []}

def arr(items: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "array", "items": items}

def str_enum(vals: List[str]) -> Dict[str, Any]:
    return {"type": "string", "enum": vals}

# ---------------------------------------------------------------------------
# Diagram kinds (added)
# ---------------------------------------------------------------------------
def _diagram_schema() -> Dict[str, Any]:
    """
    Minimal, relaxed schema for diagrams that unblocks registry lookups
    and LLM execution. 'instructions' carries the full Draw.io XML.
    """
    node = obj({
        "id": {"type": "string"},
        "name": {"type": "string"},
        "type": {"type": ["string", "null"]},
        "meta": obj({}, addl=True),
    })
    edge = obj({
        "from": {"type": "string"},
        "to": {"type": "string"},
        "label": {"type": ["string", "null"]},
        "meta": obj({}, addl=True),
    })
    return obj({
        "language": str_enum(["drawio"]),
        "instructions": {"type": "string", "minLength": 20},
        "nodes": arr(node),
        "edges": arr(edge),
        "notes": {"type": ["string", "null"]},
    })

def _diagram_prompt(diagram_type: str) -> str:
    # Keep it short; Astra uses only prompt.system here.
    return (
        "You are RAINA: Diagram Extractor. Produce exactly one JSON object. "
        "Set `language` to `drawio` and put a complete Draw.io <mxfile> XML document in `instructions`. "
        "Keep any discovered nodes/edges in the arrays when available. No prose."
    )

diagram_docs: List[Dict[str, Any]] = []
diagram_docs.append(make_kind_doc(
    _id="cam.diagram.context",
    title="Context Diagram",
    category="diagram",
    json_schema=_diagram_schema(),
    prompt_system=_diagram_prompt("context"),
))
diagram_docs.append(make_kind_doc(
    _id="cam.diagram.class",
    title="Class Diagram",
    category="diagram",
    json_schema=_diagram_schema(),
    prompt_system=_diagram_prompt("class"),
    aliases=["cam.erd"],
))
diagram_docs.append(make_kind_doc(
    _id="cam.diagram.sequence",
    title="Sequence Diagram",
    category="diagram",
    json_schema=_diagram_schema(),
    prompt_system=_diagram_prompt("sequence"),
))
diagram_docs.append(make_kind_doc(
    _id="cam.diagram.component",
    title="Component Diagram",
    category="diagram",
    json_schema=_diagram_schema(),
    prompt_system=_diagram_prompt("component"),
))
diagram_docs.append(make_kind_doc(
    _id="cam.diagram.deployment",
    title="Deployment Diagram",
    category="diagram",
    json_schema=_diagram_schema(),
    prompt_system=_diagram_prompt("deployment"),
))
diagram_docs.append(make_kind_doc(
    _id="cam.diagram.state",
    title="State Diagram",
    category="diagram",
    json_schema=_diagram_schema(),
    prompt_system=_diagram_prompt("state"),
))
diagram_docs.append(make_kind_doc(
    _id="cam.diagram.activity",
    title="Activity Diagram",
    category="diagram",
    json_schema=_diagram_schema(),
    prompt_system=_diagram_prompt("activity"),
))
diagram_docs.append(make_kind_doc(
    _id="cam.diagram.dataflow",
    title="Dataflow Diagram",
    category="diagram",
    json_schema=_diagram_schema(),
    prompt_system=_diagram_prompt("dataflow"),
))
diagram_docs.append(make_kind_doc(
    _id="cam.diagram.network",
    title="Network Diagram",
    category="diagram",
    json_schema=_diagram_schema(),
    prompt_system=_diagram_prompt("network"),
))

# ---------------------------------------------------------------------------
# Canonical list from RainaV2 (non-diagram only)
# ---------------------------------------------------------------------------
KINDS = [
    # 2.2 PAT
    "cam.pat.moscow_prioritization","cam.pat.requirements_traceability_matrix","cam.pat.stakeholder_map",
    "cam.pat.assumptions_log","cam.pat.constraints_log","cam.pat.value_stream_map",
    # 2.3 DAM
    "cam.dam.raci","cam.dam.crud","cam.dam.dependency_matrix","cam.dam.coupling_matrix","cam.dam.quality_attribute_scenarios",
    # 2.4 Contracts
    "cam.contract.api","cam.contract.event","cam.contract.schema","cam.contract.service",
    # 2.5 Capability & Domain Models
    "cam.model.capability","cam.model.domain","cam.catalog.service",
    # 2.6 Workflows & Orchestration
    "cam.workflow.process","cam.workflow.state_machine","cam.workflow.saga","cam.workflow.batch_job","cam.workflow.pipeline",
    # 2.7 Security & Compliance
    "cam.security.policy","cam.security.threat_model","cam.security.trust_boundary","cam.security.control_matrix",
    # 2.8 Data & Information Architecture
    "cam.data.model","cam.data.lineage","cam.data.retention_policy","cam.data.dictionary","cam.data.privacy_matrix",
    # 2.9 Infrastructure & Deployment
    "cam.infra.topology","cam.infra.environment","cam.infra.k8s_manifest","cam.infra.network_policy",
    "cam.infra.scaling_policy","cam.infra.backup_restore",
    # 2.10 Observability & SLOs
    "cam.obs.metrics_catalog","cam.obs.logging_plan","cam.obs.tracing_map","cam.obs.dashboard",
    "cam.obs.slo_objectives","cam.obs.alerting_policy",
    # 2.11 Governance & Decisions
    "cam.gov.adr.index","cam.gov.adr.record","cam.gov.standards","cam.gov.compliance_matrix",
    # 2.12 Risk Management
    "cam.risk.register","cam.risk.matrix","cam.risk.mitigation_plan",
    # 2.13 Operations & Runbooks
    "cam.ops.runbook","cam.ops.playbook","cam.ops.postmortem","cam.ops.oncall_roster",
    # 2.14 FinOps / Cost
    "cam.finops.cost_model","cam.finops.budget","cam.finops.usage_report","cam.finops.chargeback_policy",
    # 2.15 QA / Testing
    "cam.qa.test_plan","cam.qa.test_cases","cam.qa.coverage_matrix","cam.qa.defect_density_matrix","cam.qa.performance_report",
    # 2.16 Performance & Capacity
    "cam.perf.benchmark_report","cam.perf.capacity_plan","cam.perf.load_profile","cam.perf.tuning_guidelines",
    # 2.17 Asset & Inventory (CMDB-lite)
    "cam.asset.service_inventory","cam.asset.dependency_inventory","cam.asset.api_inventory",
]

ALIASES = {
    "cam.contract.api": ["ext.legacy.openapi_doc"],
    # NOTE: class diagram alias handled above on the diagram doc itself
}

# ---------------------------------------------------------------------------
# Per-family schema & recipes (minimal, relaxed, Astra-compatible)
# ---------------------------------------------------------------------------
docs: List[Dict[str, Any]] = []
docs.extend(diagram_docs)  # ← add the new diagram kinds first

# ---- PAT -------------------------------------------------------------------
# moscow_prioritization
docs.append(make_kind_doc(
    _id="cam.pat.moscow_prioritization",
    title="MoSCoW Prioritization",
    category="pat",
    json_schema=obj({
        "items": arr(obj({
            "id": {"type": "string"},
            "title": {"type": "string"},
            "priority": str_enum(["must","should","could","won't"]),
            "rationale": {"type": ["string","null"]},
            "tags": arr({"type": "string"})
        }))
    }),
    prompt_system="Produce a MoSCoW backlog with clear priorities and concise rationales.",
    identity={"natural_key": ["items[*].id"]},
    diagram_recipes=[{
        "id": "pat.moscow.board",
        "title": "MoSCoW Board",
        "view": "flowchart",
        "language": "mermaid",
        "description": "Group items by priority.",
        "template": """flowchart LR
  subgraph MUST
    {% for i in (data.items or []) if i.priority == 'must' %}{{ i.id | replace('-', '_') }}[{{ i.title }}]
    {% endfor %}
  end
  subgraph SHOULD
    {% for i in (data.items or []) if i.priority == 'should' %}{{ i.id | replace('-', '_') }}[{{ i.title }}]
    {% endfor %}
  end
  subgraph COULD
    {% for i in (data.items or []) if i.priority == 'could' %}{{ i.id | replace('-', '_') }}[{{ i.title }}]
    {% endfor %}
  end
  subgraph WONT
    {% for i in (data.items or []) if i.priority == "won't" %}{{ i.id | replace('-', '_') }}[{{ i.title }}]
    {% endfor %}
  end"""
    }]
))
# requirements_traceability_matrix
docs.append(make_kind_doc(
    _id="cam.pat.requirements_traceability_matrix",
    title="Requirements Traceability Matrix",
    category="pat",
    json_schema=obj({
        "rows": arr(obj({
            "requirement_id": {"type": "string"},
            "story_keys": arr({"type": "string"}),
            "tests": arr({"type": "string"}),
            "status": str_enum(["planned","in_progress","done"])
        }))
    }),
    prompt_system="Create a concise RTM linking requirements to stories and tests."
))
# stakeholder_map
docs.append(make_kind_doc(
    _id="cam.pat.stakeholder_map",
    title="Stakeholder Map",
    category="pat",
    json_schema=obj({
        "stakeholders": arr(obj({
            "name": {"type": "string"},
            "role": {"type": ["string","null"]},
            "influence": str_enum(["low","medium","high"]),
            "interest": str_enum(["low","medium","high"])
        }))
    }),
    prompt_system="List stakeholders with influence/interest to guide engagement strategy.",
    diagram_recipes=[{
        "id": "pat.stakeholders.grid",
        "title": "Influence vs Interest",
        "view": "flowchart",
        "language": "mermaid",
        "description": "Quadrant placement by influence and interest.",
        "template": """flowchart LR
  subgraph High_Influence_High_Interest
    {% for s in (data.stakeholders or []) if s.influence=='high' and s.interest=='high' %}{{ s.name | replace(' ','_') }}[{{ s.name }}]
    {% endfor %}
  end
  subgraph High_Influence_Low_Interest
    {% for s in (data.stakeholders or []) if s.influence=='high' and s.interest=='low' %}{{ s.name | replace(' ','_') }}[{{ s.name }}]
    {% endfor %}
  end
  subgraph Low_Influence_High_Interest
    {% for s in (data.stakeholders or []) if s.influence=='low' and s.interest=='high' %}{{ s.name | replace(' ','_') }}[{{ s.name }}]
    {% endfor %}
  end
  subgraph Low_Influence_Low_Interest
    {% for s in (data.stakeholders or []) if s.influence=='low' and s.interest=='low' %}{{ s.name | replace(' ','_') }}[{{ s.name }}]
    {% endfor %}
  end"""
    }]
))
# assumptions_log
docs.append(make_kind_doc(
    _id="cam.pat.assumptions_log",
    title="Assumptions Log",
    category="pat",
    json_schema=obj({
        "entries": arr(obj({
            "id": {"type": "string"},
            "assumption": {"type": "string"},
            "validated": {"type": ["boolean","null"]},
            "impact": {"type": ["string","null"]}
        }))
    }),
    prompt_system="Maintain a clear log of assumptions with validation status and impact."
))
# constraints_log
docs.append(make_kind_doc(
    _id="cam.pat.constraints_log",
    title="Constraints Log",
    category="pat",
    json_schema=obj({
        "entries": arr(obj({
            "id": {"type": "string"},
            "constraint": {"type": "string"},
            "type": str_enum(["technical","business","regulatory"]),
            "notes": {"type": ["string","null"]}
        }))
    }),
    prompt_system="Record constraints and classify by type; keep notes succinct."
))
# value_stream_map
docs.append(make_kind_doc(
    _id="cam.pat.value_stream_map",
    title="Value Stream Map",
    category="pat",
    json_schema=obj({
        "steps": arr(obj({
            "name": {"type": "string"},
            "lead_time": {"type": ["number","string","null"]},
            "value_added": {"type": ["boolean","null"]}
        })),
        "metrics": obj({}, addl=True)
    }),
    prompt_system="Summarize value stream steps with lead times and value-added flags.",
    diagram_recipes=[{
        "id": "pat.vsm.flow",
        "title": "VSM Flow",
        "view": "flowchart",
        "language": "mermaid",
        "description": "Linear flow of steps.",
        "template": """flowchart LR
  {% for s in (data.steps or []) %}
  s{{ loop.index }}[{{ s.name }}{% if s.lead_time %}\\nLT: {{ s.lead_time }}{% endif %}]
  {% endfor %}
  {% for s in (data.steps or []) %}
    {% if not loop.last %}s{{ loop.index }} --> s{{ loop.index + 1 }}{% endif %}
  {% endfor %}"""
    }]
))

# ---- DAM -------------------------------------------------------------------
def make_matrix_doc(_id: str, title: str) -> Dict[str, Any]:
    return make_kind_doc(
        _id=_id,
        title=title,
        category="dam",
        json_schema=obj({
            "rows": arr({"type": "string"}),
            "cols": arr({"type": "string"}),
            "cells": arr(obj({"row": {"type": "string"}, "col": {"type": "string"}, "value": {}}))
        }),
        prompt_system="Emit a clear matrix with rows, columns and typed cells."
    )

docs.append(make_matrix_doc("cam.dam.raci", "RACI Matrix"))
docs.append(make_matrix_doc("cam.dam.crud", "CRUD Matrix"))
docs.append(make_matrix_doc("cam.dam.dependency_matrix", "Dependency Matrix"))
docs.append(make_matrix_doc("cam.dam.coupling_matrix", "Coupling Matrix"))
docs.append(make_matrix_doc("cam.dam.quality_attribute_scenarios", "Quality Attribute Scenarios"))

# ---- Contracts -------------------------------------------------------------
# api
docs.append(make_kind_doc(
    _id="cam.contract.api",
    title="API Contracts",
    category="contract",
    aliases=ALIASES.get("cam.contract.api"),
    json_schema=obj({
        "services": arr(obj({
            "name": {"type": "string"},
            "style": str_enum(["rest","grpc","graphql"]),
            "endpoints": arr(obj({
                "method": str_enum(["GET","POST","PUT","DELETE","PATCH","HEAD","OPTIONS"]),
                "path": {"type": "string"},
                "summary": {"type": ["string","null"]},
                "request_schema": obj({}, addl=True),
                "response_schema": obj({}, addl=True),
                "auth": obj({"required": {"type": "boolean"}, "scopes": arr({"type": "string"})})
            })),
            "openapi": {"type": ["string","null"]},
            "grpc_idl": {"type": ["string","null"]},
            "story_keys": arr({"type": "string"})
        }))
    }),
    prompt_system="Produce succinct interface contracts; keep schemas minimal but valid.",
    diagram_recipes=[{
        "id": "contract.api.service_map",
        "title": "Service → Endpoints Map",
        "view": "flowchart",
        "language": "mermaid",
        "description": "Endpoints grouped by service.",
        "template": """flowchart LR
  {% for s in (data.services or []) %}
  subgraph {{ s.name | replace(' ','_') }}[{{ s.name }}]
    {% for e in (s.endpoints or []) %}
    {{ s.name | replace(' ','_') }}_{{ loop.index }}["{{ e.method }} {{ e.path }}"]
    {% endfor %}
  end
  {% endfor %}"""
    }]
))
# event
docs.append(make_kind_doc(
    _id="cam.contract.event",
    title="Event Contracts",
    category="contract",
    json_schema=obj({
        "topics": arr(obj({
            "name": {"type": "string"},
            "schema": obj({}, addl=True),
            "retention": {"type": ["string","null"]},
            "compaction": {"type": ["boolean","null"]}
        }))
    }),
    prompt_system="Define event topics with schemas and retention/compaction policies."
))
# schema
docs.append(make_kind_doc(
    _id="cam.contract.schema",
    title="Shared Schemas",
    category="contract",
    json_schema=obj({
        "definitions": arr(obj({
            "name": {"type": "string"},
            "format": str_enum(["json_schema","avro","protobuf","xsd"]),
            "definition": obj({}, addl=True)
        }))
    }),
    prompt_system="Catalog shared data definitions with their native formats."
))
# service SLA
docs.append(make_kind_doc(
    _id="cam.contract.service",
    title="Service Contract",
    category="contract",
    json_schema=obj({
        "targets": obj({
            "availability": {"type": ["string","null"]},
            "latency_ms": {"type": ["number","null"]},
            "throughput": {"type": ["string","null"]}
        }),
        "dependencies": arr({"type": "string"}),
        "interfaces": arr({"type": "string"})
    }),
    prompt_system="Capture non-functional targets, dependencies, and interfaces for a service."
))

# ---- Models / Catalog ------------------------------------------------------
docs.append(make_kind_doc(
    _id="cam.model.capability",
    title="Capability Model",
    category="model",
    json_schema=obj({
        "capabilities": arr(obj({
            "id": {"type": ["string","null"]},
            "name": {"type": "string"},
            "level": {"type": ["integer","number","null"]},
            "parent_id": {"type": ["string","null"]}
        }))
    }),
    prompt_system="Emit a concise capability hierarchy with levels and parents.",
    diagram_recipes=[{
        "id": "model.capability.tree",
        "title": "Capability Tree",
        "view": "mindmap",
        "language": "mermaid",
        "description": "Parent → child capability breakdown.",
        "template": """mindmap
  root((Capabilities))
  {% for c in (data.capabilities or []) if not c.parent_id %}
  {{ c.name }}
    {% for cc in (data.capabilities or []) if cc.parent_id == c.id %}{{ cc.name }}
    {% endfor %}
  {% endfor %}"""
    }]
))

docs.append(make_kind_doc(
    _id="cam.model.domain",
    title="Domain Model (Glossary)",
    category="model",
    json_schema=obj({
        "glossary": arr(obj({
            "term": {"type": "string"},
            "definition": {"type": ["string","null"]},
            "synonyms": arr({"type": "string"})
        }))
    }),
    prompt_system="Produce a clean glossary of terms with concise definitions."
))

docs.append(make_kind_doc(
    _id="cam.catalog.service",
    title="Service Catalog",
    category="catalog",
    json_schema=obj({
        "services": arr(obj({
            "name": {"type": "string"},
            "owner": {"type": ["string","null"]},
            "tier": str_enum(["critical","high","medium","low"]),
            "interfaces": arr({"type": "string"})
        }))
    }),
    prompt_system="List services with owner, tier and interface identifiers."
))

# ---- Workflows -------------------------------------------------------------
docs.append(make_kind_doc(
    _id="cam.workflow.process",
    title="Workflow Process",
    category="workflow",
    json_schema=obj({
        "name": {"type": "string"},
        "type": {"type": ["string","null"]},
        "lanes": arr(obj({"id": {"type": "string"}, "label": {"type": ["string","null"]}})),
        "nodes": arr(obj({"id": {"type": "string"}, "kind": {"type": ["string","null"]}, "label": {"type": ["string","null"]}, "lane": {"type": ["string","null"]}, "refs": arr({"type":"string"})})),
        "edges": arr(obj({"from": {"type": "string"}, "to": {"type": "string"}, "condition": {"type": ["string","null"]}}))
    }),
    prompt_system="Emit a minimal process graph with nodes/edges and optional lanes.",
    diagram_recipes=[{
        "id": "process.activity",
        "title": "Process Flow",
        "view": "activity",
        "language": "mermaid",
        "description": "Flowchart rendering of nodes and edges.",
        "template": """flowchart TD
  {% for n in (data.nodes or []) %}
  {{ n.id }}([{{ n.label or n.id }}])
  {% endfor %}
  {% for e in (data.edges or []) %}
  {{ e.from }} -->{% if e.condition %}|{{ e.condition }}|{% endif %} {{ e.to }}
  {% endfor %}"""
    }]
))

docs.append(make_kind_doc(
    _id="cam.workflow.state_machine",
    title="State Machine",
    category="workflow",
    json_schema=obj({
        "states": arr(obj({"id": {"type":"string"}, "name": {"type":"string"}, "type": str_enum(["initial","normal","final"])})),
        "transitions": arr(obj({"from":{"type":"string"}, "to":{"type":"string"}, "event":{"type":["string","null"]}, "guard":{"type":["string","null"]}}))
    }),
    prompt_system="Define states and transitions with events/guards when present.",
    diagram_recipes=[{
        "id": "workflow.state.flow",
        "title": "State Flow",
        "view": "flowchart",
        "language": "mermaid",
        "description": "Simple state transition chart.",
        "template": """flowchart LR
  {% for s in (data.states or []) %}{{ s.id }}([{{ s.name }}])
  {% endfor %}
  {% for t in (data.transitions or []) %}{{ t.from }} -->{% if t.event %}|{{ t.event }}{% if t.guard %} [{{ t.guard }}]{% endif %}|{% endif %} {{ t.to }}
  {% endfor %}"""
    }]
))

docs.append(make_kind_doc(
    _id="cam.workflow.saga",
    title="Saga",
    category="workflow",
    json_schema=obj({
        "stages": arr(obj({"name":{"type":"string"}, "type": str_enum(["choreography","orchestration"])})),
        "actions": arr(obj({"name":{"type":"string"}, "compensating_action": {"type":["string","null"]}}))
    }),
    prompt_system="List saga stages and compensating actions appropriate to the style."
))

docs.append(make_kind_doc(
    _id="cam.workflow.batch_job",
    title="Batch Job",
    category="workflow",
    json_schema=obj({
        "jobs": arr(obj({"name":{"type":"string"}, "schedule":{"type":["string","null"]}, "retries":{"type":["integer","number","null"]}}))
    }),
    prompt_system="Emit batch job definitions with schedules and retries."
))

docs.append(make_kind_doc(
    _id="cam.workflow.pipeline",
    title="Pipeline",
    category="workflow",
    json_schema=obj({
        "stages": arr(obj({"name":{"type":"string"}, "type":{"type":["string","null"]}, "config": obj({}, addl=True)})),
        "artifacts": arr({"type":"string"})
    }),
    prompt_system="Define ordered pipeline stages with minimal config and artifacts."
))

# ---- Security --------------------------------------------------------------
docs.append(make_kind_doc(
    _id="cam.security.policy",
    title="Security Policy",
    category="security",
    json_schema=obj({
        "roles": arr(obj({"name":{"type":"string"}, "scopes": arr({"type":"string"})})),
        "rules": obj({}, addl=True)
    }),
    prompt_system="Summarize roles and security rules; keep scopes succinct."
))

docs.append(make_kind_doc(
    _id="cam.security.threat_model",
    title="Threat Model",
    category="security",
    json_schema=obj({
        "threats": arr(obj({
            "id":{"type":"string"},
            "title":{"type":"string"},
            "stride": arr(str_enum(["S","T","R","I","D","E"])),
            "severity": str_enum(["low","medium","high","critical"])
        }))
    }),
    prompt_system="List threats with STRIDE categories and severity."
))

docs.append(make_kind_doc(
    _id="cam.security.trust_boundary",
    title="Trust Boundary",
    category="security",
    json_schema=obj({
        "zones": arr(obj({"id":{"type":"string"}, "name":{"type":"string"}, "data_classes": arr({"type":"string"})})),
        "boundaries": arr(obj({"from":{"type":"string"}, "to":{"type":"string"}, "controls": arr({"type":"string"})}))
    }),
    prompt_system="Define zones and boundaries with controls where relevant.",
    diagram_recipes=[{
        "id": "security.boundaries.map",
        "title": "Zones & Boundaries",
        "view": "flowchart",
        "language": "mermaid",
        "description": "Shows zones and connections.",
        "template": """flowchart LR
  {% for z in (data.zones or []) %}{{ z.id }}[{{ z.name }}]
  {% endfor %}
  {% for b in (data.boundaries or []) %}{{ b.from }} -.-> {{ b.to }}
  {% endfor %}"""
    }]
))

docs.append(make_kind_doc(
    _id="cam.security.control_matrix",
    title="Security Control Matrix",
    category="security",
    json_schema=obj({
        "rows": arr(obj({"control":{"type":"string"}, "evidence":{"type":["string","null"]}, "owner":{"type":["string","null"]}, "status": str_enum(["na","planned","in_progress","complete"])}))
    }),
    prompt_system="Provide a control-to-evidence mapping with owner and status."
))

# ---- Data ------------------------------------------------------------------
docs.append(make_kind_doc(
    _id="cam.data.model",
    title="Data Model",
    category="data",
    json_schema=obj({
        "logical": arr(obj({
            "name":{"type":"string"},
            "fields": arr(obj({"name":{"type":"string"}, "type":{"type":["string","null"]}, "source_refs": arr({"type":"string"})}))
        })),
        "physical": arr(obj({
            "name":{"type":"string"},
            "type":{"type":["string","null"]},
            "columns": arr(obj({"name":{"type":"string"}, "pic_or_sqltype":{"type":["string","null"]}})),
            "source_refs": arr({"type":"string"})
        }))
    }),
    prompt_system="Map sources into logical/physical entities; do not invent fields.",
    diagram_recipes=[{
        "id": "data.er",
        "title": "Logical ER Diagram",
        "view": "er",
        "language": "mermaid",
        "description": "Render logical entities as ER diagram.",
        "template": """erDiagram
  {% for e in (data.logical or []) %}
  {{ e.name }} {
    {% for f in (e.fields or []) %}{{ (f.type or "TYPE") | replace(" ", "_") }} {{ f.name }}
    {% endfor %}
  }
  {% endfor %}"""
    }]
))

docs.append(make_kind_doc(
    _id="cam.data.lineage",
    title="Data Lineage",
    category="data",
    json_schema=obj({
        "edges": arr(obj({
            "from":{"type":"string"},
            "to":{"type":"string"},
            "op":{"type":["string","null"]},
            "evidence": arr({"type":"string"})
        }))
    }),
    prompt_system="Emit lineage edges only when supported by evidence.",
    diagram_recipes=[{
        "id": "data.lineage.graph",
        "title": "Lineage Graph",
        "view": "flowchart",
        "language": "mermaid",
        "description": "Directed edges labeled by operation.",
        "template": """flowchart LR
  {% for e in (data.edges or []) %}{{ e.from | replace('.','_') }} -->|{{ e.op or '' }}| {{ e.to | replace('.','_') }}
  {% endfor %}"""
    }]
))

docs.append(make_kind_doc(
    _id="cam.data.retention_policy",
    title="Data Retention Policy",
    category="data",
    json_schema=obj({
        "rules": arr(obj({
            "dataset":{"type":"string"},
            "retention":{"type":["string","null"]},
            "delete_after_days":{"type":["integer","number","null"]}
        }))
    }),
    prompt_system="List retention rules per dataset with durations and delete-after markers."
))

docs.append(make_kind_doc(
    _id="cam.data.dictionary",
    title="Data Dictionary",
    category="data",
    json_schema=obj({
        "terms": arr(obj({
            "name":{"type":"string"},
            "type":{"type":["string","null"]},
            "description":{"type":["string","null"]}
        }))
    }),
    prompt_system="Create business-friendly term definitions grounded in sources."
))

docs.append(make_kind_doc(
    _id="cam.data.privacy_matrix",
    title="Privacy Matrix",
    category="data",
    json_schema=obj({
        "rows": arr(obj({
            "dataset":{"type":"string"},
            "pii_class":{"type":["string","null"]},
            "handling":{"type":["string","null"]}
        }))
    }),
    prompt_system="Map datasets to privacy classes and required handling."
))

# ---- Infra -----------------------------------------------------------------
docs.append(make_kind_doc(
    _id="cam.infra.topology",
    title="Infrastructure Topology",
    category="infra",
    json_schema=obj({
        "resources": arr(obj({"id":{"type":"string"}, "type":{"type":"string"}, "name":{"type":"string"}, "labels": obj({}, addl=True)})),
        "relations": arr(obj({"from":{"type":"string"}, "to":{"type":"string"}, "kind":{"type":["string","null"]}}))
    }),
    prompt_system="List infra resources and relations; keep types/labels consistent.",
    diagram_recipes=[{
        "id": "infra.topology.graph",
        "title": "Infra Topology Graph",
        "view": "flowchart",
        "language": "mermaid",
        "description": "Graph of resources and relations.",
        "template": """flowchart LR
  {% for r in (data.resources or []) %}{{ r.id }}[{{ r.name }}:{{ r.type }}]
  {% endfor %}
  {% for l in (data.relations or []) %}{{ l.from }} --> {{ l.to }}
  {% endfor %}"""
    }]
))

docs.append(make_kind_doc(
    _id="cam.infra.environment",
    title="Environments",
    category="infra",
    json_schema=obj({
        "environments": arr(obj({"name":{"type":"string"}, "purpose":{"type":["string","null"]}, "drift_policy":{"type":["string","null"]}}))
    }),
    prompt_system="List environments with purpose and any drift policies."
))

docs.append(make_kind_doc(
    _id="cam.infra.k8s_manifest",
    title="Kubernetes Manifests",
    category="infra",
    json_schema=obj({
        "manifests": arr(obj({
            "kind":{"type":"string"},
            "apiVersion":{"type":"string"},
            "metadata": obj({}, addl=True),
            "spec": obj({}, addl=True)
        }))
    }),
    prompt_system="Catalog K8s manifests with minimal normalization; do not alter spec."
))

docs.append(make_kind_doc(
    _id="cam.infra.network_policy",
    title="Network Policies",
    category="infra",
    json_schema=obj({
        "policies": arr(obj({"name":{"type":"string"}, "namespace":{"type":["string","null"]}, "ingress": obj({}, addl=True), "egress": obj({}, addl=True)}))
    }),
    prompt_system="Summarize network policies with ingress/egress rules."
))

docs.append(make_kind_doc(
    _id="cam.infra.scaling_policy",
    title="Scaling Policies",
    category="infra",
    json_schema=obj({
        "policies": arr(obj({"target":{"type":"string"}, "metric":{"type":"string"}, "threshold":{"type":["number","string","null"]}, "min":{"type":["integer","number","null"]}, "max":{"type":["integer","number","null"]}}))
    }),
    prompt_system="Capture autoscaling policies with thresholds and bounds."
))

docs.append(make_kind_doc(
    _id="cam.infra.backup_restore",
    title="Backup & Restore Plans",
    category="infra",
    json_schema=obj({
        "plans": arr(obj({"name":{"type":"string"}, "rpo":{"type":["string","null"]}, "rto":{"type":["string","null"]}, "schedule":{"type":["string","null"]}, "targets": arr({"type":"string"})}))
    }),
    prompt_system="Document backup/restore plans with RPO/RTO and schedules."
))

# ---- Observability ---------------------------------------------------------
docs.append(make_kind_doc(
    _id="cam.obs.metrics_catalog",
    title="Metrics Catalog",
    category="obs",
    json_schema=obj({
        "metrics": arr(obj({"name":{"type":"string"}, "owner":{"type":["string","null"]}, "sli":{"type":["string","null"]}, "unit":{"type":["string","null"]}}))
    }),
    prompt_system="List key metrics with SLI and owner where applicable."
))

docs.append(make_kind_doc(
    _id="cam.obs.logging_plan",
    title="Logging Plan",
    category="obs",
    json_schema=obj({
        "events": arr(obj({"name":{"type":"string"}, "level": str_enum(["debug","info","warn","error"]), "retention_days":{"type":["integer","number","null"]}, "redact":{"type":["boolean","null"]}}))
    }),
    prompt_system="Define log events with levels, retention, and redaction flags."
))

docs.append(make_kind_doc(
    _id="cam.obs.tracing_map",
    title="Tracing Map",
    category="obs",
    json_schema=obj({
        "spans": arr(obj({"name":{"type":"string"}, "service":{"type":"string"}, "critical_path":{"type":["boolean","null"]}}))
    }),
    prompt_system="Map critical spans to services for distributed tracing."
))

docs.append(make_kind_doc(
    _id="cam.obs.dashboard",
    title="Dashboards",
    category="obs",
    json_schema=obj({
        "dashboards": arr(obj({"name":{"type":"string"}, "panels": arr({"type":"string"}), "owner":{"type":["string","null"]}}))
    }),
    prompt_system="List dashboards and key panels."
))

docs.append(make_kind_doc(
    _id="cam.obs.slo_objectives",
    title="SLO Objectives",
    category="obs",
    json_schema=obj({
        "slos": arr(obj({"service":{"type":"string"}, "sli":{"type":"string"}, "target":{"type":["number","string"]}, "window":{"type":["string","null"]}}))
    }),
    prompt_system="Define SLOs with SLI, target and window."
))

docs.append(make_kind_doc(
    _id="cam.obs.alerting_policy",
    title="Alerting Policy",
    category="obs",
    json_schema=obj({
        "alerts": arr(obj({"name":{"type":"string"}, "condition":{"type":"string"}, "threshold":{"type":["number","string","null"]}, "runbook":{"type":["string","null"]}}))
    }),
    prompt_system="List alerts with conditions, thresholds, and runbook links."
))

# ---- Governance ------------------------------------------------------------
docs.append(make_kind_doc(
    _id="cam.gov.adr.index",
    title="ADR Index",
    category="gov",
    json_schema=obj({
        "entries": arr(obj({"id":{"type":"string"}, "title":{"type":"string"}, "status": str_enum(["proposed","accepted","rejected","superseded"])}))
    }),
    prompt_system="Summarize Architectural Decision Records in a navigable index.",
    diagram_recipes=[{
        "id": "gov.adr.timeline",
        "title": "ADR Timeline",
        "view": "flowchart",
        "language": "mermaid",
        "description": "Sequence of ADRs by id.",
        "template": """flowchart LR
  {% for e in (data.entries or []) %}
  {{ e.id | replace(' ','_') }}[{{ e.id }}: {{ e.title }}]
  {% if not loop.last %}{{ e.id | replace(' ','_') }} --> {{ (data.entries[loop.index].id)|replace(' ','_') }}{% endif %}
  {% endfor %}"""
    }]
))

docs.append(make_kind_doc(
    _id="cam.gov.adr.record",
    title="ADR Record",
    category="gov",
    json_schema=obj({
        "record": obj({
            "id":{"type":"string"},
            "title":{"type":"string"},
            "context":{"type":["string","null"]},
            "decision":{"type":"string"},
            "status": str_enum(["proposed","accepted","rejected","superseded"])
        })
    }),
    prompt_system="Capture a single ADR with context and decision."
))

docs.append(make_kind_doc(
    _id="cam.gov.standards",
    title="Standards",
    category="gov",
    json_schema=obj({
        "standards": arr(obj({"name":{"type":"string"}, "category":{"type":["string","null"]}, "status": str_enum(["approved","deprecated","experimental"])}))
    }),
    prompt_system="List technical standards and their lifecycle status."
))

docs.append(make_kind_doc(
    _id="cam.gov.compliance_matrix",
    title="Compliance Matrix",
    category="gov",
    json_schema=obj({
        "rows": arr(obj({"control":{"type":"string"}, "evidence":{"type":["string","null"]}, "owner":{"type":["string","null"]}, "status": str_enum(["na","planned","in_progress","complete"])}))
    }),
    prompt_system="Map controls to evidence/owner and completion status."
))

# ---- Risk ------------------------------------------------------------------
docs.append(make_kind_doc(
    _id="cam.risk.register",
    title="Risk Register",
    category="risk",
    json_schema=obj({
        "risks": arr(obj({
            "id":{"type":"string"},
            "title":{"type":"string"},
            "probability": str_enum(["low","medium","high"]),
            "impact": str_enum(["low","medium","high"]),
            "owner":{"type":["string","null"]},
            "status":{"type":["string","null"]}
        }))
    }),
    prompt_system="List risks with probability, impact, owner and status."
))

docs.append(make_kind_doc(
    _id="cam.risk.matrix",
    title="Risk Matrix",
    category="risk",
    json_schema=obj({
        "cells": arr(obj({"prob":{"type":"string"}, "impact":{"type":"string"}, "count":{"type":["integer","number","null"]}}))
    }),
    prompt_system="Summarize counts of risks across probability/impact cells.",
    diagram_recipes=[{
        "id": "risk.matrix.grid",
        "title": "Risk Heatmap (Abstract)",
        "view": "flowchart",
        "language": "mermaid",
        "description": "Probability vs Impact grid with counts.",
        "template": """flowchart LR
  subgraph LOW_Prob
  end
  subgraph MED_Prob
  end
  subgraph HIGH_Prob
  end
  %% note: textual grouping; visualization left to renderer"""
    }]
))

docs.append(make_kind_doc(
    _id="cam.risk.mitigation_plan",
    title="Risk Mitigation Plan",
    category="risk",
    json_schema=obj({
        "steps": arr(obj({"risk_id":{"type":"string"}, "action":{"type":"string"}, "owner":{"type":["string","null"]}, "due":{"type":["string","null"]}, "status":{"type":["string","null"]}}))
    }),
    prompt_system="Provide mitigation steps per risk with owner and due date."
))

# ---- Operations ------------------------------------------------------------
docs.append(make_kind_doc(
    _id="cam.ops.runbook",
    title="Runbook",
    category="ops",
    json_schema=obj({
        "steps": arr(obj({"order":{"type":["integer","number"]}, "instruction":{"type":"string"}, "check":{"type":["string","null"]}}))
    }),
    prompt_system="Emit deterministic, numbered runbook steps."
))

docs.append(make_kind_doc(
    _id="cam.ops.playbook",
    title="Ops Playbook",
    category="ops",
    json_schema=obj({
        "scenarios": arr(obj({"name":{"type":"string"}, "triggers": arr({"type":"string"}), "actions": arr({"type":"string"})}))
    }),
    prompt_system="Outline operational scenarios with triggers and actions.",
    diagram_recipes=[{
        "id": "ops.playbook.flow",
        "title": "Playbook Flow",
        "view": "flowchart",
        "language": "mermaid",
        "description": "Trigger → actions visualization.",
        "template": """flowchart TD
  {% for s in (data.scenarios or []) %}
  subgraph {{ s.name | replace(' ','_') }}[{{ s.name }}]
    TRIGGERS{{ loop.index }}[[Triggers]]
    ACTIONS{{ loop.index }}[[Actions]]
  end
  {% for t in (s.triggers or []) %}TRIGGERS{{ loop.index0 + 1 }} --> "{{ t }}"
  {% endfor %}
  {% for a in (s.actions or []) %}ACTIONS{{ loop.index0 + 1 }} --> "{{ a }}"
  {% endfor %}
  {% endfor %}"""
    }]
))

docs.append(make_kind_doc(
    _id="cam.ops.postmortem",
    title="Postmortem",
    category="ops",
    json_schema=obj({
        "report": obj({
            "incident_id":{"type":"string"},
            "impact":{"type":["string","null"]},
            "root_cause":{"type":["string","null"]},
            "actions": arr({"type":"string"})
        })
    }),
    prompt_system="Capture concise incident postmortems with actions."
))

docs.append(make_kind_doc(
    _id="cam.ops.oncall_roster",
    title="On-Call Roster",
    category="ops",
    json_schema=obj({
        "rosters": arr(obj({"team":{"type":"string"}, "rotation":{"type":["string","null"]}, "members": arr({"type":"string"})}))
    }),
    prompt_system="List on-call rotations and members per team."
))

# ---- FinOps ----------------------------------------------------------------
docs.append(make_kind_doc(
    _id="cam.finops.cost_model",
    title="Cost Model",
    category="finops",
    json_schema=obj({
        "drivers": arr(obj({"name":{"type":"string"}, "metric":{"type":"string"}, "weight":{"type":["number","string","null"]}}))
    }),
    prompt_system="Define cost drivers with metrics and optional weights."
))

docs.append(make_kind_doc(
    _id="cam.finops.budget",
    title="Budget",
    category="finops",
    json_schema=obj({
        "budgets": arr(obj({"period":{"type":"string"}, "amount":{"type":["number","string"]}, "owner":{"type":["string","null"]}}))
    }),
    prompt_system="List budgets with period, amount and owner."
))

docs.append(make_kind_doc(
    _id="cam.finops.usage_report",
    title="Usage Report",
    category="finops",
    json_schema=obj({
        "records": arr(obj({"period":{"type":"string"}, "service":{"type":"string"}, "usage":{"type":["number","string","null"]}, "cost":{"type":["number","string","null"]}}))
    }),
    prompt_system="Summarize usage/cost per service and period."
))

docs.append(make_kind_doc(
    _id="cam.finops.chargeback_policy",
    title="Chargeback Policy",
    category="finops",
    json_schema=obj({
        "policies": arr(obj({"rule":{"type":"string"}, "allocation":{"type":["string","null"]}}))
    }),
    prompt_system="Define chargeback allocation rules succinctly."
))

# ---- QA --------------------------------------------------------------------
docs.append(make_kind_doc(
    _id="cam.qa.test_plan",
    title="Test Plan",
    category="qa",
    json_schema=obj({
        "plan": obj({"name":{"type":"string"}, "scope":{"type":["string","null"]}, "strategy":{"type":["string","null"]}})
    }),
    prompt_system="Produce a lean test plan with scope and strategy."
))

docs.append(make_kind_doc(
    _id="cam.qa.test_cases",
    title="Test Cases",
    category="qa",
    json_schema=obj({
        "cases": arr(obj({"id":{"type":"string"}, "title":{"type":"string"}, "steps": arr({"type":"string"}), "expected":{"type":["string","null"]}}))
    }),
    prompt_system="List atomic test cases with concise steps and expected outcome."
))

docs.append(make_kind_doc(
    _id="cam.qa.coverage_matrix",
    title="Coverage Matrix",
    category="qa",
    json_schema=obj({
        "cells": arr(obj({"component":{"type":"string"}, "area":{"type":"string"}, "coverage":{"type":["number","string","null"]}}))
    }),
    prompt_system="Summarize coverage by component/area with numeric or qualitative values."
))

docs.append(make_kind_doc(
    _id="cam.qa.defect_density_matrix",
    title="Defect Density Matrix",
    category="qa",
    json_schema=obj({
        "rows": arr(obj({"component":{"type":"string"}, "loc":{"type":["integer","number","null"]}, "defects":{"type":["integer","number","null"]}}))
    }),
    prompt_system="Report defects vs LOC per component to estimate defect density."
))

docs.append(make_kind_doc(
    _id="cam.qa.performance_report",
    title="Performance Report",
    category="qa",
    json_schema=obj({
        "metrics": arr(obj({"metric":{"type":"string"}, "value":{"type":["number","string"]}, "unit":{"type":["string","null"]}}))
    }),
    prompt_system="Publish key performance metrics with units."
))

# ---- Performance -----------------------------------------------------------
docs.append(make_kind_doc(
    _id="cam.perf.benchmark_report",
    title="Benchmark Report",
    category="perf",
    json_schema=obj({
        "runs": arr(obj({"name":{"type":"string"}, "scenario":{"type":["string","null"]}, "results": obj({}, addl=True)}))
    }),
    prompt_system="List benchmark runs with scenario and result map."
))

docs.append(make_kind_doc(
    _id="cam.perf.capacity_plan",
    title="Capacity Plan",
    category="perf",
    json_schema=obj({
        "entries": arr(obj({"resource":{"type":"string"}, "current":{"type":["number","string","null"]}, "forecast":{"type":["number","string","null"]}}))
    }),
    prompt_system="Forecast capacity with current vs projected numbers."
))

docs.append(make_kind_doc(
    _id="cam.perf.load_profile",
    title="Load Profile",
    category="perf",
    json_schema=obj({
        "series": arr(obj({"timestamp":{"type":"string"}, "load":{"type":["number","string"]}}))
    }),
    prompt_system="Emit time-series load points with timestamps."
))

docs.append(make_kind_doc(
    _id="cam.perf.tuning_guidelines",
    title="Tuning Guidelines",
    category="perf",
    json_schema=obj({
        "guidelines": arr(obj({"area":{"type":"string"}, "recommendation":{"type":"string"}}))
    }),
    prompt_system="Provide actionable tuning recommendations per area."
))

# ---- Asset / Inventory -----------------------------------------------------
docs.append(make_kind_doc(
    _id="cam.asset.service_inventory",
    title="Service/Asset Inventory",
    category="asset",
    json_schema=obj({
        "programs": arr({"type":"string"}),
        "jobs": arr({"type":"string"}),
        "datasets": arr({"type":"string"}),
        "transactions": arr({"type":"string"})
    }),
    prompt_system="Aggregate identifiers from upstream facts into a single inventory.",
    diagram_recipes=[{
        "id": "asset.inventory.map",
        "title": "Inventory Mindmap",
        "view": "mindmap",
        "language": "mermaid",
        "description": "Programs, Jobs, Datasets, Transactions grouped.",
        "template": """mindmap
  root((Inventory))
    Programs
      {% for p in (data.programs or []) %}{{ p }}
      {% endfor %}
    Jobs
      {% for j in (data.jobs or []) %}{{ j }}
      {% endfor %}
    Datasets
      {% for d in (data.datasets or []) %}{{ d }}
      {% endfor %}
    Transactions
      {% for t in (data.transactions or []) %}{{ t }}
      {% endfor %}"""
    }]
))

docs.append(make_kind_doc(
    _id="cam.asset.dependency_inventory",
    title="Dependency Inventory",
    category="asset",
    json_schema=obj({
        "call_graph": arr(obj({"from":{"type":"string"}, "to":{"type":"string"}, "dynamic":{"type":["boolean","string","null"]}})),
        "job_flow": arr(obj({"job":{"type":"string"}, "step":{"type":"string"}, "seq":{"type":["integer","number","string","null"]}, "program":{"type":["string","null"]}})),
        "dataset_deps": arr(obj({"producer":{"type":"string"}, "dataset":{"type":"string"}, "consumer":{"type":"string"}}))
    }),
    prompt_system="List call edges, job flow, and dataset producer/consumer relations.",
    diagram_recipes=[{
        "id": "asset.deps.graph",
        "title": "Dependencies Graph",
        "view": "flowchart",
        "language": "mermaid",
        "description": "Mixed graph for program calls and job flows.",
        "template": """flowchart LR
  %% Program call graph
  {% for e in (data.call_graph or []) %}{{ e.from | replace('-','_') }} --> {{ e.to | replace('-','_') }}
  {% endfor %}
  %% Job flow
  {% for e in (data.job_flow or [])|sort(attribute='seq') %}
  {{ (e.step or 'STEP') | replace('-','_') }}_{{ loop.index }}["{{ e.job }}::{{ e.step }}\\n{{ e.program or '' }}"]
  {% endfor %}
  {% for e in (data.job_flow or [])|sort(attribute='seq') %}
    {% if not loop.last %}{{ (data.job_flow[loop.index0].step or 'S') | replace('-','_') }}_{{ loop.index0 + 1 }} --> {{ (data.job_flow[loop.index0+1].step or 'S') | replace('-','_') }}_{{ loop.index0 + 2 }}{% endif %}
  {% endfor %}"""
    }]
))

docs.append(make_kind_doc(
    _id="cam.asset.api_inventory",
    title="API Inventory",
    category="asset",
    json_schema=obj({
        "endpoints": arr(obj({"service":{"type":"string"}, "method":{"type":"string"}, "path":{"type":"string"}}))
    }),
    prompt_system="Aggregate API endpoints across services into a flat inventory."
))

# ---------------------------------------------------------------------------
# Seeder
# ---------------------------------------------------------------------------
def seed_registry_raina() -> None:
    for doc in docs:
        upsert_kind(doc)

if __name__ == "__main__":
    seed_registry_raina()
    print(f"Seeded {len(docs)} kinds into registry.")
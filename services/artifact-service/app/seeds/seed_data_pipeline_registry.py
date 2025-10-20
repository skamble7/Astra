# services/artifact-service/app/seeds/seed_data_pipeline_registry.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from app.dal.kind_registry_dal import upsert_kind

LATEST = "1.0.0"

DEFAULT_NARRATIVES_SPEC: Dict[str, Any] = {
    "allowed_formats": ["markdown", "asciidoc"],
    "default_format": "markdown",
    "max_length_chars": 20000,
    "allowed_locales": ["en-US"],
}

KIND_DOCS: List[Dict[str, Any]] = [
    {
        "_id": "cam.data.model_logical",
        "title": "Logical Data Model",
        "category": "data",
        "aliases": ["cam.data.model"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["domain", "entities"],
                    "properties": {
                        "domain": {"type": "string"},
                        "entities": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["name", "attributes"],
                                "properties": {
                                    "name": {"type": "string"},
                                    "attributes": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "additionalProperties": False,
                                            "required": ["name", "type"],
                                            "properties": {
                                                "name": {"type": "string"},
                                                "type": {"type": "string"},
                                                "nullable": {
                                                    "type": "boolean",
                                                    "default": True,
                                                },
                                                "pii": {
                                                    "type": "boolean",
                                                    "default": False,
                                                },
                                                "description": {"type": "string"},
                                            },
                                        },
                                    },
                                    "keys": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "properties": {
                                            "primary": {
                                                "type": "array",
                                                "items": {"type": "string"},
                                                "default": [],
                                            },
                                            "unique": {
                                                "type": "array",
                                                "items": {"type": "string"},
                                                "default": [],
                                            },
                                        },
                                    },
                                },
                            },
                        },
                        "relationships": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["from", "to", "type"],
                                "properties": {
                                    "from": {"type": "string"},
                                    "to": {"type": "string"},
                                    "type": {
                                        "type": "string",
                                        "enum": ["1-1", "1-n", "n-n"],
                                    },
                                    "via": {"type": "string"},
                                    "description": {"type": "string"},
                                },
                            },
                            "default": [],
                        },
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": ("Produce a strict JSON Logical Data Model (entities, attributes, keys, relationships) that conforms exactly to the JSON Schema. Use the provided `cam.inputs.raina` artifact (inputs.avc / inputs.fss / inputs.pss, plus goals, non-functionals, constraints, assumptions, and context) as the single source of truth. Do not include any keys that are not defined in the schema (AdditionalProperties=false). Prefer entities and attributes that map directly to FSS stories and AVC domain language. Deduplicate entities; choose stable primary keys; mark PII thoughtfully. Emit JSON only."),
                    "user_template": "{context}",
                    "variants": [],
                    "io_hints": None,
                    "strict_json": True,
                    "prompt_rev": 2,
                },
                "diagram_recipes": [
                    {
                        "id": "data.er",
                        "title": "Entity-Relationship Diagram",
                        "view": "er",
                        "language": "mermaid",
                        "description": "Render entities with attributes and relationships.",
                        "template": "erDiagram\n%% iterate entities/relationships to render",
                        "prompt": None,
                        "renderer_hints": {"direction": "LR"},
                        "examples": [],
                        "depends_on": None,
                    }
                ],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
                "identity": {
                    "natural_key": ["domain"],
                    "summary_rule": None,
                    "category": "data",
                },
                "adapters": [],
                "migrators": [],
                "examples": [
                    {
                        "domain": "cards",
                        "entities": [
                            {
                                "name": "Card",
                                "attributes": [
                                    {
                                        "name": "card_id",
                                        "type": "string",
                                        "nullable": False,
                                    },
                                    {"name": "status", "type": "string"},
                                ],
                                "keys": {"primary": ["card_id"], "unique": []},
                            }
                        ],
                        "relationships": [],
                    }
                ],
                "depends_on": {
                    "hard": ["cam.inputs.raina"],
                    "soft": ["cam.architecture.pipeline_patterns"],
                    "context_hint": "Ground entities in FSS stories and AVC context.",
                },
            }
        ],
    },
    {
        "_id": "cam.flow.business_flow_catalog",
        "title": "Business Flow Catalog",
        "category": "workflow",
        "aliases": ["cam.workflow.business_flows"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["flows"],
                    "properties": {
                        "flows": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": [
                                    "name",
                                    "actors",
                                    "steps",
                                    "datasets_touched",
                                ],
                                "properties": {
                                    "name": {"type": "string"},
                                    "actors": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "steps": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "datasets_touched": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                },
                            },
                        }
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": ("Use ONLY the data from the `cam.inputs.raina` artifact (inputs.avc / inputs.fss / inputs.pss). Do not expect any 'request' or external graph state. Extract key business flows and emit strict JSON conforming to the schema. Read the appended section '=== RUN INPUTS (authoritative, from inputs) ===' and use AVC/FSS/PSS, FR/NFR as the basis for flows, actors, steps, and datasets_touched. Do not invent properties not in the schema; AdditionalProperties=false. Map steps to datasets using the Logical Data Model when possible. Emit JSON only."),
                    "user_template": "{context}",
                    "variants": [],
                    "io_hints": None,
                    "strict_json": True,
                    "prompt_rev": 2,
                },
                "diagram_recipes": [
                    {
                        "id": "flows.activity",
                        "title": "Business Activity",
                        "view": "activity",
                        "language": "mermaid",
                        "description": "High-level business flows",
                        "template": "stateDiagram-v2\n%% steps per flow",
                        "prompt": None,
                        "renderer_hints": None,
                        "examples": [],
                        "depends_on": None,
                    },
                    {
                        "id": "flows.sequence",
                        "title": "Flow Sequence",
                        "view": "sequence",
                        "language": "mermaid",
                        "description": "Actor interactions",
                        "template": "sequenceDiagram\n%% actors & steps",
                        "prompt": None,
                        "renderer_hints": None,
                        "examples": [],
                        "depends_on": None,
                    },
                ],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
                "identity": {
                    "natural_key": ["flows.name"],
                    "summary_rule": None,
                    "category": "workflow",
                },
                "adapters": [],
                "migrators": [],
                "examples": [
                    {
                        "flows": [
                            {
                                "name": "Card Activation",
                                "actors": ["Customer", "BackOffice"],
                                "steps": ["Submit Request", "Verify KYC", "Activate"],
                                "datasets_touched": ["customers", "cards"],
                            }
                        ]
                    }
                ],
                "depends_on": {
                    "hard": ["cam.inputs.raina", "cam.data.model_logical"],
                    "soft": [],
                    "context_hint": "Use FSS stories to enumerate flows.",
                },
            }
        ],
    },
    {
        "_id": "cam.architecture.pipeline_patterns",
        "title": "Pipeline Architecture Patterns",
        "category": "architecture",
        "aliases": ["cam.patterns.pipeline"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["selected", "alternatives", "rationale"],
                    "properties": {
                        "selected": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": [
                                    "batch",
                                    "stream",
                                    "lambda",
                                    "microservices",
                                    "event_driven",
                                ],
                            },
                        },
                        "alternatives": {"type": "array", "items": {"type": "string"}},
                        "rationale": {"type": "string"},
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": ("Use ONLY the data from the `cam.inputs.raina` artifact (inputs.avc / inputs.fss / inputs.pss). Do not expect any 'request' or external graph state. Pick and justify data pipeline patterns strictly per the schema. Use the appended '=== RUN INPUTS (authoritative, from inputs) ===' (AVC/FSS/PSS, FR/NFR) to decide. Be explicit about why selected vs alternatives, aligning to latency, throughput, availability, privacy, and ops constraints. Do not emit properties not defined by the schema. Emit JSON only."),
                    "user_template": "{context}",
                    "variants": [],
                    "io_hints": None,
                    "strict_json": True,
                    "prompt_rev": 2,
                },
                "diagram_recipes": [
                    {
                        "id": "patterns.mindmap",
                        "title": "Patterns Mindmap",
                        "view": "mindmap",
                        "language": "mermaid",
                        "description": "Visualize pattern choices",
                        "template": "mindmap\n  root((Pipeline Patterns))\n  %% selected/alternatives",
                        "prompt": None,
                        "renderer_hints": None,
                        "examples": [],
                        "depends_on": None,
                    }
                ],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
                "identity": {
                    "natural_key": ["selected"],
                    "summary_rule": None,
                    "category": "architecture",
                },
                "adapters": [],
                "migrators": [],
                "examples": [
                    {
                        "selected": ["stream", "batch"],
                        "alternatives": ["lambda"],
                        "rationale": "Alerts in real-time + daily analytics.",
                    }
                ],
                "depends_on": {
                    "hard": ["cam.inputs.raina"],
                    "soft": [],
                    "context_hint": "Base selection on FR/NFR and PSS style.",
                },
            }
        ],
    },
    {
        "_id": "cam.data.dataset_contract",
        "title": "Dataset Contract",
        "category": "data",
        "aliases": [],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "system",
                        "domain",
                        "name",
                        "version",
                        "schema",
                        "ownership",
                    ],
                    "properties": {
                        "system": {"type": "string"},
                        "domain": {"type": "string"},
                        "name": {"type": "string"},
                        "version": {"type": "string"},
                        "description": {"type": "string"},
                        "schema": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["name", "type"],
                                "properties": {
                                    "name": {"type": "string"},
                                    "type": {"type": "string"},
                                    "nullable": {"type": "boolean", "default": True},
                                    "description": {"type": "string"},
                                    "pii": {"type": "boolean", "default": False},
                                    "constraints": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "default": [],
                                    },
                                },
                            },
                        },
                        "keys": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "primary": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "default": [],
                                },
                                "unique": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "default": [],
                                },
                                "foreign": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "required": [
                                            "fields",
                                            "ref_dataset",
                                            "ref_fields",
                                        ],
                                        "properties": {
                                            "fields": {
                                                "type": "array",
                                                "items": {"type": "string"},
                                            },
                                            "ref_dataset": {"type": "string"},
                                            "ref_fields": {
                                                "type": "array",
                                                "items": {"type": "string"},
                                            },
                                        },
                                    },
                                    "default": [],
                                },
                            },
                        },
                        "classification": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": [],
                        },
                        "ownership": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["product_owner", "tech_owner"],
                            "properties": {
                                "product_owner": {"type": "string"},
                                "tech_owner": {"type": "string"},
                                "stewards": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "default": [],
                                },
                            },
                        },
                        "quality_rules": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["id", "rule", "target"],
                                "properties": {
                                    "id": {"type": "string"},
                                    "rule": {"type": "string"},
                                    "target": {"type": "string"},
                                    "severity": {
                                        "type": "string",
                                        "enum": ["info", "warn", "error"],
                                        "default": "warn",
                                    },
                                },
                            },
                            "default": [],
                        },
                        "retention": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "mode": {"type": "string"},
                                "value": {"type": "string"},
                            },
                        },
                        "sample_records": {
                            "type": "array",
                            "items": {"type": "object", "additionalProperties": True},
                            "default": [],
                        },
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": ("Use ONLY the data from the `cam.inputs.raina` artifact (inputs.avc / inputs.fss / inputs.pss). Do not expect any 'request' or external graph state. Generate a strictly-typed Dataset Contract that conforms exactly to the JSON Schema. Read the appended '=== RUN INPUTS (authoritative, from inputs) ===' and base your design on AVC/FSS/PSS, goals, and NFRs. Use the 'schema' array for columns; DO NOT use an 'attributes' key anywhere. Keep key definitions ONLY in the top-level 'keys' object (primary/unique/foreign); DO NOT add 'keys' at the column level. Respect AdditionalProperties=false: do not emit any properties not defined by the schema. Emit JSON only."),
                    "user_template": "{context}",
                    "variants": [],
                    "io_hints": None,
                    "strict_json": True,
                    "prompt_rev": 2,
                },
                "diagram_recipes": [],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
                "identity": {
                    "natural_key": ["system", "domain", "name", "version"],
                    "summary_rule": None,
                    "category": "data",
                },
                "adapters": [],
                "migrators": [],
                "examples": [
                    {
                        "system": "analytics",
                        "domain": "cards",
                        "name": "transactions_curated",
                        "version": "1.0.0",
                        "description": "Curated card transactions",
                        "schema": [
                            {"name": "txn_id", "type": "string", "nullable": False},
                            {"name": "card_id", "type": "string"},
                            {"name": "amount", "type": "decimal(18,2)"},
                            {"name": "event_time", "type": "timestamp"},
                        ],
                        "keys": {"primary": ["txn_id"], "unique": [], "foreign": []},
                        "classification": ["financial"],
                        "ownership": {
                            "product_owner": "Payments PO",
                            "tech_owner": "Data Eng Lead",
                            "stewards": ["DQ Team"],
                        },
                        "quality_rules": [
                            {
                                "id": "Q1",
                                "rule": "amount >= 0",
                                "target": "100% rows",
                                "severity": "error",
                            }
                        ],
                        "retention": {"mode": "time", "value": "365d"},
                        "sample_records": [],
                    }
                ],
                "depends_on": {
                    "hard": ["cam.inputs.raina"],
                    "soft": [
                        "cam.data.model_logical",
                        "cam.architecture.pipeline_patterns",
                    ],
                    "context_hint": "Use `inputs` from graph state for FR/NFR and stories→datasets mapping.",
                },
            }
        ],
    },
    {
        "_id": "cam.workflow.data_pipeline_architecture",
        "title": "Data Pipeline Architecture",
        "category": "workflow",
        "aliases": ["cam.workflow.pipeline_architecture"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["patterns", "stages", "idempotency", "sla"],
                    "properties": {
                        "patterns": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": [
                                    "batch",
                                    "stream",
                                    "lambda",
                                    "microservices",
                                    "event_driven",
                                ],
                            },
                        },
                        "stages": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["name", "kind", "inputs", "outputs"],
                                "properties": {
                                    "name": {"type": "string"},
                                    "kind": {
                                        "type": "string",
                                        "enum": [
                                            "ingest",
                                            "transform",
                                            "enrich",
                                            "validate",
                                            "persist",
                                            "serve",
                                        ],
                                    },
                                    "tooling": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "default": [],
                                    },
                                    "inputs": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "outputs": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "compute": {
                                        "type": "string",
                                        "enum": ["batch", "stream", "mixed"],
                                        "default": "batch",
                                    },
                                    "windowing": {"type": ["string", "null"]},
                                    "exactly_once": {
                                        "type": "boolean",
                                        "default": False,
                                    },
                                },
                            },
                        },
                        "routing": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["from", "to", "condition"],
                                "properties": {
                                    "from": {"type": "string"},
                                    "to": {"type": "string"},
                                    "condition": {"type": "string"},
                                },
                            },
                            "default": [],
                        },
                        "idempotency": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["strategy"],
                            "properties": {
                                "strategy": {
                                    "type": "string",
                                    "enum": [
                                        "keys",
                                        "dedupe_table",
                                        "watermarks",
                                        "transactions",
                                    ],
                                    "default": "keys",
                                },
                                "keys": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "default": [],
                                },
                            },
                        },
                        "sla": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["freshness", "latency_p95", "availability"],
                            "properties": {
                                "freshness": {"type": "string"},
                                "latency_p95": {"type": "string"},
                                "availability": {"type": "string"},
                            },
                        },
                        "stack_recommendations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["rank", "stack"],
                                "properties": {
                                    "rank": {"type": "integer"},
                                    "stack": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "rationale": {"type": "string"},
                                },
                            },
                            "default": [],
                        },
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": ("Use ONLY the data from the `cam.inputs.raina` artifact (inputs.avc / inputs.fss / inputs.pss). Do not expect any 'request' or external graph state.Emit strict JSON pipeline architecture conforming to the schema: patterns, stages, routing, idempotency, SLAs, and ranked tech-stack recommendations. Read and base your design on the appended '=== RUN INPUTS (authoritative, from inputs) ===' (AVC/FSS/PSS, goals, NFRs, constraints). Align stages and routing to latency/freshness/availability requirements; choose stack consistent with constraints. Do not add properties outside the schema. Emit JSON only."),
                    "user_template": "{context}",
                    "variants": [],
                    "io_hints": None,
                    "strict_json": True,
                    "prompt_rev": 2,
                },
                "diagram_recipes": [
                    {
                        "id": "pipeline.flow",
                        "title": "Pipeline Flow",
                        "view": "flowchart",
                        "language": "mermaid",
                        "description": "Stages and routes",
                        "template": "flowchart LR\n%% stages & routing",
                        "prompt": None,
                        "renderer_hints": {"direction": "LR"},
                        "examples": [],
                        "depends_on": None,
                    },
                    {
                        "id": "pipeline.activity",
                        "title": "Processing Activity",
                        "view": "activity",
                        "language": "mermaid",
                        "description": "Processing steps",
                        "template": "stateDiagram-v2\n%% states per stage",
                        "prompt": None,
                        "renderer_hints": None,
                        "examples": [],
                        "depends_on": None,
                    },
                ],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
                "identity": {
                    "natural_key": [
                        "patterns",
                        "sla.freshness",
                        "sla.latency_p95",
                        "sla.availability",
                    ],
                    "summary_rule": None,
                    "category": "workflow",
                },
                "adapters": [],
                "migrators": [],
                "examples": [
                    {
                        "patterns": ["stream", "batch"],
                        "stages": [
                            {
                                "name": "ingest_kafka",
                                "kind": "ingest",
                                "tooling": ["Kafka Connect"],
                                "inputs": ["card_swipes"],
                                "outputs": ["raw_swipes"],
                                "compute": "stream",
                                "windowing": None,
                                "exactly_once": False,
                            },
                            {
                                "name": "transform_spark",
                                "kind": "transform",
                                "tooling": ["Spark"],
                                "inputs": ["raw_swipes"],
                                "outputs": ["curated_swipes"],
                                "compute": "batch",
                                "windowing": None,
                                "exactly_once": True,
                            },
                        ],
                        "routing": [
                            {
                                "from": "ingest_kafka",
                                "to": "transform_spark",
                                "condition": "always",
                            }
                        ],
                        "idempotency": {"strategy": "keys", "keys": ["txn_id"]},
                        "sla": {
                            "freshness": "1h",
                            "latency_p95": "<10m",
                            "availability": "99.9%",
                        },
                        "stack_recommendations": [
                            {
                                "rank": 1,
                                "stack": [
                                    "Kafka",
                                    "Spark",
                                    "Delta Lake",
                                    "Airflow",
                                    "dbt",
                                    "Great Expectations",
                                    "Prometheus/Grafana",
                                ],
                                "rationale": "Mature batch+stream ecosystem",
                            }
                        ],
                    }
                ],
                "depends_on": {
                    "hard": ["cam.inputs.raina", "cam.data.model_logical",
                        "cam.data.dataset_contract",
                        "cam.architecture.pipeline_patterns",],
                    "soft": ["cam.deployment.data_platform_topology"],
                    "context_hint": "Derive from flows, entities, and NFRs.",
                },
            }
        ],
    },
    {
        "_id": "cam.workflow.batch_job_spec",
        "title": "Batch Job Spec",
        "category": "workflow",
        "aliases": [],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "name",
                        "schedule",
                        "inputs",
                        "outputs",
                        "steps",
                        "retries",
                    ],
                    "properties": {
                        "name": {"type": "string"},
                        "schedule": {"type": "string"},
                        "inputs": {"type": "array", "items": {"type": "string"}},
                        "outputs": {"type": "array", "items": {"type": "string"}},
                        "steps": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["name", "type"],
                                "properties": {
                                    "name": {"type": "string"},
                                    "type": {
                                        "type": "string",
                                        "enum": [
                                            "extract",
                                            "transform",
                                            "load",
                                            "validate",
                                        ],
                                    },
                                    "tool": {"type": ["string", "null"]},
                                    "args": {
                                        "type": "object",
                                        "additionalProperties": True,
                                        "default": {},
                                    },
                                },
                            },
                        },
                        "retries": {"type": "integer", "minimum": 0, "default": 2},
                        "timeout": {"type": "string"},
                        "idempotent": {"type": "boolean", "default": True},
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": ("Use ONLY the data from the `cam.inputs.raina` artifact (inputs.avc / inputs.fss / inputs.pss). Do not expect any 'request' or external graph state. Create a strict JSON Batch Job Spec from AVC/FSS/PSS, FR/NFR found in the appended '=== RUN INPUTS (authoritative, from inputs) ==='. Map stories to batch steps, set schedules to meet freshness/latency SLAs, and ensure idempotency. Do not include any properties not defined in the schema. Emit JSON only."),
                    "user_template": "{context}",
                    "variants": [],
                    "io_hints": None,
                    "strict_json": True,
                    "prompt_rev": 2,
                },
                "diagram_recipes": [
                    {
                        "id": "batch.gantt",
                        "title": "Batch Gantt",
                        "view": "gantt",
                        "language": "mermaid",
                        "description": "Timeline of batch steps",
                        "template": "gantt\n%% steps→timeline",
                        "prompt": None,
                        "renderer_hints": None,
                        "examples": [],
                        "depends_on": None,
                    }
                ],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
                "identity": {
                    "natural_key": ["name", "schedule"],
                    "summary_rule": None,
                    "category": "workflow",
                },
                "adapters": [],
                "migrators": [],
                "examples": [
                    {
                        "name": "daily_curate",
                        "schedule": "0 2 * * *",
                        "inputs": ["raw_swipes"],
                        "outputs": ["curated_swipes"],
                        "steps": [
                            {
                                "name": "validate",
                                "type": "validate",
                                "tool": "Great Expectations",
                                "args": {},
                            }
                        ],
                        "retries": 2,
                        "timeout": "1h",
                        "idempotent": True,
                    }
                ],
                "depends_on": {
                    "hard": ["cam.inputs.raina", "cam.workflow.data_pipeline_architecture"],
                    "soft": ["cam.data.dataset_contract"],
                    "context_hint": "Adhere to pipeline SLAs and dataset contracts.",
                },
            }
        ],
    },
    {
        "_id": "cam.workflow.stream_job_spec",
        "title": "Stream Job Spec",
        "category": "workflow",
        "aliases": [],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "name",
                        "sources",
                        "sinks",
                        "processing",
                        "exactly_once",
                    ],
                    "properties": {
                        "name": {"type": "string"},
                        "sources": {"type": "array", "items": {"type": "string"}},
                        "sinks": {"type": "array", "items": {"type": "string"}},
                        "processing": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["ops"],
                            "properties": {
                                "ops": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "required": ["op"],
                                        "properties": {
                                            "op": {
                                                "type": "string",
                                                "enum": [
                                                    "map",
                                                    "filter",
                                                    "join",
                                                    "aggregate",
                                                    "window",
                                                ],
                                            },
                                            "args": {
                                                "type": "object",
                                                "additionalProperties": True,
                                                "default": {},
                                            },
                                        },
                                    },
                                },
                                "window": {"type": ["string", "null"]},
                            },
                        },
                        "exactly_once": {"type": "boolean", "default": False},
                        "latency_budget": {"type": "string"},
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": ("Use ONLY the data from the `cam.inputs.raina` artifact (inputs.avc / inputs.fss / inputs.pss). Do not expect any 'request' or external graph state. Generate a strict JSON Stream Job Spec using the appended '=== RUN INPUTS (authoritative, from inputs) ===' (AVC/FSS/PSS). Define sources, sinks, and a minimal sequence of ops (map/filter/join/aggregate/window) with windowing and exactly-once if NFRs require. Do not add properties outside the schema. Emit JSON only."),
                    "user_template": "{context}",
                    "variants": [],
                    "io_hints": None,
                    "strict_json": True,
                    "prompt_rev": 2,
                },
                "diagram_recipes": [
                    {
                        "id": "stream.sequence",
                        "title": "Stream Processing Sequence",
                        "view": "sequence",
                        "language": "mermaid",
                        "description": "Streaming ops sequence",
                        "template": "sequenceDiagram\n%% ops→sequence",
                        "prompt": None,
                        "renderer_hints": None,
                        "examples": [],
                        "depends_on": None,
                    }
                ],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
                "identity": {
                    "natural_key": ["name"],
                    "summary_rule": None,
                    "category": "workflow",
                },
                "adapters": [],
                "migrators": [],
                "examples": [
                    {
                        "name": "fraud_stream",
                        "sources": ["swipes_topic"],
                        "sinks": ["alerts_topic"],
                        "processing": {
                            "ops": [
                                {"op": "filter", "args": {"expr": "amount>5000"}},
                                {
                                    "op": "aggregate",
                                    "args": {"key": "card_id", "window": "5m"},
                                },
                            ],
                            "window": "5m",
                        },
                        "exactly_once": True,
                        "latency_budget": "<1m",
                    }
                ],
                "depends_on": {
                    "hard": ["cam.inputs.raina", "cam.workflow.data_pipeline_architecture"],
                    "soft": ["cam.data.dataset_contract"],
                    "context_hint": "Follow stream SLAs and idempotency requirements.",
                },
            }
        ],
    },
    {
        "_id": "cam.workflow.transform_spec",
        "title": "Data Transformations Spec",
        "category": "workflow",
        "aliases": [],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["transforms"],
                    "properties": {
                        "transforms": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["name", "input", "output", "logic"],
                                "properties": {
                                    "name": {"type": "string"},
                                    "input": {"type": "string"},
                                    "output": {"type": "string"},
                                    "logic": {"type": "string"},
                                    "dq_checks": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "default": [],
                                    },
                                },
                            },
                        }
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": ("Use ONLY the data from the `cam.inputs.raina` artifact (inputs.avc / inputs.fss / inputs.pss). Do not expect any 'request' or external graph state. Emit strict JSON transformation specs (input→output with logic and DQ checks) using the appended '=== RUN INPUTS (authoritative, from inputs) ===' and derived datasets. Keep only schema-allowed fields; AdditionalProperties=false. Emit JSON only."),
                    "user_template": "{context}",
                    "variants": [],
                    "io_hints": None,
                    "strict_json": True,
                    "prompt_rev": 2,
                },
                "diagram_recipes": [
                    {
                        "id": "transform.flow",
                        "title": "Transformation Flow",
                        "view": "flowchart",
                        "language": "mermaid",
                        "description": "Transform edges",
                        "template": "flowchart LR\n%% transforms input→output",
                        "prompt": None,
                        "renderer_hints": None,
                        "examples": [],
                        "depends_on": None,
                    }
                ],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
                "identity": {
                    "natural_key": ["transforms.name"],
                    "summary_rule": None,
                    "category": "workflow",
                },
                "adapters": [],
                "migrators": [],
                "examples": [
                    {
                        "transforms": [
                            {
                                "name": "curate_swipes",
                                "input": "raw_swipes",
                                "output": "curated_swipes",
                                "logic": "SELECT ...",
                                "dq_checks": ["not null(txn_id)"],
                            }
                        ]
                    }
                ],
                "depends_on": {
                    "hard": ["cam.inputs.raina", "cam.data.dataset_contract"],
                    "soft": ["cam.data.model_logical"],
                    "context_hint": "Use dataset schemas to validate logic.",
                },
            }
        ],
    },
    {
        "_id": "cam.data.lineage_map",
        "title": "Data Lineage Map",
        "category": "data",
        "aliases": ["cam.data.lineage"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["nodes", "edges"],
                    "properties": {
                        "nodes": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["id", "type", "label"],
                                "properties": {
                                    "id": {"type": "string"},
                                    "type": {
                                        "type": "string",
                                        "enum": ["source", "dataset", "job", "sink"],
                                    },
                                    "label": {"type": "string"},
                                    "system": {"type": ["string", "null"]},
                                },
                            },
                        },
                        "edges": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["from", "to", "kind"],
                                "properties": {
                                    "from": {"type": "string"},
                                    "to": {"type": "string"},
                                    "kind": {
                                        "type": "string",
                                        "enum": [
                                            "reads",
                                            "writes",
                                            "derives",
                                            "publishes",
                                        ],
                                    },
                                },
                            },
                        },
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": ("Use ONLY the data from the `cam.inputs.raina` artifact (inputs.avc / inputs.fss / inputs.pss). Do not expect any 'request' or external graph state. Produce strict JSON lineage nodes/edges derived from datasets and jobs. Read the appended '=== RUN INPUTS (authoritative, from inputs) ===' for AVC/FSS/PSS, FR/NFR to ensure coverage of critical flows and compliance datasets. Do not add fields outside the schema. Emit JSON only."),
                    "user_template": "{context}",
                    "variants": [],
                    "io_hints": None,
                    "strict_json": True,
                    "prompt_rev": 2,
                },
                "diagram_recipes": [
                    {
                        "id": "lineage.flow",
                        "title": "Lineage Flow",
                        "view": "flowchart",
                        "language": "mermaid",
                        "description": "Dataset/job lineage",
                        "template": "flowchart LR\n%% nodes/edges→graph",
                        "prompt": None,
                        "renderer_hints": {"direction": "LR"},
                        "examples": [],
                        "depends_on": None,
                    }
                ],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
                "identity": {
                    "natural_key": ["nodes", "edges"],
                    "summary_rule": None,
                    "category": "data",
                },
                "adapters": [],
                "migrators": [],
                "examples": [
                    {
                        "nodes": [
                            {
                                "id": "kafka_swipes",
                                "type": "source",
                                "label": "Kafka:swipes",
                            },
                            {
                                "id": "curated_swipes",
                                "type": "dataset",
                                "label": "Curated Swipes",
                            },
                        ],
                        "edges": [
                            {
                                "from": "kafka_swipes",
                                "to": "curated_swipes",
                                "kind": "derives",
                            }
                        ],
                    }
                ],
                "depends_on": {
                    "hard": ["cam.inputs.raina", "cam.workflow.data_pipeline_architecture",
                        "cam.data.dataset_contract",],
                    "soft": [
                        "cam.workflow.batch_job_spec",
                        "cam.workflow.stream_job_spec",
                    ],
                    "context_hint": "Generate lineage from stages, jobs, and datasets.",
                },
            }
        ],
    },
    {
        "_id": "cam.governance.data_governance_policies",
        "title": "Data Governance Policies",
        "category": "governance",
        "aliases": ["cam.policy.data_governance"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "classification",
                        "access_controls",
                        "retention",
                        "lineage_requirements",
                    ],
                    "properties": {
                        "classification": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "access_controls": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["role", "permissions"],
                                "properties": {
                                    "role": {"type": "string"},
                                    "permissions": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                },
                            },
                        },
                        "retention": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "default": {"type": "string"},
                                "overrides": {
                                    "type": "object",
                                    "additionalProperties": {"type": "string"},
                                },
                            },
                        },
                        "lineage_requirements": {"type": "string"},
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": ("Use ONLY the data from the `cam.inputs.raina` artifact (inputs.avc / inputs.fss / inputs.pss). Do not expect any 'request' or external graph state. Emit strict JSON governance policies derived from AVC constraints/NFRs in the appended '=== RUN INPUTS (authoritative, from inputs) ==='. Respect the schema only; do not add extra properties. Emit JSON only."),
                    "user_template": "{context}",
                    "variants": [],
                    "io_hints": None,
                    "strict_json": True,
                    "prompt_rev": 2,
                },
                "diagram_recipes": [],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
                "identity": {
                    "natural_key": ["classification", "retention.default"],
                    "summary_rule": None,
                    "category": "governance",
                },
                "adapters": [],
                "migrators": [],
                "examples": [
                    {
                        "classification": ["pii", "financial"],
                        "access_controls": [
                            {"role": "analyst_ro", "permissions": ["SELECT"]}
                        ],
                        "retention": {"default": "365d", "overrides": {}},
                        "lineage_requirements": "End-to-end for financial datasets",
                    }
                ],
                "depends_on": {
                    "hard": ["cam.inputs.raina"],
                    "soft": ["cam.data.dataset_contract"],
                    "context_hint": "Map dataset classifications to policy.",
                },
            }
        ],
    },
    {
        "_id": "cam.security.data_access_control",
        "title": "Data Access Control",
        "category": "security",
        "aliases": ["cam.policy.dac"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["policies"],
                    "properties": {
                        "policies": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["dataset", "role", "access"],
                                "properties": {
                                    "dataset": {"type": "string"},
                                    "role": {"type": "string"},
                                    "access": {
                                        "type": "array",
                                        "items": {
                                            "type": "string",
                                            "enum": ["read", "write", "admin", "mask"],
                                        },
                                    },
                                },
                            },
                        }
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": ("Use ONLY the data from the `cam.inputs.raina` artifact (inputs.avc / inputs.fss / inputs.pss). Do not expect any 'request' or external graph state. Derive strict JSON access control policies from dataset classification and privacy constraints in the appended '=== RUN INPUTS (authoritative, from inputs) ==='. Emit only schema-allowed properties. Emit JSON only."),
                    "user_template": "{context}",
                    "variants": [],
                    "io_hints": None,
                    "strict_json": True,
                    "prompt_rev": 2,
                },
                "diagram_recipes": [],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
                "identity": {
                    "natural_key": ["policies.dataset", "policies.role"],
                    "summary_rule": None,
                    "category": "security",
                },
                "adapters": [],
                "migrators": [],
                "examples": [
                    {
                        "policies": [
                            {
                                "dataset": "transactions_curated",
                                "role": "analyst_ro",
                                "access": ["read", "mask"],
                            }
                        ]
                    }
                ],
                "depends_on": {
                    "hard": ["cam.inputs.raina", "cam.data.dataset_contract",
                        "cam.governance.data_governance_policies",],
                    "soft": [],
                    "context_hint": "Join dataset classification with governance policy to decide access.",
                },
            }
        ],
    },
    {
        "_id": "cam.security.data_masking_policy",
        "title": "Data Masking & Anonymization Policy",
        "category": "security",
        "aliases": ["cam.policy.masking"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["rules"],
                    "properties": {
                        "rules": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["dataset", "field", "strategy"],
                                "properties": {
                                    "dataset": {"type": "string"},
                                    "field": {"type": "string"},
                                    "strategy": {
                                        "type": "string",
                                        "enum": [
                                            "mask",
                                            "hash",
                                            "tokenize",
                                            "generalize",
                                            "noise",
                                        ],
                                    },
                                },
                            },
                        }
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": ("Use ONLY the data from the `cam.inputs.raina` artifact (inputs.avc / inputs.fss / inputs.pss). Do not expect any 'request' or external graph state.From dataset contracts and privacy-related AVC/NFRs in the appended '=== RUN INPUTS (authoritative, from inputs) ===', produce strict JSON field-level masking/anonymization rules. Do not emit extra properties beyond the schema. Emit JSON only."),
                    "user_template": "{context}",
                    "variants": [],
                    "io_hints": None,
                    "strict_json": True,
                    "prompt_rev": 2,
                },
                "diagram_recipes": [],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
                "identity": {
                    "natural_key": ["rules.dataset", "rules.field"],
                    "summary_rule": None,
                    "category": "security",
                },
                "adapters": [],
                "migrators": [],
                "examples": [
                    {
                        "rules": [
                            {
                                "dataset": "transactions_curated",
                                "field": "card_number",
                                "strategy": "tokenize",
                            }
                        ]
                    }
                ],
                "depends_on": {
                    "hard": ["cam.inputs.raina", "cam.data.dataset_contract"],
                    "soft": ["cam.governance.data_governance_policies"],
                    "context_hint": "Map classification/PII flags to masking strategies.",
                },
            }
        ],
    },
    {
        "_id": "cam.quality.data_sla",
        "title": "Data Quality & SLA",
        "category": "quality",
        "aliases": [],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["targets", "monitors"],
                    "properties": {
                        "targets": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": [
                                "freshness",
                                "latency_p95",
                                "availability",
                                "dq_pass_rate",
                            ],
                            "properties": {
                                "freshness": {"type": "string"},
                                "latency_p95": {"type": "string"},
                                "availability": {"type": "string"},
                                "dq_pass_rate": {"type": "string"},
                            },
                        },
                        "monitors": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["name", "type", "metric", "threshold"],
                                "properties": {
                                    "name": {"type": "string"},
                                    "type": {
                                        "type": "string",
                                        "enum": [
                                            "freshness",
                                            "volume",
                                            "schema",
                                            "dq_rule",
                                            "latency",
                                            "availability",
                                        ],
                                    },
                                    "metric": {"type": "string"},
                                    "threshold": {"type": "string"},
                                    "alerting": {"type": "string"},
                                },
                            },
                        },
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": ("Use ONLY the data from the `cam.inputs.raina` artifact (inputs.avc / inputs.fss / inputs.pss). Do not expect any 'request' or external graph state.Define quality/SLA targets and monitors based on NFRs/AVC goals in the appended '=== RUN INPUTS (authoritative, from inputs) ===' and the pipeline architecture. Only use schema-allowed fields. Emit JSON only."),
                    "user_template": "{context}",
                    "variants": [],
                    "io_hints": None,
                    "strict_json": True,
                    "prompt_rev": 2,
                },
                "diagram_recipes": [],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
                "identity": {
                    "natural_key": [
                        "targets.freshness",
                        "targets.latency_p95",
                        "targets.availability",
                    ],
                    "summary_rule": None,
                    "category": "quality",
                },
                "adapters": [],
                "migrators": [],
                "examples": [
                    {
                        "targets": {
                            "freshness": "1h",
                            "latency_p95": "<10m",
                            "availability": "99.9%",
                            "dq_pass_rate": ">=99.5%",
                        },
                        "monitors": [
                            {
                                "name": "freshness_curated_swipes",
                                "type": "freshness",
                                "metric": "age_minutes",
                                "threshold": "<=60",
                                "alerting": "PagerDuty",
                            }
                        ],
                    }
                ],
                "depends_on": {
                    "hard": ["cam.inputs.raina", "cam.workflow.data_pipeline_architecture"],
                    "soft": ["cam.data.dataset_contract"],
                    "context_hint": "Align monitors with SLAs and critical datasets.",
                },
            }
        ],
    },
    {
        "_id": "cam.observability.data_observability_spec",
        "title": "Data Observability Spec",
        "category": "observability",
        "aliases": [],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["metrics", "logs", "traces"],
                    "properties": {
                        "metrics": {"type": "array", "items": {"type": "string"}},
                        "logs": {"type": "array", "items": {"type": "string"}},
                        "traces": {"type": "array", "items": {"type": "string"}},
                        "exporters": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": [],
                        },
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": ("Use ONLY the data from the `cam.inputs.raina` artifact (inputs.avc / inputs.fss / inputs.pss). Do not expect any 'request' or external graph state. Define data observability signals (metrics/logs/traces) and exporters based on FR/NFR in the appended '=== RUN INPUTS (authoritative, from inputs) ===' and the pipeline architecture. Only emit schema-allowed properties. Emit JSON only."),
                    "user_template": "{context}",
                    "variants": [],
                    "io_hints": None,
                    "strict_json": True,
                    "prompt_rev": 2,
                },
                "diagram_recipes": [],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
                "identity": {
                    "natural_key": ["metrics", "exporters"],
                    "summary_rule": None,
                    "category": "observability",
                },
                "adapters": [],
                "migrators": [],
                "examples": [
                    {
                        "metrics": [
                            "dq_pass_rate",
                            "freshness_minutes",
                            "job_latency_p95",
                        ],
                        "logs": ["job_failures", "schema_drift"],
                        "traces": ["ingest→transform→serve"],
                        "exporters": ["OTel", "Prometheus"],
                    }
                ],
                "depends_on": {
                    "hard": ["cam.inputs.raina", "cam.quality.data_sla"],
                    "soft": ["cam.workflow.data_pipeline_architecture"],
                    "context_hint": "Observability derived from SLAs and stages.",
                },
            }
        ],
    },
    {
        "_id": "cam.workflow.orchestration_spec",
        "title": "Data Orchestration Spec",
        "category": "workflow",
        "aliases": ["cam.workflow.schedule"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["orchestrator", "jobs", "dependencies"],
                    "properties": {
                        "orchestrator": {
                            "type": "string",
                            "enum": ["airflow", "dagster", "prefect", "custom"],
                        },
                        "jobs": {"type": "array", "items": {"type": "string"}},
                        "dependencies": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["from", "to"],
                                "properties": {
                                    "from": {"type": "string"},
                                    "to": {"type": "string"},
                                },
                            },
                        },
                        "failure_policy": {
                            "type": "string",
                            "enum": ["halt", "skip", "retry"],
                            "default": "retry",
                        },
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": ("Use ONLY the data from the `cam.inputs.raina` artifact (inputs.avc / inputs.fss / inputs.pss). Do not expect any 'request' or external graph state. Create a strict JSON orchestration spec wiring batch and stream jobs with dependencies aligned to SLAs/NFRs. Choose the orchestrator consistent with PSS and stack rankings. Use the appended '=== RUN INPUTS (authoritative, from inputs) ===' as the basis; emit only schema-allowed properties. Emit JSON only."),
                    "user_template": "{context}",
                    "variants": [],
                    "io_hints": None,
                    "strict_json": True,
                    "prompt_rev": 2,
                },
                "diagram_recipes": [
                    {
                        "id": "orchestration.dependency",
                        "title": "Job Dependency Graph",
                        "view": "flowchart",
                        "language": "mermaid",
                        "description": "Jobs and edges",
                        "template": "flowchart TD\n%% jobs/dependencies",
                        "prompt": None,
                        "renderer_hints": None,
                        "examples": [],
                        "depends_on": None,
                    }
                ],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
                "identity": {
                    "natural_key": ["orchestrator", "jobs"],
                    "summary_rule": None,
                    "category": "workflow",
                },
                "adapters": [],
                "migrators": [],
                "examples": [
                    {
                        "orchestrator": "airflow",
                        "jobs": ["daily_curate", "dq_check"],
                        "dependencies": [{"from": "daily_curate", "to": "dq_check"}],
                        "failure_policy": "retry",
                    }
                ],
                "depends_on": {
                    "hard": ["cam.inputs.raina", "cam.workflow.batch_job_spec",
                        "cam.workflow.stream_job_spec",
                        "cam.quality.data_sla",],
                    "soft": [],
                    "context_hint": "Topologically order jobs to hit freshness/latency targets.",
                },
            }
        ],
    },
    {
        "_id": "cam.catalog.tech_stack_rankings",
        "title": "Tech Stack Rankings",
        "category": "architecture",
        "aliases": ["cam.architecture.tech_stack"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["categories"],
                    "properties": {
                        "categories": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["name", "candidates"],
                                "properties": {
                                    "name": {
                                        "type": "string",
                                        "enum": [
                                            "ingest",
                                            "streaming",
                                            "batch_compute",
                                            "storage",
                                            "lakehouse",
                                            "orchestration",
                                            "transforms",
                                            "dq",
                                            "catalog",
                                            "observability",
                                        ],
                                    },
                                    "candidates": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "additionalProperties": False,
                                            "required": ["rank", "tool"],
                                            "properties": {
                                                "rank": {"type": "integer"},
                                                "tool": {"type": "string"},
                                                "rationale": {"type": "string"},
                                            },
                                        },
                                    },
                                },
                            },
                        }
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": ("Use ONLY the data from the `cam.inputs.raina` artifact (inputs.avc / inputs.fss / inputs.pss). Do not expect any 'request' or external graph state.Produce ranked tech-stack candidates by category with rationale, strictly following the schema. Base recommendations on AVC/FSS/PSS, FR/NFR in the appended '=== RUN INPUTS (authoritative, from inputs) ==='. No extra properties. Emit JSON only."),
                    "user_template": "{context}",
                    "variants": [],
                    "io_hints": None,
                    "strict_json": True,
                    "prompt_rev": 2,
                },
                "diagram_recipes": [],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
                "identity": {
                    "natural_key": ["categories.name"],
                    "summary_rule": None,
                    "category": "architecture",
                },
                "adapters": [],
                "migrators": [],
                "examples": [
                    {
                        "categories": [
                            {
                                "name": "streaming",
                                "candidates": [
                                    {
                                        "rank": 1,
                                        "tool": "Kafka",
                                        "rationale": "ecosystem & scale",
                                    },
                                    {
                                        "rank": 2,
                                        "tool": "Pulsar",
                                        "rationale": "multi-tenant",
                                    },
                                ],
                            }
                        ]
                    }
                ],
                "depends_on": {
                    "hard": ["cam.inputs.raina"],
                    "soft": ["cam.workflow.data_pipeline_architecture"],
                    "context_hint": "Echo/extend pipeline-level stack recommendations.",
                },
            }
        ],
    },
    {
        "_id": "cam.catalog.data_source_inventory",
        "title": "Data Source & Sink Inventory",
        "category": "data",
        "aliases": ["cam.asset.data_sources"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["sources", "sinks"],
                    "properties": {
                        "sources": {"type": "array", "items": {"type": "string"}},
                        "sinks": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": ("Use ONLY the data from the `cam.inputs.raina` artifact (inputs.avc / inputs.fss / inputs.pss). Do not expect any 'request' or external graph state.List principal sources and sinks implied by AVC/FSS/PSS and NFRs in the appended '=== RUN INPUTS (authoritative, from inputs) ==='. Emit strict JSON arrays only; no extra properties."),
                    "user_template": "{context}",
                    "variants": [],
                    "io_hints": None,
                    "strict_json": True,
                    "prompt_rev": 2,
                },
                "diagram_recipes": [],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
                "identity": {
                    "natural_key": ["sources", "sinks"],
                    "summary_rule": None,
                    "category": "data",
                },
                "adapters": [],
                "migrators": [],
                "examples": [
                    {
                        "sources": ["core_banking_db", "swipes_topic"],
                        "sinks": ["alerts_topic", "analytics_lake"],
                    }
                ],
                "depends_on": {
                    "hard": ["cam.inputs.raina"],
                    "soft": [
                        "cam.flow.business_flow_catalog",
                        "cam.data.model_logical",
                    ],
                    "context_hint": "Ground in flows and entities.",
                },
            }
        ],
    },
    {
        "_id": "cam.data_product.catalog",
        "title": "Data Product Catalog",
        "category": "data",
        "aliases": ["cam.data.product"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["products"],
                    "properties": {
                        "products": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["name", "owner", "datasets", "slo"],
                                "properties": {
                                    "name": {"type": "string"},
                                    "owner": {"type": "string"},
                                    "datasets": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "slo": {"type": "string"},
                                },
                            },
                        }
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": ("Use ONLY the data from the `cam.inputs.raina` artifact (inputs.avc / inputs.fss / inputs.pss). Do not expect any 'request' or external graph state.Propose Data-as-a-Product entries bundling datasets with ownership and SLO, strictly per the schema. Base on AVC/FSS/PSS, FR/NFR in the appended '=== RUN INPUTS (authoritative, from inputs) ==='. Do not add extra properties. Emit JSON only."),
                    "user_template": "{context}",
                    "variants": [],
                    "io_hints": None,
                    "strict_json": True,
                    "prompt_rev": 2,
                },
                "diagram_recipes": [],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
                "identity": {
                    "natural_key": ["products.name"],
                    "summary_rule": None,
                    "category": "data",
                },
                "adapters": [],
                "migrators": [],
                "examples": [
                    {
                        "products": [
                            {
                                "name": "Fraud Alerts",
                                "owner": "Risk Analytics",
                                "datasets": ["alerts_topic", "fraud_cases"],
                                "slo": "p95<1m",
                            }
                        ]
                    }
                ],
                "depends_on": {
                    "hard": ["cam.inputs.raina", "cam.data.dataset_contract", "cam.quality.data_sla"],
                    "soft": [],
                    "context_hint": "Use dataset contracts + SLAs to define products.",
                },
            }
        ],
    },
    {
        "_id": "cam.deployment.data_platform_topology",
        "title": "Data Platform Topology",
        "category": "deployment",
        "aliases": ["cam.diagram.deployment.data_platform"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["components", "links", "environments"],
                    "properties": {
                        "components": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["id", "type", "label"],
                                "properties": {
                                    "id": {"type": "string"},
                                    "type": {
                                        "type": "string",
                                        "enum": [
                                            "ingest",
                                            "queue",
                                            "compute",
                                            "storage",
                                            "orchestrator",
                                            "catalog",
                                            "dq",
                                            "observability",
                                        ],
                                    },
                                    "label": {"type": "string"},
                                },
                            },
                        },
                        "links": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["from", "to"],
                                "properties": {
                                    "from": {"type": "string"},
                                    "to": {"type": "string"},
                                    "protocol": {"type": ["string", "null"]},
                                },
                            },
                        },
                        "environments": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": ["dev", "qa", "prod"],
                        },
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": ("Use ONLY the data from the `cam.inputs.raina` artifact (inputs.avc / inputs.fss / inputs.pss). Do not expect any 'request' or external graph state.Output a strict JSON deployment topology covering components and links, derived from PSS stack and NFRs in the appended '=== RUN INPUTS (authoritative, from inputs) ==='. Include target environments. No extra properties. Emit JSON only."),
                    "user_template": "{context}",
                    "variants": [],
                    "io_hints": None,
                    "strict_json": True,
                    "prompt_rev": 2,
                },
                "diagram_recipes": [
                    {
                        "id": "deployment.component",
                        "title": "Component Diagram",
                        "view": "component",
                        "language": "mermaid",
                        "description": "Platform components and connections",
                        "template": "graph LR\n%% components/links",
                        "prompt": None,
                        "renderer_hints": {"direction": "LR"},
                        "examples": [],
                        "depends_on": None,
                    },
                    {
                        "id": "deployment.view",
                        "title": "Deployment View",
                        "view": "deployment",
                        "language": "mermaid",
                        "description": "Infra deployment view",
                        "template": "%% map components to envs",
                        "prompt": None,
                        "renderer_hints": None,
                        "examples": [],
                        "depends_on": None,
                    },
                ],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
                "identity": {
                    "natural_key": ["components", "environments"],
                    "summary_rule": None,
                    "category": "deployment",
                },
                "adapters": [],
                "migrators": [],
                "examples": [
                    {
                        "components": [
                            {"id": "kafka", "type": "queue", "label": "Kafka"},
                            {"id": "spark", "type": "compute", "label": "Spark"},
                        ],
                        "links": [
                            {"from": "kafka", "to": "spark", "protocol": "OTel/HTTP"}
                        ],
                        "environments": ["dev", "prod"],
                    }
                ],
                "depends_on": {
                    "hard": ["cam.inputs.raina", "cam.workflow.data_pipeline_architecture"],
                    "soft": ["cam.observability.data_observability_spec"],
                    "context_hint": "Topology must host the proposed stages and observability.",
                },
            }
        ],
    },
    {
        "_id": "cam.deployment.pipeline_deployment_plan",
        "title": "Pipeline Deployment Plan",
        "category": "deployment",
        "aliases": ["cam.plan.deployment"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["environments", "rollout", "migration", "backout"],
                    "properties": {
                        "environments": {"type": "array", "items": {"type": "string"}},
                        "rollout": {"type": "array", "items": {"type": "string"}},
                        "migration": {"type": "string"},
                        "backout": {"type": "string"},
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": ("Use ONLY the data from the `cam.inputs.raina` artifact (inputs.avc / inputs.fss / inputs.pss). Do not expect any 'request' or external graph state.Create a strict JSON deployment plan across environments based on NFRs, topology, and orchestration, reading the appended '=== RUN INPUTS (authoritative, from inputs) ==='. Include phased rollout, migration/backfill, and backout. No extra properties. Emit JSON only."),
                    "user_template": "{context}",
                    "variants": [],
                    "io_hints": None,
                    "strict_json": True,
                    "prompt_rev": 2,
                },
                "diagram_recipes": [
                    {
                        "id": "deploy.timeline",
                        "title": "Rollout Timeline",
                        "view": "timeline",
                        "language": "mermaid",
                        "description": "High-level rollout timeline",
                        "template": "timeline\n%% rollout steps",
                        "prompt": None,
                        "renderer_hints": None,
                        "examples": [],
                        "depends_on": None,
                    }
                ],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
                "identity": {
                    "natural_key": ["environments", "rollout"],
                    "summary_rule": None,
                    "category": "deployment",
                },
                "adapters": [],
                "migrators": [],
                "examples": [
                    {
                        "environments": ["dev", "qa", "prod"],
                        "rollout": [
                            "dev dual-run",
                            "qa soak",
                            "prod phased enablement",
                        ],
                        "migration": "backfill 90d history",
                        "backout": "toggle legacy feed",
                    }
                ],
                "depends_on": {
                    "hard": ["cam.inputs.raina", "cam.deployment.data_platform_topology",
                        "cam.workflow.orchestration_spec",],
                    "soft": ["cam.quality.data_sla"],
                    "context_hint": "Plan must be feasible on platform and meet SLAs.",
                },
            }
        ],
    },
    # ─────────────────────────────────────────────────────────────
    # File Detail artifact (unchanged schema; prompt already minimal)
    # ─────────────────────────────────────────────────────────────
    {
        "_id": "cam.asset.cobol_artifacts_summary",
        "title": "File Detail",
        "category": "generic",
        "aliases": [],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": True,
                    "required": ["name"],
                    "properties": {
                        "name": {
                            "type": ["string", "null"],
                            "description": "Human-friendly file name (may differ from filename).",
                        },
                        "description": {
                            "type": ["string", "null"],
                            "description": "Optional description of the file contents/purpose.",
                        },
                        "filename": {
                            "type": ["string", "null"],
                            "description": "Actual filename including extension.",
                        },
                        "path": {
                            "type": ["string", "null"],
                            "description": "Logical or repository path (if applicable).",
                        },
                        "storage_uri": {
                            "type": ["string", "null"],
                            "description": "Canonical storage URI.",
                        },
                        "download_url": {
                            "type": ["string", "null"],
                            "format": "uri",
                            "description": "Direct link to download the file.",
                        },
                        "download_expires_at": {
                            "type": ["string", "null"],
                            "format": "date-time",
                            "description": "If the download link is temporary, its expiry.",
                        },
                        "size_bytes": {
                            "type": ["integer", "string", "null"],
                            "description": "Size of the file in bytes.",
                        },
                        "mime_type": {
                            "type": ["string", "null"],
                            "description": "IANA media type.",
                        },
                        "encoding": {
                            "type": ["string", "null"],
                            "description": "Text/binary encoding if relevant.",
                        },
                        "checksum": {
                            "type": ["object", "null"],
                            "additionalProperties": True,
                            "properties": {
                                "md5": {"type": ["string", "null"]},
                                "sha1": {"type": ["string", "null"]},
                                "sha256": {"type": ["string", "null"]},
                            },
                        },
                        "revision": {
                            "type": ["string", "null"],
                            "description": "File revision/version identifier.",
                        },
                        "source_system": {
                            "type": ["string", "null"],
                            "description": "Originating system or repository.",
                        },
                        "owner": {
                            "type": ["string", "null"],
                            "description": "Owner or steward of the file.",
                        },
                        "tags": {
                            "type": ["array", "null"],
                            "items": {"type": "string"},
                            "description": "Free-form tags.",
                        },
                        "created_at": {
                            "type": ["string", "null"],
                            "format": "date-time",
                        },
                        "updated_at": {
                            "type": ["string", "null"],
                            "format": "date-time",
                        },
                        "access_policy": {
                            "type": ["string", "object", "null"],
                            "description": "Policy label or inline ACL summary for the file.",
                        },
                        "metadata": {
                            "type": ["object", "null"],
                            "additionalProperties": True,
                            "description": "Arbitrary extra metadata.",
                        },
                        "preview": {
                            "type": ["object", "null"],
                            "additionalProperties": True,
                            "properties": {
                                "thumbnail_url": {
                                    "type": ["string", "null"],
                                    "format": "uri",
                                },
                                "text_excerpt": {"type": ["string", "null"]},
                                "page_count": {"type": ["integer", "string", "null"]},
                            },
                            "description": "Optional preview hints for UIs.",
                        },
                        "related_assets": {
                            "type": ["array", "null"],
                            "items": {
                                "type": "object",
                                "additionalProperties": True,
                                "required": ["id"],
                                "properties": {
                                    "id": {
                                        "type": ["string", "null"],
                                        "description": "CAM ID of a related asset/kind.",
                                    },
                                    "relation": {
                                        "type": ["string", "null"],
                                        "description": "Relation (e.g., derived-from, source-of).",
                                    },
                                },
                            },
                        },
                    },
                },
                "additional_props_policy": "allow",
                "prompt": {
                    "system": "Produce a summary description of all the cobol specifc artifacts in the workspace.",
                    "strict_json": True,
                },
                "depends_on": {
                    "hard": ["cam.inputs.raina", "cam.cobol.program", "cam.cobol.copybook"],
                    "soft": [],
                },
                "identity": {
                    "natural_key": ["storage_uri", "revision", "checksum.sha256"]
                },
                "examples": [
                    {
                        "name": "Monthly Transactions Export (July 2025)",
                        "description": "CSV export for finance reconciliation.",
                        "filename": "txns_2025_07.csv",
                        "path": "exports/finance/2025/07/txns_2025_07.csv",
                        "storage_uri": "s3://acme-data/exports/finance/2025/07/txns_2025_07.csv",
                        "download_url": "https://signed.example.com/download/txns_2025_07.csv?sig=abc123",
                        "download_expires_at": "2025-08-01T00:00:00Z",
                        "size_bytes": 18432291,
                        "mime_type": "text/csv",
                        "encoding": "utf-8",
                        "checksum": {
                            "sha256": "2dfc0f2b7f3f4b7a8b9d9e2a5c1a9c3d7e4f5a6b8c9d0e1f2a3b4c5d6e7f809a"
                        },
                        "revision": "6b9c1e2",
                        "source_system": "Data Lake (Finance Workspace)",
                        "owner": "finance-data@acme.com",
                        "tags": ["finance", "export", "csv", "monthly"],
                        "created_at": "2025-07-31T23:40:02Z",
                        "updated_at": "2025-07-31T23:41:55Z",
                        "access_policy": "internal-confidential",
                        "metadata": {"row_count": 128934, "columns": 24},
                        "preview": {
                            "thumbnail_url": None,
                            "text_excerpt": "txn_id,posted_at,amount,currency,...",
                            "page_count": None,
                        },
                        "related_assets": [
                            {
                                "id": "cam.catalog.data_products:finance-monthly-txns",
                                "relation": "published-as",
                            }
                        ],
                    }
                ],
                "diagram_recipes": [
                    {
                        "id": "file.card",
                        "title": "File Card",
                        "view": "flowchart",
                        "language": "mermaid",
                        "description": "Compact card with name, size, type.",
                        "template": "flowchart TB\n  A[\"{{ (data.name or data.filename) | replace('\\\"', \"'\") }}\\n{{ (data.mime_type or 'unknown') }}\\n{{ (data.size_bytes or 'n/a') }} bytes\"]",
                        "renderer_hints": {"direction": "TB"},
                    }
                ],
                "narratives_spec": {
                    "allowed_formats": ["markdown", "asciidoc"],
                    "default_format": "markdown",
                    "max_length_chars": 10000,
                    "allowed_locales": ["en-US"],
                },
            }
        ],
    },
    # ─────────────────────────────────────────────────────────────
    # NEW: Architecture Guidance Document (prose, grounded on artifacts)
    # ─────────────────────────────────────────────────────────────
    {
        "_id": "cam.documents.data-pipeline-arch-guidance",
        "title": "Data Pipeline Architecture Guidance",
        "category": "documents",
        "aliases": [
            "cam.doc.data_pipeline_guidance",
            "cam.docs.pipeline_arch_guidance",
        ],
        "status": "active",
        "latest_schema_version": "1.0.0",
        "schema_versions": [
            {
                "version": "1.0.0",
                "json_schema": {
                    "type": "object",
                    "additionalProperties": True,
                    "required": ["name"],
                    "properties": {
                        "name": {
                            "type": ["string", "null"],
                            "description": "Human-friendly file name (may differ from filename).",
                        },
                        "description": {
                            "type": ["string", "null"],
                            "description": "Optional description of the file contents/purpose.",
                        },
                        "filename": {
                            "type": ["string", "null"],
                            "description": "Actual filename including extension.",
                        },
                        "path": {
                            "type": ["string", "null"],
                            "description": "Logical or repository path (if applicable).",
                        },
                        "storage_uri": {
                            "type": ["string", "null"],
                            "description": "Canonical storage URI.",
                        },
                        "download_url": {
                            "type": ["string", "null"],
                            "format": "uri",
                            "description": "Direct link to download the file.",
                        },
                        "download_expires_at": {
                            "type": ["string", "null"],
                            "format": "date-time",
                            "description": "If the download link is temporary, its expiry.",
                        },
                        "size_bytes": {
                            "type": ["integer", "string", "null"],
                            "description": "Size of the file in bytes.",
                        },
                        "mime_type": {
                            "type": ["string", "null"],
                            "description": "IANA media type.",
                        },
                        "encoding": {
                            "type": ["string", "null"],
                            "description": "Text/binary encoding if relevant.",
                        },
                        "checksum": {
                            "type": ["object", "null"],
                            "additionalProperties": True,
                            "properties": {
                                "md5": {"type": ["string", "null"]},
                                "sha1": {"type": ["string", "null"]},
                                "sha256": {"type": ["string", "null"]},
                            },
                        },
                        "revision": {
                            "type": ["string", "null"],
                            "description": "File revision/version identifier.",
                        },
                        "source_system": {
                            "type": ["string", "null"],
                            "description": "Originating system or repository.",
                        },
                        "owner": {
                            "type": ["string", "null"],
                            "description": "Owner or steward of the file.",
                        },
                        "tags": {
                            "type": ["array", "null"],
                            "items": {"type": "string"},
                            "description": "Free-form tags.",
                        },
                        "created_at": {
                            "type": ["string", "null"],
                            "format": "date-time",
                        },
                        "updated_at": {
                            "type": ["string", "null"],
                            "format": "date-time",
                        },
                        "access_policy": {
                            "type": ["string", "object", "null"],
                            "description": "Policy label or inline ACL summary for the file.",
                        },
                        "metadata": {
                            "type": ["object", "null"],
                            "additionalProperties": True,
                            "description": "Arbitrary extra metadata.",
                        },
                        "preview": {
                            "type": ["object", "null"],
                            "additionalProperties": True,
                            "properties": {
                                "thumbnail_url": {
                                    "type": ["string", "null"],
                                    "format": "uri",
                                },
                                "text_excerpt": {"type": ["string", "null"]},
                                "page_count": {"type": ["integer", "string", "null"]},
                            },
                            "description": "Optional preview hints for UIs.",
                        },
                        "related_assets": {
                            "type": ["array", "null"],
                            "items": {
                                "type": "object",
                                "additionalProperties": True,
                                "required": ["id"],
                                "properties": {
                                    "id": {
                                        "type": ["string", "null"],
                                        "description": "CAM ID of a related asset/kind.",
                                    },
                                    "relation": {
                                        "type": ["string", "null"],
                                        "description": "Relation (e.g., derived-from, source-of).",
                                    },
                                },
                            },
                        },
                    },
                },
                "additional_props_policy": "allow",
                "prompt": {
                    "system": 'You are to author a comprehensive **Architecture Guidance Document** for a *data engineering* pipeline as the lead architect instructing delivery teams.\n\n# Grounding sources (MUST cite both)\n1) The section labeled exactly: `=== RUN INPUTS (authoritative, from request.inputs) ===` — contains AVC/FSS/PSS, FR/NFR, goals, constraints.\n2) The section labeled exactly: `=== DEPENDENCIES (discovered artifacts) ===` — already-staged CAM artifacts and their facts.\n\n# Output CONTRACT (STRICT)\n- Output **exactly one** JSON object. **No text before or after** the JSON.\n- The JSON object MUST include:\n\t - `name`: "Data Pipeline Architecture Guidance"\n\t - `description`: one-line summary\n\t - `filename`: "data-pipeline-architecture-guidance.md"\n\t - `mime_type`: "text/markdown"\n\t - `tags`: array of sensible tags, e.g. ["architecture","guidance","data-pipeline"]\n\t - `content`: a **single string** that is a **valid GitHub-Flavored Markdown document** (GFM).\n- You MAY include additional metadata fields permitted by schema (e.g., `owner`, `version`, `dependencies_refs`, etc.), but **all prose MUST live inside `content`**.\n\n# Markdown FORMAT RULES (HARD)\n- Use proper Markdown headings only (`#`, `##`, `###` …). No ad-hoc banners or underlines.\n- Provide a title H1: `# Data Pipeline Architecture Guidance`\n- Immediately follow with a metadata table (Owner, Version, Date, Scope, Out of Scope).\n- Provide a **Table of Contents** with **anchor links** to sections (GFM link style).\n- **Every diagram MUST be fenced** as:\n\t ```mermaid\n\t <valid mermaid>\n\t ```\n\t **CRITICAL:** Do NOT include a blank ` ``` ` fence before or after the ` ```mermaid` block. Flowcharts MUST use `flowchart TD` or `graph TD` syntax (NOT `gantt`). Use standard, safe UTF-8 characters for prose (e.g., prefer `->` or `-->` over special arrow characters if encoding issues persist).\n- When referencing facts from artifacts, cite inline like: *(from cam.data.dataset_contract: transactions_curated)*.\n- If a fact is unknown from RUN INPUTS or DEPENDENCIES, either omit, or include it under **Assumptions**.\n\n# Document SECTIONS (REQUIRED)\n1. Executive Summary (context from AVC, recommended approach)\n2. Architecture Overview (align to patterns selected: batch/stream/lambda/event-driven; high-level flow; mermaid optional)\n3. Source & Sink Inventory (trace to Business Flows + Logical Data Model)\n4. Data Model Overview (key entities, PII notes, relationship summary — no schema dumps)\n5. Dataset Contracts (what consumers need, retention, classification; link names to contracts)\n6. Transformation Design (major transforms, DQ checks, idempotency & windowing as relevant)\n7. Jobs & Orchestration (batch/stream jobs, schedules/latency targets, dependencies/backfills/failure policy)\n8. Lineage (critical paths, auditability, compliance impact)\n9. Governance & Security (classification, access control, masking + rationale)\n10. SLAs & Observability (targets, monitors, alerting paths, SLO dashboards)\n11. Platform Topology & Tech Stack (rankings, rationale, environment strategy)\n12. Deployment Plan (rollout phases, backout/rollback, data migration/backfill)\n13. **ADRs** (3–6): Context → Decision → Consequences → Alternatives\n14. Risks & Mitigations, Assumptions, Open Questions\n15. Appendices (glossary, references to artifact IDs/kinds, example queries, runbooks)\n\n# Tone & Constraints\n- Directive, precise, implementation-oriented; no hand-waving.\n- Prefer concise, accurate prose; separate **Facts** vs **Assumptions**.\n- All statements MUST be grounded in RUN INPUTS and/or DEPENDENCIES; explicitly label assumptions.\n\n# Self-Validation CHECKLIST (perform before emitting JSON)\n- [ ] Output is a **single JSON object**.\n- [ ] JSON contains a **string** field `content`.\n- [ ] `content` starts with `# Data Pipeline Architecture Guidance`.\n- [ ] All diagrams (if any) are inside a **single** fenced block starting with ```mermaid and ending with ``` on their own lines (no triple-backticks alone).\n- [ ] No stray “mermaid” tokens outside fences.\n- [ ] Table of Contents contains anchor links that match headings.\n- [ ] Required sections 1–15 present.\n- [ ] File metadata fields set exactly as specified.\n\nNow produce the JSON.\n\n=== RUN INPUTS (authoritative, from request.inputs) ===\n{{RUN_INPUTS}}\n\n=== DEPENDENCIES (discovered artifacts) ===\n{{DEPENDENCIES}}',
                    "strict_json": True,
                },
                "depends_on": {
                    "hard": ["cam.inputs.raina", "cam.catalog.data_source_inventory",
                        "cam.flow.business_flow_catalog",
                        "cam.data.model_logical",
                        "cam.architecture.pipeline_patterns",
                        "cam.data.dataset_contract",
                        "cam.workflow.transform_spec",
                        "cam.workflow.batch_job_spec",
                        "cam.workflow.stream_job_spec",
                        "cam.workflow.orchestration_spec",
                        "cam.data.lineage_map",
                        "cam.governance.data_governance_policies",
                        "cam.security.data_access_control",
                        "cam.security.data_masking_policy",
                        "cam.quality.data_sla",
                        "cam.observability.data_observability_spec",
                        "cam.deployment.data_platform_topology",
                        "cam.catalog.tech_stack_rankings",
                        "cam.data_product.catalog",
                        "cam.workflow.data_pipeline_architecture",
                        "cam.deployment.pipeline_deployment_plan",],
                    "soft": [],
                },
                "identity": {"natural_key": ["filename", "revision"]},
                "examples": [
                    {
                        "name": "Data Pipeline Architecture Guidance",
                        "description": "Directive architecture guidance grounded on discovered artifacts and RUN INPUTS.",
                        "filename": "data-pipeline-architecture-guidance.md",
                        "mime_type": "text/markdown",
                        "tags": ["architecture", "guidance", "data-pipeline"],
                        "content": "# Data Pipeline Architecture Guidance\n\n<!-- Example structure only; real content generated at runtime -->\n\n## Executive Summary\n...\n\n## Table of Contents\n- [Executive Summary](#executive-summary)\n- [Architecture Overview](#architecture-overview)\n- [ADRs](#architecture-decision-records-adrs)\n- [Appendix](#appendix)\n",
                        "related_assets": [
                            {
                                "id": "cam.workflow.data_pipeline_architecture",
                                "relation": "grounds",
                            },
                            {
                                "id": "cam.architecture.pipeline_patterns",
                                "relation": "cites",
                            },
                        ],
                    }
                ],
                "diagram_recipes": [],
                "narratives_spec": {
                    "allowed_formats": ["markdown", "asciidoc"],
                    "default_format": "markdown",
                    "max_length_chars": 50000,
                    "allowed_locales": ["en-US"],
                },
            }
        ],
    },
    {
        "_id": "cam.inputs.raina",
        "title": "Raina Input (AVC/FSS/PSS)",
        "category": "inputs",
        "aliases": ["cam.raina.input", "cam.discovery.raina"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "$id": "https://astra.example/schemas/raina-input.json",
                    "title": "Raina Input",
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["inputs"],
                    "properties": {
                        "inputs": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["avc", "fss", "pss"],
                            "properties": {
                                "avc": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": [
                                        "vision",
                                        "problem_statements",
                                        "goals",
                                        "non_functionals",
                                        "constraints",
                                        "assumptions",
                                        "context",
                                        "success_criteria",
                                    ],
                                    "properties": {
                                        "vision": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "default": [],
                                        },
                                        "problem_statements": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "default": [],
                                        },
                                        "goals": {
                                            "type": "array",
                                            "default": [],
                                            "items": {
                                                "type": "object",
                                                "additionalProperties": False,
                                                "required": ["id", "text"],
                                                "properties": {
                                                    "id": {
                                                        "type": "string",
                                                        "minLength": 1,
                                                    },
                                                    "text": {
                                                        "type": "string",
                                                        "minLength": 1,
                                                    },
                                                    "metric": {
                                                        "type": ["string", "null"]
                                                    },
                                                },
                                            },
                                        },
                                        "non_functionals": {
                                            "type": "array",
                                            "default": [],
                                            "items": {
                                                "type": "object",
                                                "additionalProperties": False,
                                                "required": ["type", "target"],
                                                "properties": {
                                                    "type": {
                                                        "type": "string",
                                                        "minLength": 1,
                                                    },
                                                    "target": {
                                                        "type": "string",
                                                        "minLength": 1,
                                                    },
                                                },
                                            },
                                        },
                                        "constraints": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "default": [],
                                        },
                                        "assumptions": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "default": [],
                                        },
                                        "context": {
                                            "type": "object",
                                            "additionalProperties": False,
                                            "required": ["domain", "actors"],
                                            "properties": {
                                                "domain": {"type": "string"},
                                                "actors": {
                                                    "type": "array",
                                                    "items": {"type": "string"},
                                                    "default": [],
                                                },
                                            },
                                        },
                                        "success_criteria": {
                                            "type": "array",
                                            "default": [],
                                            "items": {
                                                "type": "object",
                                                "additionalProperties": False,
                                                "required": ["kpi", "target"],
                                                "properties": {
                                                    "kpi": {
                                                        "type": "string",
                                                        "minLength": 1,
                                                    },
                                                    "target": {
                                                        "type": "string",
                                                        "minLength": 1,
                                                    },
                                                },
                                            },
                                        },
                                    },
                                },
                                "fss": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["stories"],
                                    "properties": {
                                        "stories": {
                                            "type": "array",
                                            "default": [],
                                            "items": {
                                                "type": "object",
                                                "additionalProperties": False,
                                                "required": ["key", "title"],
                                                "properties": {
                                                    "key": {
                                                        "type": "string",
                                                        "minLength": 1,
                                                    },
                                                    "title": {
                                                        "type": "string",
                                                        "minLength": 1,
                                                    },
                                                    "description": {
                                                        "oneOf": [
                                                            {"type": "string"},
                                                            {
                                                                "type": "array",
                                                                "items": {
                                                                    "type": "string"
                                                                },
                                                            },
                                                            {"type": "null"},
                                                        ]
                                                    },
                                                    "acceptance_criteria": {
                                                        "type": "array",
                                                        "items": {"type": "string"},
                                                        "default": [],
                                                    },
                                                    "tags": {
                                                        "type": "array",
                                                        "items": {"type": "string"},
                                                        "default": [],
                                                    },
                                                },
                                            },
                                        }
                                    },
                                },
                                "pss": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["paradigm", "style", "tech_stack"],
                                    "properties": {
                                        "paradigm": {"type": "string", "minLength": 1},
                                        "style": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "default": [],
                                        },
                                        "tech_stack": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "default": [],
                                        },
                                    },
                                },
                            },
                        }
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": ("Use ONLY the data from the `cam.inputs.raina` artifact (inputs.avc / inputs.fss / inputs.pss). Do not expect any 'request' or external graph state.Validate and store a Raina Input document (AVC/FSS/PSS). Emit JSON strictly conforming to the schema; do not add fields."),
                    "strict_json": True,
                },
                "depends_on": {
                    "hard": ["cam.inputs.raina"],
                    "soft": [],
                },
                "identity": {
                    # Adjust if you prefer a composite natural key.
                    "natural_key": ["inputs.avc.context.domain"]
                },
                "examples": [
                    {
                        "inputs": {
                            "avc": {
                                "vision": [
                                    "Modernize the COBOL-based retail equity post-trade system into a real-time, scalable pipeline..."
                                ],
                                "problem_statements": [
                                    "The current mainframe application is a batch monolith..."
                                ],
                                "goals": [
                                    {
                                        "id": "G1",
                                        "text": "Ingest and validate trade and quote streams...",
                                        "metric": "validation throughput in trades per second",
                                    }
                                ],
                                "non_functionals": [
                                    {"type": "performance", "target": "p95<60s"}
                                ],
                                "constraints": [
                                    "Must operate on multiple currencies (USD/EUR/GBP)"
                                ],
                                "assumptions": [
                                    "Modern platform will have access to GPU resources..."
                                ],
                                "context": {
                                    "domain": "Retail Equity Post-Trade",
                                    "actors": ["Trader", "RiskAnalyst"],
                                },
                                "success_criteria": [
                                    {
                                        "kpi": "validation_latency",
                                        "target": "< 1 second",
                                    }
                                ],
                            },
                            "fss": {
                                "stories": [
                                    {
                                        "key": "EPT-101",
                                        "title": "Ingest and validate trades",
                                        "description": [
                                            "As the system, I need to ingest raw trade events..."
                                        ],
                                        "acceptance_criteria": [
                                            "Trades with invalid side values are marked invalid"
                                        ],
                                        "tags": [
                                            "domain:trade",
                                            "function:validation",
                                            "actor:Trader",
                                        ],
                                    }
                                ]
                            },
                            "pss": {
                                "paradigm": "Data Engineering",
                                "style": [
                                    "Streaming Pipeline",
                                    "Batch-able Steps for Back-Filling",
                                ],
                                "tech_stack": [
                                    "Apache Kafka",
                                    "Apache Flink",
                                    "RAPIDS cuDF",
                                ],
                            },
                        }
                    }
                ],
                "diagram_recipes": [],
                "narratives_spec": {
                    "allowed_formats": ["markdown", "asciidoc"],
                    "default_format": "markdown",
                    "max_length_chars": 200000,
                    "allowed_locales": ["en-US"],
                },
            }
        ],
    },
]


def seed_registry() -> None:
    now = datetime.utcnow()
    for doc in KIND_DOCS:
        doc.setdefault("aliases", [])
        doc.setdefault("policies", {})
        doc["created_at"] = doc.get("created_at", now)
        doc["updated_at"] = now
        upsert_kind(doc)


if __name__ == "__main__":
    seed_registry()
    print(f"Seeded {len(KIND_DOCS)} kinds into registry.")

# services/artifact-service/app/seeds/seed_microservices_arch_registry.py
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
    # ---------------------------------------------------------------------
    # Domain & Service Design
    # ---------------------------------------------------------------------
    {
        "_id": "cam.domain.ubiquitous_language",
        "title": "Ubiquitous Language",
        "category": "domain",
        "aliases": ["cam.domain.glossary", "cam.domain.terms"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["domain", "terms"],
                    "properties": {
                        "domain": {"type": "string", "minLength": 1},
                        "terms": {
                            "type": "array",
                            "default": [],
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["term", "definition"],
                                "properties": {
                                    "term": {"type": "string", "minLength": 1},
                                    "definition": {"type": "string", "minLength": 1},
                                    "synonyms": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "default": [],
                                    },
                                    "context": {
                                        "type": ["string", "null"],
                                        "description": "Optional bounded context name where this term is used.",
                                    },
                                    "examples": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "default": [],
                                    },
                                },
                            },
                        },
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": (
                        "Derive a concise ubiquitous language from `cam.asset.raina_input` "
                        "(AVC/FSS/PSS). Output JSON strictly matching the schema."
                    ),
                    "strict_json": True,
                },
                "depends_on": {"hard": ["cam.asset.raina_input"], "soft": []},
                "identity": {"natural_key": ["domain"]},
                "examples": [
                    {
                        "domain": "Retail Equity Post-Trade",
                        "terms": [
                            {
                                "term": "Trade",
                                "definition": "An executed buy/sell transaction recorded for settlement and reporting.",
                                "synonyms": ["Fill"],
                                "context": "Trade Capture",
                                "examples": [
                                    "A trade has side, quantity, price, and instrument."
                                ],
                            }
                        ],
                    }
                ],
                "diagram_recipes": [],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
            }
        ],
    },
    {
        "_id": "cam.domain.bounded_context_map",
        "title": "Bounded Context Map",
        "category": "domain",
        "aliases": ["cam.domain.context_map"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["domain", "contexts", "relationships"],
                    "properties": {
                        "domain": {"type": "string", "minLength": 1},
                        "contexts": {
                            "type": "array",
                            "default": [],
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["name", "description", "capabilities"],
                                "properties": {
                                    "name": {"type": "string", "minLength": 1},
                                    "description": {"type": "string", "minLength": 1},
                                    "capabilities": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "default": [],
                                    },
                                    "core_domain": {
                                        "type": "boolean",
                                        "default": False,
                                    },
                                    "key_entities": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "default": [],
                                    },
                                },
                            },
                        },
                        "relationships": {
                            "type": "array",
                            "default": [],
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["from", "to", "type"],
                                "properties": {
                                    "from": {"type": "string", "minLength": 1},
                                    "to": {"type": "string", "minLength": 1},
                                    "type": {
                                        "type": "string",
                                        "enum": [
                                            "customer_supplier",
                                            "conformist",
                                            "anti_corruption_layer",
                                            "shared_kernel",
                                            "partnership",
                                            "separate_ways",
                                            "open_host_service",
                                            "published_language",
                                        ],
                                    },
                                    "notes": {"type": ["string", "null"]},
                                },
                            },
                        },
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": (
                        "Discover bounded contexts based on `cam.asset.raina_input` and the "
                        "domain terms in `cam.domain.ubiquitous_language`. Output strict JSON."
                    ),
                    "strict_json": True,
                },
                "depends_on": {
                    "hard": ["cam.asset.raina_input", "cam.domain.ubiquitous_language"],
                    "soft": [],
                },
                "identity": {"natural_key": ["domain"]},
                "examples": [
                    {
                        "domain": "Retail Equity Post-Trade",
                        "contexts": [
                            {
                                "name": "Trade Capture",
                                "description": "Captures, validates, and normalizes trades.",
                                "capabilities": [
                                    "ingest trades",
                                    "validate",
                                    "normalize",
                                ],
                                "core_domain": True,
                                "key_entities": ["Trade", "Instrument"],
                            }
                        ],
                        "relationships": [
                            {
                                "from": "Trade Capture",
                                "to": "Settlement",
                                "type": "customer_supplier",
                                "notes": "Settlement consumes validated trades.",
                            }
                        ],
                    }
                ],
                "diagram_recipes": [
                    {
                        "id": "context_map",
                        "title": "Bounded Context Map",
                        "view": "flowchart",
                        "language": "mermaid",
                        "description": "Visualize bounded contexts and their relationship types.",
                        "template": (
                            "flowchart LR\n"
                            "  %% Render contexts and relationships from bounded context map\n"
                            "  %% Nodes: contexts[].name\n"
                            "  %% Edges: relationships[].from --> relationships[].to\n"
                        ),
                        "prompt": None,
                        "renderer_hints": {"direction": "LR"},
                        "examples": [],
                        "depends_on": None,
                    }
                ],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
            }
        ],
    },
    {
        "_id": "cam.catalog.microservice_inventory",
        "title": "Microservice Inventory",
        "category": "catalog",
        "aliases": [
            "cam.catalog.service_inventory",
            "cam.architecture.service_inventory",
        ],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["domain", "services"],
                    "properties": {
                        "domain": {"type": "string", "minLength": 1},
                        "services": {
                            "type": "array",
                            "default": [],
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": [
                                    "name",
                                    "bounded_context",
                                    "responsibilities",
                                ],
                                "properties": {
                                    "name": {"type": "string", "minLength": 1},
                                    "bounded_context": {
                                        "type": "string",
                                        "minLength": 1,
                                    },
                                    "responsibilities": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "default": [],
                                    },
                                    "owned_data": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "default": [],
                                    },
                                    "apis": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "default": [],
                                    },
                                    "events_published": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "default": [],
                                    },
                                    "events_consumed": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "default": [],
                                    },
                                    "dependencies": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "default": [],
                                    },
                                    "notes": {"type": ["string", "null"]},
                                },
                            },
                        },
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": (
                        "Derive candidate microservices from `cam.domain.bounded_context_map`. "
                        "Keep services cohesive and aligned to bounded contexts. Output strict JSON."
                    ),
                    "strict_json": True,
                },
                "depends_on": {
                    "hard": ["cam.domain.bounded_context_map"],
                    "soft": ["cam.asset.raina_input"],
                },
                "identity": {"natural_key": ["domain"]},
                "examples": [
                    {
                        "domain": "Retail Equity Post-Trade",
                        "services": [
                            {
                                "name": "trade-capture-svc",
                                "bounded_context": "Trade Capture",
                                "responsibilities": [
                                    "ingest trades",
                                    "validate trades",
                                    "publish TradeValidated",
                                ],
                                "owned_data": ["Trade"],
                                "apis": ["POST /trades", "GET /trades/{id}"],
                                "events_published": ["TradeValidated"],
                                "events_consumed": [],
                                "dependencies": [],
                                "notes": "Front-door for trade ingestion.",
                            }
                        ],
                    }
                ],
                "diagram_recipes": [],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
            }
        ],
    },
    {
        "_id": "cam.architecture.service_interaction_matrix",
        "title": "Service Interaction Matrix",
        "category": "architecture",
        "aliases": ["cam.architecture.interaction_matrix"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["domain", "interactions"],
                    "properties": {
                        "domain": {"type": "string", "minLength": 1},
                        "interactions": {
                            "type": "array",
                            "default": [],
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": [
                                    "from",
                                    "to",
                                    "mode",
                                    "mechanism",
                                    "purpose",
                                ],
                                "properties": {
                                    "from": {"type": "string", "minLength": 1},
                                    "to": {"type": "string", "minLength": 1},
                                    "mode": {
                                        "type": "string",
                                        "enum": ["sync", "async"],
                                    },
                                    "mechanism": {
                                        "type": "string",
                                        "enum": [
                                            "http_api",
                                            "grpc",
                                            "event",
                                            "queue",
                                            "file",
                                            "db_replication",
                                        ],
                                    },
                                    "purpose": {"type": "string", "minLength": 1},
                                    "reliability": {
                                        "type": ["string", "null"],
                                        "description": "e.g., retries, DLQ, idempotency, at-least-once",
                                    },
                                },
                            },
                        },
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": (
                        "Map interactions based on service APIs (`cam.contract.service_api`) "
                        "and events (`cam.catalog.events`). Output strict JSON."
                    ),
                    "strict_json": True,
                },
                "depends_on": {
                    "hard": [
                        "cam.contract.service_api",
                        "cam.catalog.events",
                    ],
                    "soft": [],
                },
                "identity": {"natural_key": ["domain"]},
                "examples": [
                    {
                        "domain": "Retail Equity Post-Trade",
                        "interactions": [
                            {
                                "from": "trade-capture-svc",
                                "to": "settlement-svc",
                                "mode": "async",
                                "mechanism": "event",
                                "purpose": "Propagate validated trades for settlement workflow.",
                                "reliability": "outbox + at-least-once + idempotent consumers",
                            }
                        ],
                    }
                ],
                "diagram_recipes": [
                    {
                        "id": "service_interactions",
                        "title": "Service Interactions",
                        "view": "flowchart",
                        "language": "mermaid",
                        "description": "Graph service-to-service edges with labeled mode/mechanism.",
                        "template": (
                            "flowchart LR\n"
                            "  %% Nodes: unique service names in interactions\n"
                            "  %% Edges: from --> to with labels mode/mechanism\n"
                        ),
                        "prompt": None,
                        "renderer_hints": {"direction": "LR"},
                        "examples": [],
                        "depends_on": None,
                    }
                ],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
            }
        ],
    },
    # ---------------------------------------------------------------------
    # Contracts
    # ---------------------------------------------------------------------
    {
        "_id": "cam.contract.service_api",
        "title": "Service API Contracts",
        "category": "contract",
        "aliases": ["cam.api.service_api_contract", "cam.api.contracts", "cam.api.service_contracts"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["domain", "contracts"],
                    "properties": {
                        "domain": {"type": "string", "minLength": 1},
                        "contracts": {
                            "type": "array",
                            "default": [],
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["service", "endpoints"],
                                "properties": {
                                    "service": {"type": "string", "minLength": 1},
                                    "base_path": {"type": ["string", "null"]},
                                    "endpoints": {
                                        "type": "array",
                                        "default": [],
                                        "items": {
                                            "type": "object",
                                            "additionalProperties": False,
                                            "required": ["method", "path", "summary"],
                                            "properties": {
                                                "method": {
                                                    "type": "string",
                                                    "enum": [
                                                        "GET",
                                                        "POST",
                                                        "PUT",
                                                        "PATCH",
                                                        "DELETE",
                                                    ],
                                                },
                                                "path": {
                                                    "type": "string",
                                                    "minLength": 1,
                                                },
                                                "summary": {
                                                    "type": "string",
                                                    "minLength": 1,
                                                },
                                                "request": {"type": ["object", "null"]},
                                                "response": {
                                                    "type": ["object", "null"]
                                                },
                                                "auth": {
                                                    "type": ["string", "null"],
                                                    "description": "e.g., oauth2, mTLS, api-key, none",
                                                },
                                                "idempotent": {
                                                    "type": "boolean",
                                                    "default": False,
                                                },
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": (
                        "Define APIs per service using `cam.catalog.microservice_inventory` and "
                        "`cam.asset.raina_input` stories. Output strict JSON."
                    ),
                    "strict_json": True,
                },
                "depends_on": {
                    "hard": ["cam.catalog.microservice_inventory", "cam.asset.raina_input"],
                    "soft": [],
                },
                "identity": {"natural_key": ["domain"]},
                "examples": [
                    {
                        "domain": "Retail Equity Post-Trade",
                        "contracts": [
                            {
                                "service": "trade-capture-svc",
                                "base_path": "/trade-capture",
                                "endpoints": [
                                    {
                                        "method": "POST",
                                        "path": "/trades",
                                        "summary": "Ingest a new trade event for validation.",
                                        "request": {
                                            "content_type": "application/json",
                                            "schema_ref": "TradeIn",
                                        },
                                        "response": {
                                            "status": 202,
                                            "schema_ref": "TradeAccepted",
                                        },
                                        "auth": "oauth2",
                                        "idempotent": True,
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "diagram_recipes": [],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
            }
        ],
    },
    {
        "_id": "cam.catalog.events",
        "title": "Event Catalog",
        "category": "catalog",
        "aliases": ["cam.events.event_catalog", "cam.events.catalog"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["domain", "events"],
                    "properties": {
                        "domain": {"type": "string", "minLength": 1},
                        "events": {
                            "type": "array",
                            "default": [],
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["name", "publisher", "description"],
                                "properties": {
                                    "name": {"type": "string", "minLength": 1},
                                    "description": {"type": "string", "minLength": 1},
                                    "publisher": {"type": "string", "minLength": 1},
                                    "subscribers": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "default": [],
                                    },
                                    "schema": {"type": ["object", "null"]},
                                    "delivery": {
                                        "type": ["string", "null"],
                                        "description": "e.g., at-least-once + DLQ + retry policy",
                                    },
                                },
                            },
                        },
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": (
                        "Define domain events from `cam.catalog.microservice_inventory` and "
                        "`cam.domain.ubiquitous_language`. Output strict JSON."
                    ),
                    "strict_json": True,
                },
                "depends_on": {
                    "hard": [
                        "cam.catalog.microservice_inventory",
                        "cam.domain.ubiquitous_language",
                    ],
                    "soft": ["cam.asset.raina_input"],
                },
                "identity": {"natural_key": ["domain"]},
                "examples": [
                    {
                        "domain": "Retail Equity Post-Trade",
                        "events": [
                            {
                                "name": "TradeValidated",
                                "description": "Emitted when a trade passes validation and normalization.",
                                "publisher": "trade-capture-svc",
                                "subscribers": ["settlement-svc", "risk-svc"],
                                "schema": {
                                    "type": "object",
                                    "required": ["trade_id", "status"],
                                },
                                "delivery": "at-least-once + DLQ; idempotent subscribers",
                            }
                        ],
                    }
                ],
                "diagram_recipes": [],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
            }
        ],
    },
    {
        "_id": "cam.data.service_data_ownership",
        "title": "Service Data Ownership",
        "category": "data",
        "aliases": ["cam.data.ownership_map"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["domain", "ownership"],
                    "properties": {
                        "domain": {"type": "string", "minLength": 1},
                        "ownership": {
                            "type": "array",
                            "default": [],
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": [
                                    "service",
                                    "data_entities",
                                    "consistency_model",
                                ],
                                "properties": {
                                    "service": {"type": "string", "minLength": 1},
                                    "data_entities": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "default": [],
                                    },
                                    "storage": {
                                        "type": ["string", "null"],
                                        "description": "e.g., postgres, mongo, dynamodb",
                                    },
                                    "consistency_model": {
                                        "type": "string",
                                        "enum": [
                                            "strong",
                                            "eventual",
                                            "bounded_staleness",
                                        ],
                                    },
                                    "sharing_strategy": {
                                        "type": ["string", "null"],
                                        "description": "e.g., API-only, events, CDC, shared DB (discouraged)",
                                    },
                                    "notes": {"type": ["string", "null"]},
                                },
                            },
                        },
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": (
                        "Assign data ownership per service using `cam.catalog.microservice_inventory` "
                        "and `cam.asset.raina_input`. Prefer database-per-service. Output strict JSON."
                    ),
                    "strict_json": True,
                },
                "depends_on": {
                    "hard": ["cam.catalog.microservice_inventory", "cam.asset.raina_input"],
                    "soft": [],
                },
                "identity": {"natural_key": ["domain"]},
                "examples": [
                    {
                        "domain": "Retail Equity Post-Trade",
                        "ownership": [
                            {
                                "service": "trade-capture-svc",
                                "data_entities": ["Trade"],
                                "storage": "postgres",
                                "consistency_model": "strong",
                                "sharing_strategy": "events + API",
                                "notes": "Other services rely on TradeValidated events.",
                            }
                        ],
                    }
                ],
                "diagram_recipes": [],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
            }
        ],
    },
    # ---------------------------------------------------------------------
    # Cross-cutting
    # ---------------------------------------------------------------------
    {
        "_id": "cam.architecture.integration_patterns",
        "title": "Integration Patterns",
        "category": "architecture",
        "aliases": ["cam.architecture.integration_guidance"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["domain", "patterns"],
                    "properties": {
                        "domain": {"type": "string", "minLength": 1},
                        "patterns": {
                            "type": "array",
                            "default": [],
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["name", "applies_to", "rationale"],
                                "properties": {
                                    "name": {
                                        "type": "string",
                                        "enum": [
                                            "saga_orchestration",
                                            "saga_choreography",
                                            "outbox",
                                            "cqrs",
                                            "event_sourcing",
                                            "api_gateway",
                                            "service_mesh",
                                            "idempotent_consumer",
                                            "bulkhead",
                                            "circuit_breaker",
                                            "retry_with_backoff",
                                        ],
                                    },
                                    "applies_to": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "default": [],
                                        "description": "Service names or interaction pairs",
                                    },
                                    "rationale": {"type": "string", "minLength": 1},
                                    "notes": {"type": ["string", "null"]},
                                },
                            },
                        },
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": (
                        "Select integration patterns based on `cam.architecture.service_interaction_matrix` "
                        "and `cam.data.service_data_ownership`. Output strict JSON."
                    ),
                    "strict_json": True,
                },
                "depends_on": {
                    "hard": [
                        "cam.architecture.service_interaction_matrix",
                        "cam.data.service_data_ownership",
                    ],
                    "soft": [],
                },
                "identity": {"natural_key": ["domain"]},
                "examples": [
                    {
                        "domain": "Retail Equity Post-Trade",
                        "patterns": [
                            {
                                "name": "outbox",
                                "applies_to": ["trade-capture-svc"],
                                "rationale": "Ensure atomic write of Trade + TradeValidated event.",
                                "notes": "Publish from outbox table with retries and DLQ.",
                            }
                        ],
                    }
                ],
                "diagram_recipes": [],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
            }
        ],
    },
    {
        "_id": "cam.security.microservices_security_architecture",
        "title": "Microservices Security Architecture",
        "category": "security",
        "aliases": ["cam.security.svc_security_arch"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "domain",
                        "principles",
                        "service_to_service",
                        "edge_security",
                    ],
                    "properties": {
                        "domain": {"type": "string", "minLength": 1},
                        "principles": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": [],
                        },
                        "identity_provider": {"type": ["string", "null"]},
                        "edge_security": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["gateway", "authn", "authz"],
                            "properties": {
                                "gateway": {"type": "string", "minLength": 1},
                                "authn": {"type": "string", "minLength": 1},
                                "authz": {"type": "string", "minLength": 1},
                                "rate_limiting": {"type": ["string", "null"]},
                            },
                        },
                        "service_to_service": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["trust", "secrets", "network_controls"],
                            "properties": {
                                "trust": {
                                    "type": "string",
                                    "minLength": 1,
                                    "description": "e.g., mTLS via mesh, SPIFFE",
                                },
                                "secrets": {
                                    "type": "string",
                                    "minLength": 1,
                                    "description": "e.g., vault + rotation",
                                },
                                "network_controls": {
                                    "type": "string",
                                    "minLength": 1,
                                    "description": "e.g., zero trust policies",
                                },
                            },
                        },
                        "data_protection": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["encryption_at_rest", "encryption_in_transit"],
                            "properties": {
                                "encryption_at_rest": {
                                    "type": "string",
                                    "minLength": 1,
                                },
                                "encryption_in_transit": {
                                    "type": "string",
                                    "minLength": 1,
                                },
                                "pii_handling": {"type": ["string", "null"]},
                            },
                        },
                        "threats_and_mitigations": {
                            "type": "array",
                            "default": [],
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["threat", "mitigation"],
                                "properties": {
                                    "threat": {"type": "string", "minLength": 1},
                                    "mitigation": {"type": "string", "minLength": 1},
                                },
                            },
                        },
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": (
                        "Define security architecture using `cam.catalog.microservice_inventory`, "
                        "`cam.contract.service_api`, and `cam.asset.raina_input` non-functionals/constraints. "
                        "Output strict JSON."
                    ),
                    "strict_json": True,
                },
                "depends_on": {
                    "hard": [
                        "cam.catalog.microservice_inventory",
                        "cam.contract.service_api",
                        "cam.asset.raina_input",
                    ],
                    "soft": [],
                },
                "identity": {"natural_key": ["domain"]},
                "examples": [
                    {
                        "domain": "Retail Equity Post-Trade",
                        "principles": [
                            "least privilege",
                            "zero trust",
                            "secure by default",
                        ],
                        "identity_provider": "Keycloak",
                        "edge_security": {
                            "gateway": "API Gateway",
                            "authn": "OIDC (Auth Code + PKCE)",
                            "authz": "RBAC/ABAC via centralized policy engine",
                            "rate_limiting": "per-client and per-route quotas",
                        },
                        "service_to_service": {
                            "trust": "mTLS via service mesh",
                            "secrets": "Vault with automatic rotation",
                            "network_controls": "namespace policies + deny-by-default",
                        },
                        "data_protection": {
                            "encryption_at_rest": "AES-256 managed keys",
                            "encryption_in_transit": "TLS 1.2+ everywhere",
                            "pii_handling": "tokenization for sensitive identifiers",
                        },
                        "threats_and_mitigations": [
                            {
                                "threat": "token replay",
                                "mitigation": "short-lived tokens + mTLS + audience checks",
                            }
                        ],
                    }
                ],
                "diagram_recipes": [],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
            }
        ],
    },
    {
        "_id": "cam.observability.microservices_observability_spec",
        "title": "Microservices Observability Specification",
        "category": "observability",
        "aliases": ["cam.observability.spec"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["domain", "logs", "metrics", "traces", "slos"],
                    "properties": {
                        "domain": {"type": "string", "minLength": 1},
                        "logs": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["format", "correlation"],
                            "properties": {
                                "format": {"type": "string", "minLength": 1},
                                "correlation": {
                                    "type": "string",
                                    "minLength": 1,
                                    "description": "trace_id, request_id, etc.",
                                },
                                "pii_redaction": {"type": ["string", "null"]},
                            },
                        },
                        "metrics": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["golden_signals"],
                            "properties": {
                                "golden_signals": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "default": [
                                        "latency",
                                        "traffic",
                                        "errors",
                                        "saturation",
                                    ],
                                },
                                "custom_metrics": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "default": [],
                                },
                            },
                        },
                        "traces": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["propagation", "sampling"],
                            "properties": {
                                "propagation": {"type": "string", "minLength": 1},
                                "sampling": {"type": "string", "minLength": 1},
                            },
                        },
                        "slos": {
                            "type": "array",
                            "default": [],
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["service", "objective"],
                                "properties": {
                                    "service": {"type": "string", "minLength": 1},
                                    "objective": {
                                        "type": "string",
                                        "minLength": 1,
                                        "description": "e.g. p95<200ms, 99.9%",
                                    },
                                    "notes": {"type": ["string", "null"]},
                                },
                            },
                        },
                        "alerting": {
                            "type": "array",
                            "default": [],
                            "items": {"type": "string"},
                        },
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": (
                        "Define observability spec using `cam.catalog.microservice_inventory` and "
                        "`cam.architecture.service_interaction_matrix`. Output strict JSON."
                    ),
                    "strict_json": True,
                },
                "depends_on": {
                    "hard": [
                        "cam.catalog.microservice_inventory",
                        "cam.architecture.service_interaction_matrix",
                    ],
                    "soft": [],
                },
                "identity": {"natural_key": ["domain"]},
                "examples": [
                    {
                        "domain": "Retail Equity Post-Trade",
                        "logs": {
                            "format": "JSON",
                            "correlation": "trace_id + span_id",
                            "pii_redaction": "mask account_id",
                        },
                        "metrics": {
                            "golden_signals": [
                                "latency",
                                "traffic",
                                "errors",
                                "saturation",
                            ],
                            "custom_metrics": ["trades_validated_per_sec"],
                        },
                        "traces": {
                            "propagation": "W3C tracecontext",
                            "sampling": "head-based 10% + tail-based for errors",
                        },
                        "slos": [
                            {
                                "service": "trade-capture-svc",
                                "objective": "p95<200ms and 99.9% availability",
                            }
                        ],
                        "alerting": [
                            "error_rate>2% for 10m",
                            "p95_latency breach for 15m",
                        ],
                    }
                ],
                "diagram_recipes": [],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
            }
        ],
    },
    {
        "_id": "cam.deployment.microservices_topology",
        "title": "Microservices Deployment Topology",
        "category": "deployment",
        "aliases": [
            "cam.deployment.topology",
            "cam.deployment.microservices_deployment",
        ],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["domain", "runtime", "networking", "environments"],
                    "properties": {
                        "domain": {"type": "string", "minLength": 1},
                        "runtime": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["platform", "service_mesh"],
                            "properties": {
                                "platform": {
                                    "type": "string",
                                    "minLength": 1,
                                    "description": "e.g., Kubernetes",
                                },
                                "service_mesh": {
                                    "type": ["string", "null"],
                                    "description": "e.g., Istio, Linkerd",
                                },
                                "ingress": {
                                    "type": ["string", "null"],
                                    "description": "e.g., API Gateway / Ingress Controller",
                                },
                            },
                        },
                        "networking": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["segmentation", "east_west", "north_south"],
                            "properties": {
                                "segmentation": {"type": "string", "minLength": 1},
                                "east_west": {"type": "string", "minLength": 1},
                                "north_south": {"type": "string", "minLength": 1},
                            },
                        },
                        "environments": {
                            "type": "array",
                            "default": [],
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["name", "purpose"],
                                "properties": {
                                    "name": {
                                        "type": "string",
                                        "enum": ["dev", "test", "staging", "prod"],
                                    },
                                    "purpose": {"type": "string", "minLength": 1},
                                    "scaling": {"type": ["string", "null"]},
                                },
                            },
                        },
                        "dependencies": {
                            "type": "array",
                            "default": [],
                            "items": {"type": "string"},
                        },
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": (
                        "Define deployment topology using `cam.catalog.microservice_inventory` and "
                        "`cam.security.microservices_security_architecture`. Output strict JSON."
                    ),
                    "strict_json": True,
                },
                "depends_on": {
                    "hard": [
                        "cam.catalog.microservice_inventory",
                        "cam.security.microservices_security_architecture",
                    ],
                    "soft": ["cam.architecture.integration_patterns"],
                },
                "identity": {"natural_key": ["domain"]},
                "examples": [
                    {
                        "domain": "Retail Equity Post-Trade",
                        "runtime": {
                            "platform": "Kubernetes",
                            "service_mesh": "Istio",
                            "ingress": "API Gateway",
                        },
                        "networking": {
                            "segmentation": "namespace-per-domain",
                            "east_west": "mTLS in-mesh",
                            "north_south": "WAF + gateway auth",
                        },
                        "environments": [
                            {
                                "name": "dev",
                                "purpose": "developer integration testing",
                                "scaling": "minimal autoscaling",
                            },
                            {
                                "name": "prod",
                                "purpose": "customer-facing runtime",
                                "scaling": "HPA + multi-AZ",
                            },
                        ],
                        "dependencies": [
                            "Kafka",
                            "Postgres",
                            "Vault",
                            "Observability stack",
                        ],
                    }
                ],
                "diagram_recipes": [
                    {
                        "id": "topology",
                        "title": "Deployment Topology",
                        "view": "deployment",
                        "language": "mermaid",
                        "description": "High-level runtime topology including ingress, mesh, clusters, and external dependencies.",
                        "template": (
                            "flowchart TB\n"
                            "  %% Render runtime components: ingress/gateway, mesh, clusters, external deps\n"
                        ),
                        "prompt": None,
                        "renderer_hints": {"direction": "TB"},
                        "examples": [],
                        "depends_on": None,
                    }
                ],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
            }
        ],
    },
    {
        "_id": "cam.catalog.tech_stack_rankings",
        "title": "Tech Stack Rankings",
        "category": "catalog",
        "aliases": [
            "cam.catalog.stack_rankings",
            "cam.catalog.technology_recommendations",
        ],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["domain", "categories"],
                    "properties": {
                        "domain": {"type": "string", "minLength": 1},
                        "categories": {
                            "type": "array",
                            "default": [],
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["category", "ranked_options"],
                                "properties": {
                                    "category": {
                                        "type": "string",
                                        "enum": [
                                            "api",
                                            "messaging",
                                            "database",
                                            "cache",
                                            "service_mesh",
                                            "observability",
                                            "cicd",
                                            "secrets",
                                        ],
                                    },
                                    "ranked_options": {
                                        "type": "array",
                                        "default": [],
                                        "items": {
                                            "type": "object",
                                            "additionalProperties": False,
                                            "required": ["name", "rank", "reasoning"],
                                            "properties": {
                                                "name": {
                                                    "type": "string",
                                                    "minLength": 1,
                                                },
                                                "rank": {
                                                    "type": "integer",
                                                    "minimum": 1,
                                                },
                                                "reasoning": {
                                                    "type": "string",
                                                    "minLength": 1,
                                                },
                                                "tradeoffs": {
                                                    "type": ["string", "null"]
                                                },
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": (
                        "Rank tech choices based on integration patterns, deployment topology, and `cam.asset.raina_input` "
                        "constraints/tech_stack hints. Output strict JSON."
                    ),
                    "strict_json": True,
                },
                "depends_on": {
                    "hard": [
                        "cam.architecture.integration_patterns",
                        "cam.deployment.microservices_topology",
                        "cam.asset.raina_input",
                    ],
                    "soft": ["cam.observability.microservices_observability_spec"],
                },
                "identity": {"natural_key": ["domain"]},
                "examples": [
                    {
                        "domain": "Retail Equity Post-Trade",
                        "categories": [
                            {
                                "category": "messaging",
                                "ranked_options": [
                                    {
                                        "name": "Apache Kafka",
                                        "rank": 1,
                                        "reasoning": "Strong ecosystem for event-driven microservices.",
                                        "tradeoffs": "Operational overhead.",
                                    },
                                    {
                                        "name": "RabbitMQ",
                                        "rank": 2,
                                        "reasoning": "Simple queues and routing patterns.",
                                        "tradeoffs": "Less suited for long retention streams.",
                                    },
                                ],
                            }
                        ],
                    }
                ],
                "diagram_recipes": [],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
            }
        ],
    },
    # ---------------------------------------------------------------------
    # Synthesis (Primary Deliverable)
    # ---------------------------------------------------------------------
    {
        "_id": "cam.architecture.microservices_architecture",
        "title": "Microservices Architecture",
        "category": "architecture",
        "aliases": [
            "cam.architecture.microservices",
            "cam.architecture.target_microservices_architecture",
        ],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "domain",
                        "summary",
                        "services",
                        "contracts",
                        "cross_cutting",
                    ],
                    "properties": {
                        "domain": {"type": "string", "minLength": 1},
                        "summary": {"type": "string", "minLength": 1},
                        "services": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": [
                                "inventory_ref",
                                "interaction_matrix_ref",
                                "data_ownership_ref",
                            ],
                            "properties": {
                                "inventory_ref": {
                                    "type": "string",
                                    "minLength": 1,
                                    "description": "Artifact ref/id for cam.catalog.microservice_inventory",
                                },
                                "interaction_matrix_ref": {
                                    "type": "string",
                                    "minLength": 1,
                                    "description": "Artifact ref/id for cam.architecture.service_interaction_matrix",
                                },
                                "data_ownership_ref": {
                                    "type": "string",
                                    "minLength": 1,
                                    "description": "Artifact ref/id for cam.data.service_data_ownership",
                                },
                            },
                        },
                        "contracts": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["api_contract_ref", "event_catalog_ref"],
                            "properties": {
                                "api_contract_ref": {"type": "string", "minLength": 1},
                                "event_catalog_ref": {"type": "string", "minLength": 1},
                            },
                        },
                        "cross_cutting": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": [
                                "integration_patterns_ref",
                                "security_arch_ref",
                                "observability_ref",
                                "topology_ref",
                                "tech_stack_rankings_ref",
                            ],
                            "properties": {
                                "integration_patterns_ref": {
                                    "type": "string",
                                    "minLength": 1,
                                },
                                "security_arch_ref": {"type": "string", "minLength": 1},
                                "observability_ref": {"type": "string", "minLength": 1},
                                "topology_ref": {"type": "string", "minLength": 1},
                                "tech_stack_rankings_ref": {
                                    "type": "string",
                                    "minLength": 1,
                                },
                            },
                        },
                        "key_decisions": {
                            "type": "array",
                            "default": [],
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["decision", "rationale"],
                                "properties": {
                                    "decision": {"type": "string", "minLength": 1},
                                    "rationale": {"type": "string", "minLength": 1},
                                    "alternatives": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "default": [],
                                    },
                                },
                            },
                        },
                        "risks": {
                            "type": "array",
                            "default": [],
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["risk", "mitigation"],
                                "properties": {
                                    "risk": {"type": "string", "minLength": 1},
                                    "mitigation": {"type": "string", "minLength": 1},
                                },
                            },
                        },
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": (
                        "Assemble the final target architecture using the referenced microservices artifacts. "
                        "Produce a coherent summary and key decisions/risks. Output strict JSON."
                    ),
                    "strict_json": True,
                },
                "depends_on": {
                    "hard": [
                        "cam.catalog.microservice_inventory",
                        "cam.contract.service_api",
                        "cam.catalog.events",
                        "cam.data.service_data_ownership",
                        "cam.architecture.integration_patterns",
                        "cam.security.microservices_security_architecture",
                        "cam.observability.microservices_observability_spec",
                        "cam.deployment.microservices_topology",
                        "cam.catalog.tech_stack_rankings",
                    ],
                    "soft": [
                        "cam.domain.bounded_context_map",
                        "cam.domain.ubiquitous_language",
                    ],
                },
                "identity": {"natural_key": ["domain"]},
                "examples": [
                    {
                        "domain": "Retail Equity Post-Trade",
                        "summary": "Event-driven microservices aligned to bounded contexts with API Gateway at the edge and service mesh for mTLS.",
                        "services": {
                            "inventory_ref": "artifact:cam.catalog.microservice_inventory:latest",
                            "interaction_matrix_ref": "artifact:cam.architecture.service_interaction_matrix:latest",
                            "data_ownership_ref": "artifact:cam.data.service_data_ownership:latest",
                        },
                        "contracts": {
                            "api_contract_ref": "artifact:cam.contract.service_api:latest",
                            "event_catalog_ref": "artifact:cam.catalog.events:latest",
                        },
                        "cross_cutting": {
                            "integration_patterns_ref": "artifact:cam.architecture.integration_patterns:latest",
                            "security_arch_ref": "artifact:cam.security.microservices_security_architecture:latest",
                            "observability_ref": "artifact:cam.observability.microservices_observability_spec:latest",
                            "topology_ref": "artifact:cam.deployment.microservices_topology:latest",
                            "tech_stack_rankings_ref": "artifact:cam.catalog.tech_stack_rankings:latest",
                        },
                        "key_decisions": [
                            {
                                "decision": "Adopt outbox pattern for critical events",
                                "rationale": "Avoid dual-write inconsistencies",
                                "alternatives": ["best-effort publish"],
                            }
                        ],
                        "risks": [
                            {
                                "risk": "Operational complexity of Kafka + mesh",
                                "mitigation": "platform templates + SRE runbooks",
                            }
                        ],
                    }
                ],
                "diagram_recipes": [
                    {
                        "id": "microservices_arch",
                        "title": "Microservices Architecture Overview",
                        "view": "flowchart",
                        "language": "mermaid",
                        "description": "High-level view: edge gateway, services, event bus, and data stores.",
                        "template": (
                            "flowchart LR\n"
                            "  %% High-level view: services, gateway, event bus, data stores\n"
                        ),
                        "prompt": None,
                        "renderer_hints": {"direction": "LR"},
                        "examples": [],
                        "depends_on": None,
                    }
                ],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
            }
        ],
    },
    {
        "_id": "cam.governance.microservices_arch_guidance",
        "title": "Microservices Architecture Guidance",
        "category": "governance",
        "aliases": [
            "cam.documents.microservices-arch-guidance",
            "cam.doc.microservices_guidance",
            "cam.docs.microservices_arch_guidance",
            "cam.docs.microservices_architecture_guidance",
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
                    "system": 'You are to author a comprehensive **Architecture Guidance Document** for a *microservices* target architecture as the lead architect instructing delivery teams.\n\n# Grounding sources (MUST cite both)\n1) The section labeled exactly: `=== RUN INPUTS (authoritative, from request.inputs) ===` — contains AVC/FSS/PSS, FR/NFR, goals, constraints.\n2) The section labeled exactly: `=== DEPENDENCIES (discovered artifacts) ===` — already-staged CAM artifacts and their facts.\n\n# Output CONTRACT (STRICT)\n- Output **exactly one** JSON object. **No text before or after** the JSON.\n- The JSON object MUST include:\n\t - `name`: "Microservices Architecture Guidance"\n\t - `description`: one-line summary\n\t - `filename`: "microservices-architecture-guidance.md"\n\t - `mime_type`: "text/markdown"\n\t - `tags`: array of sensible tags, e.g. ["architecture","guidance","microservices"]\n\t - `content`: a **single string** that is a **valid GitHub-Flavored Markdown document** (GFM).\n- You MAY include additional metadata fields permitted by schema (e.g., `owner`, `revision`, `related_assets`, `metadata`, etc.), but **all prose MUST live inside `content`**.\n\n# Markdown FORMAT RULES (HARD)\n- Use proper Markdown headings only (`#`, `##`, `###` …). No ad-hoc banners or underlines.\n- Provide a title H1: `# Microservices Architecture Guidance`\n- Immediately follow with a metadata table (Owner, Version, Date, Scope, Out of Scope).\n- Provide a **Table of Contents** with **anchor links** to sections (GFM link style).\n- **Every diagram MUST be fenced** as:\n\t ```mermaid\n\t <valid mermaid>\n\t ```\n\t **CRITICAL:** Do NOT include a blank ` ``` ` fence before or after the ` ```mermaid` block. Flowcharts MUST use `flowchart TD` or `flowchart LR` syntax (NOT `gantt`). Use safe ASCII arrows `-->`.\n- When referencing facts from artifacts, cite inline like: *(from cam.catalog.microservice_inventory: services[0].name)*.\n- If a fact is unknown from RUN INPUTS or DEPENDENCIES, either omit it, or include it under **Assumptions**.\n\n# Document SECTIONS (REQUIRED)\n1. Executive Summary (context from AVC; recommended target style: event-driven vs sync-first)\n2. Domain Decomposition (ubiquitous language + bounded contexts; boundaries and anti-goals)\n3. Target Architecture Overview (high-level view and principles; mermaid optional)\n4. Service Inventory & Ownership (per bounded context; responsibilities; owned data; team alignment)\n5. API Design Guidance (API contracts, versioning, idempotency, error model, pagination)\n6. Eventing & Messaging Guidance (event catalog, naming, schemas, delivery semantics, DLQ)\n7. Service Interaction Model (sync vs async; interaction matrix; reliability patterns)\n8. Data Ownership & Consistency (database-per-service, consistency model, sharing strategy)\n9. Integration Patterns & Resilience (outbox, saga, retries, circuit breakers, bulkheads)\n10. Security Architecture (edge + service-to-service trust, secrets, zero trust, threat mitigations)\n11. Observability & SLOs (logs/metrics/traces, correlation, alerts, SLOs per service)\n12. Deployment Topology & Environments (runtime, mesh/ingress, networking, dev→prod strategy)\n13. Tech Stack Recommendations (rankings with rationale and tradeoffs, aligned to constraints)\n14. Delivery & Migration Plan (phases, cutover/testing strategy, rollback, org enablement)\n15. **ADRs** (3–6): Context → Decision → Consequences → Alternatives\n16. Risks & Mitigations, Assumptions, Open Questions\n17. Appendices (glossary, artifact references, example payloads, runbooks)\n\n# Tone & Constraints\n- Directive, precise, implementation-oriented; no hand-waving.\n- Prefer concise, accurate prose; separate **Facts** vs **Assumptions**.\n- All statements MUST be grounded in RUN INPUTS and/or DEPENDENCIES; explicitly label assumptions.\n\n# Self-Validation CHECKLIST (perform before emitting JSON)\n- [ ] Output is a **single JSON object**.\n- [ ] JSON contains a **string** field `content`.\n- [ ] `content` starts with `# Microservices Architecture Guidance`.\n- [ ] All diagrams (if any) are inside a **single** fenced block starting with ```mermaid and ending with ``` on their own lines.\n- [ ] No stray “mermaid” tokens outside fences.\n- [ ] Table of Contents contains anchor links that match headings.\n- [ ] Required sections 1–17 present.\n- [ ] File metadata fields set exactly as specified.\n\nNow produce the JSON.\n\n=== RUN INPUTS (authoritative, from request.inputs) ===\n{{RUN_INPUTS}}\n\n=== DEPENDENCIES (discovered artifacts) ===\n{{DEPENDENCIES}}',
                    "strict_json": True,
                },
                "depends_on": {
                    "hard": [
                        "cam.asset.raina_input",
                        "cam.domain.ubiquitous_language",
                        "cam.domain.bounded_context_map",
                        "cam.catalog.microservice_inventory",
                        "cam.contract.service_api",
                        "cam.catalog.events",
                        "cam.architecture.service_interaction_matrix",
                        "cam.data.service_data_ownership",
                        "cam.architecture.integration_patterns",
                        "cam.security.microservices_security_architecture",
                        "cam.observability.microservices_observability_spec",
                        "cam.deployment.microservices_topology",
                        "cam.catalog.tech_stack_rankings",
                        "cam.architecture.microservices_architecture",
                        "cam.deployment.microservices_migration_plan",
                    ],
                    "soft": [],
                },
                "identity": {"natural_key": ["filename", "revision"]},
                "examples": [
                    {
                        "name": "Microservices Architecture Guidance",
                        "description": "Directive architecture guidance grounded on discovered microservices artifacts and RUN INPUTS.",
                        "filename": "microservices-architecture-guidance.md",
                        "mime_type": "text/markdown",
                        "tags": ["architecture", "guidance", "microservices"],
                        "content": "# Microservices Architecture Guidance\n\n<!-- Example structure only; real content generated at runtime -->\n\n| Field | Value |\n|---|---|\n| Owner | Platform Architecture |\n| Version | 1.0 |\n| Date | 2026-02-17 |\n| Scope | Target microservices architecture and rollout guidance |\n| Out of Scope | Low-level code design and per-team sprint plans |\n\n## Table of Contents\n- [Executive Summary](#executive-summary)\n- [Domain Decomposition](#domain-decomposition)\n- [Target Architecture Overview](#target-architecture-overview)\n- [ADRs](#architecture-decision-records-adrs)\n- [Appendices](#appendices)\n\n## Executive Summary\n...\n",
                        "related_assets": [
                            {
                                "id": "cam.architecture.microservices_architecture",
                                "relation": "grounds",
                            },
                            {
                                "id": "cam.catalog.microservice_inventory",
                                "relation": "cites",
                            },
                            {
                                "id": "cam.architecture.service_interaction_matrix",
                                "relation": "cites",
                            },
                            {
                                "id": "cam.deployment.microservices_migration_plan",
                                "relation": "drives",
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
    # ---------------------------------------------------------------------
    # Delivery Plan
    # ---------------------------------------------------------------------
    {
        "_id": "cam.deployment.microservices_migration_plan",
        "title": "Microservices Migration / Rollout Plan",
        "category": "deployment",
        "aliases": ["cam.deployment.migration_plan", "cam.deployment.rollout_plan"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["domain", "phases"],
                    "properties": {
                        "domain": {"type": "string", "minLength": 1},
                        "phases": {
                            "type": "array",
                            "default": [],
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["name", "scope", "exit_criteria"],
                                "properties": {
                                    "name": {"type": "string", "minLength": 1},
                                    "scope": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "default": [],
                                    },
                                    "dependencies": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "default": [],
                                    },
                                    "risks": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "default": [],
                                    },
                                    "rollback_strategy": {"type": ["string", "null"]},
                                    "exit_criteria": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "default": [],
                                    },
                                },
                            },
                        },
                        "cutover_strategy": {
                            "type": ["string", "null"],
                            "description": "e.g., strangler fig, parallel run, big bang",
                        },
                        "testing_strategy": {
                            "type": ["string", "null"],
                            "description": "e.g., contract tests, canary, shadow traffic",
                        },
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": (
                        "Create a phased migration plan using `cam.architecture.microservices_architecture` "
                        "and `cam.asset.raina_input` constraints. Output strict JSON."
                    ),
                    "strict_json": True,
                },
                "depends_on": {
                    "hard": [
                        "cam.architecture.microservices_architecture",
                        "cam.asset.raina_input",
                    ],
                    "soft": [],
                },
                "identity": {"natural_key": ["domain"]},
                "examples": [
                    {
                        "domain": "Retail Equity Post-Trade",
                        "phases": [
                            {
                                "name": "Phase 1 - Establish platform foundation",
                                "scope": [
                                    "Kubernetes baseline",
                                    "CI/CD",
                                    "Observability stack",
                                    "Gateway + OIDC",
                                ],
                                "dependencies": ["Cloud account setup", "Networking"],
                                "risks": ["Platform delays"],
                                "rollback_strategy": "N/A (foundation work)",
                                "exit_criteria": [
                                    "Prod-ready cluster",
                                    "Golden path templates available",
                                ],
                            }
                        ],
                        "cutover_strategy": "strangler fig",
                        "testing_strategy": "consumer-driven contract tests + canary releases",
                    }
                ],
                "diagram_recipes": [],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
            }
        ],
    },
]


def seed() -> None:
    now = datetime.utcnow()
    for doc in KIND_DOCS:
        upsert_kind(doc, now=now)


if __name__ == "__main__":
    seed()
    print(f"Seeded {len(KIND_DOCS)} microservices kinds into registry.")

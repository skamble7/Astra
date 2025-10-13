from __future__ import annotations

import logging

from app.models import PackInputCreate
from app.services.pack_input_service import PackInputService

log = logging.getLogger("app.seeds.pack_inputs")


async def seed_pack_inputs() -> None:
    """
    Seed pack inputs.

    - Keeps the existing Renova input contract (form-based) AS IS.
    - Adds a new Astra Discovery input contract (AVC/FSS/PSS).
    """
    svc = PackInputService()

    # ─────────────────────────────────────────────────────────────
    # Existing seed (UNCHANGED)
    # ─────────────────────────────────────────────────────────────
    renova_target = PackInputCreate(
        id="input.renova.repo",  # keep the same ID to replace the existing one
        name="Renova – Minimal COBOL Pack Run Form",
        description=(
            "Form definition for a minimal COBOL pack run. Captures title, description, "
            "shallow clone option, repository (URL/branch/destination), and execution options. "
            "Frontends map this to the lower-level run inputs (e.g., inputs.repos[0], inputs.extra)."
        ),
        tags=["renova", "repo", "git", "inputs", "form"],
        json_schema={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://astra.example/schemas/minimal-cobol-pack-run-form.json",
            "title": "Minimal COBOL Pack Run – Form",
            "type": "object",
            "additionalProperties": False,
            "required": ["title", "repository"],
            "properties": {
                "title": {
                    "type": "string",
                    "title": "Title",
                    "minLength": 1,
                    "default": "Minimal COBOL Pack Run",
                    "description": "Human-friendly name of the run."
                },
                "description": {
                    "type": "string",
                    "title": "Description",
                    "default": "Clone + Parse using MCP servers",
                    "description": "Optional notes about the run."
                },
                "shallowClone": {
                    "type": "boolean",
                    "title": "Shallow clone",
                    "default": True,
                    "description": "Use a shallow git clone (e.g., --depth=1)."
                },
                "repository": {
                    "type": "object",
                    "title": "Repository",
                    "additionalProperties": False,
                    "required": ["gitUrl", "branch", "destination"],
                    "properties": {
                        "gitUrl": {
                            "type": "string",
                            "title": "Git URL",
                            "format": "uri",
                            "default": "https://github.com/aws-samples/aws-mainframe-modernization-carddemo",
                            "description": "HTTPS/SSH URL to the repository to clone."
                        },
                        "branch": {
                            "type": "string",
                            "title": "Branch",
                            "default": "main",
                            "minLength": 1,
                            "description": "Branch or ref to checkout."
                        },
                        "destination": {
                            "type": "string",
                            "title": "Local destination (folder)",
                            "default": "/mnt/src",
                            "minLength": 1,
                            "description": "Filesystem path where the repo will be cloned."
                        }
                    }
                },
                "options": {
                    "type": "object",
                    "title": "Options",
                    "additionalProperties": False,
                    "properties": {
                        "validate": {
                            "type": "boolean",
                            "title": "Validate",
                            "default": True,
                            "description": "Validate against the pack input schema before starting."
                        },
                        "strictJson": {
                            "type": "boolean",
                            "title": "Strict JSON",
                            "default": True,
                            "description": "Require strictly valid JSON when generating inputs."
                        }
                    }
                }
            }
        },
        # Remove existing example value(s)
        examples=[],
    )

    # Idempotent replace-by-id for existing Renova input
    try:
        existing = await svc.get(renova_target.id)
    except Exception:
        existing = None

    if existing:
        try:
            ok = await svc.delete(renova_target.id, actor="seed")
            if ok:
                log.info("[pack_inputs.seeds] replaced existing: %s", renova_target.id)
            else:
                log.warning("[pack_inputs.seeds] could not delete existing: %s (continuing)", renova_target.id)
        except Exception as e:
            log.warning("[pack_inputs.seeds] delete failed for %s: %s (continuing)", renova_target.id, e)

    created = await svc.create(renova_target, actor="seed")
    log.info("[pack_inputs.seeds] created: %s", created.id)

    # ─────────────────────────────────────────────────────────────
    # New Astra Discovery input (AVC/FSS/PSS)
    # ─────────────────────────────────────────────────────────────
    discovery_target = PackInputCreate(
        id="input.astra.discovery.avc-fss-pss",
        name="Astra – Discovery Inputs (AVC/FSS/PSS)",
        description=(
            "Input contract for Astra discovery runs combining AVC (vision/problem/goals/NFRs/context/"
            "constraints/assumptions/success criteria), FSS (feature/user stories), and PSS (architecture "
            "paradigm/style/tech stack), plus execution options. Mirrors StartDiscoveryRequest."
        ),
        tags=["astra", "discovery", "inputs", "avc", "fss", "pss"],
        json_schema={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://astra.example/schemas/astra-discovery-avc-fss-pss.json",
            "title": "Astra Discovery – StartDiscoveryRequest",
            "type": "object",
            "additionalProperties": False,
            "required": ["playbook_id", "workspace_id", "inputs"],
            "properties": {
                "playbook_id": {
                    "type": "string",
                    "title": "Playbook Id",
                    "minLength": 1
                },
                "workspace_id": {
                    "type": "string",
                    "title": "Workspace Id (UUID4)",
                    "format": "uuid"
                },
                "inputs": { "$ref": "#/$defs/DiscoveryInputs" },
                "options": { "$ref": "#/$defs/DiscoveryOptions" },
                "title": {
                    "type": ["string", "null"],
                    "maxLength": 200,
                    "description": "Human-friendly title for the run."
                },
                "description": {
                    "type": ["string", "null"],
                    "maxLength": 2000,
                    "description": "Optional description for the run."
                }
            },
            "$defs": {
                "AVCGoal": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "text"],
                    "properties": {
                        "id":   { "type": "string", "minLength": 1 },
                        "text": { "type": "string", "minLength": 1 },
                        "metric": { "type": ["string", "null"] }
                    }
                },
                "AVCNonFunctional": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["type", "target"],
                    "properties": {
                        "type":   { "type": "string", "minLength": 1 },
                        "target": { "type": "string", "minLength": 1 }
                    }
                },
                "AVCContext": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "domain": { "type": ["string", "null"] },
                        "actors": {
                            "type": "array",
                            "items": { "type": "string" },
                            "default": []
                        }
                    }
                },
                "AVCSuccessCriterion": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["kpi", "target"],
                    "properties": {
                        "kpi":    { "type": "string", "minLength": 1 },
                        "target": { "type": "string", "minLength": 1 }
                    }
                },
                "AVC": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "vision": {
                            "type": "array",
                            "items": { "type": "string" },
                            "default": []
                        },
                        "problem_statements": {
                            "type": "array",
                            "items": { "type": "string" },
                            "default": []
                        },
                        "goals": {
                            "type": "array",
                            "items": { "$ref": "#/$defs/AVCGoal" },
                            "default": []
                        },
                        "non_functionals": {
                            "type": "array",
                            "items": { "$ref": "#/$defs/AVCNonFunctional" },
                            "default": []
                        },
                        "constraints": {
                            "type": "array",
                            "items": { "type": "string" },
                            "default": []
                        },
                        "assumptions": {
                            "type": "array",
                            "items": { "type": "string" },
                            "default": []
                        },
                        "context": {
                            "allOf": [ { "$ref": "#/$defs/AVCContext" } ],
                            "default": {}
                        },
                        "success_criteria": {
                            "type": "array",
                            "items": { "$ref": "#/$defs/AVCSuccessCriterion" },
                            "default": []
                        }
                    },
                    "required": ["context"]
                },
                "FSSStory": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["key", "title"],
                    "properties": {
                        "key":   { "type": "string", "minLength": 1 },
                        "title": { "type": "string", "minLength": 1 },
                        "description": {
                            "oneOf": [
                                { "type": "string" },
                                { "type": "array", "items": { "type": "string" } },
                                { "type": "null" }
                            ],
                            "description": "Freeform text or bullet list."
                        },
                        "acceptance_criteria": {
                            "type": "array",
                            "items": { "type": "string" },
                            "default": []
                        },
                        "tags": {
                            "type": "array",
                            "items": { "type": "string" },
                            "description": "Structured tags like prefix:value (e.g., domain:auth).",
                            "default": []
                        }
                    }
                },
                "FSS": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "stories": {
                            "type": "array",
                            "items": { "$ref": "#/$defs/FSSStory" },
                            "default": []
                        }
                    },
                    "required": ["stories"]
                },
                "PSS": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["paradigm", "style", "tech_stack"],
                    "properties": {
                        "paradigm": { "type": "string", "minLength": 1 },
                        "style": {
                            "type": "array",
                            "items": { "type": "string" },
                            "default": []
                        },
                        "tech_stack": {
                            "type": "array",
                            "items": { "type": "string" },
                            "default": []
                        }
                    }
                },
                "DiscoveryInputs": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["avc", "fss", "pss"],
                    "properties": {
                        "avc": { "$ref": "#/$defs/AVC" },
                        "fss": { "$ref": "#/$defs/FSS" },
                        "pss": { "$ref": "#/$defs/PSS" }
                    }
                },
                "DiscoveryOptions": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "model":        { "type": ["string", "null"] },
                        "dry_run":      { "type": "boolean", "default": False },
                        "validate":     { "type": "boolean", "default": True },
                        "pack_key":     { "type": ["string", "null"] },
                        "pack_version": { "type": ["string", "null"] }
                    }
                }
            }
        },
        examples=[
            {
                "playbook_id": "playbook.astra.discovery.default",
                "workspace_id": "6c3f2a2b-19a8-4c79-9b9a-2c8a2f7e2a11",
                "title": "Astra Discovery – Payments Domain",
                "description": "Explore goals, scope, and architecture for next-gen payments.",
                "inputs": {
                    "avc": {
                        "vision": [
                            "Unified, real-time payments experience across channels",
                            "Reduce settlement time and operational risk"
                        ],
                        "problem_statements": [
                            "Batch-oriented legacy is causing high latency",
                            "Manual reconciliation increases errors and cost"
                        ],
                        "goals": [
                            { "id": "G1", "text": "Cut settlement time to < T+0", "metric": "avg_settlement_duration" },
                            { "id": "G2", "text": "99.95% uptime for core payment flows" }
                        ],
                        "non_functionals": [
                            { "type": "availability", "target": ">= 99.95%" },
                            { "type": "latency_p95", "target": "< 200ms" }
                        ],
                        "constraints": [
                            "PCI-DSS compliance",
                            "Must integrate with existing core banking APIs"
                        ],
                        "assumptions": [
                            "Traffic growth 2x over 12 months",
                            "Multi-region deployment feasible"
                        ],
                        "context": {
                            "domain": "payments",
                            "actors": ["customer", "merchant", "risk-engine", "settlement-service"]
                        },
                        "success_criteria": [
                            { "kpi": "chargeback_rate", "target": "< 0.2%" },
                            { "kpi": "operational_incidents_per_quarter", "target": "< 2" }
                        ]
                    },
                    "fss": {
                        "stories": [
                            {
                                "key": "PAY-101",
                                "title": "As a customer, I can pay with a saved card",
                                "description": [
                                    "Support card-on-file",
                                    "Handle 3DS challenge when required"
                                ],
                                "acceptance_criteria": [
                                    "Declined transactions return reason codes",
                                    "3DS step-up is audited"
                                ],
                                "tags": ["domain:payments", "capability:card-on-file"]
                            },
                            {
                                "key": "PAY-205",
                                "title": "As an analyst, I can view near-real-time settlement status",
                                "description": "Dashboard refresh <= 1 minute",
                                "acceptance_criteria": ["P95 API latency < 200ms"],
                                "tags": ["domain:analytics", "capability:settlement-tracking"]
                            }
                        ]
                    },
                    "pss": {
                        "paradigm": "event-driven microservices",
                        "style": ["saga", "hexagonal", "CQRS"],
                        "tech_stack": ["Kafka", "PostgreSQL", "gRPC", "OpenTelemetry"]
                    }
                },
                "options": {
                    "model": "gpt-4o-mini",
                    "dry_run": False,
                    "validate": True,
                    "pack_key": "pack.astra.discovery",
                    "pack_version": "1.0.0"
                }
            }
        ],
    )

    # Idempotent replace-by-id for new Astra input
    try:
        existing_discovery = await svc.get(discovery_target.id)
    except Exception:
        existing_discovery = None

    if existing_discovery:
        try:
            ok = await svc.delete(discovery_target.id, actor="seed")
            if ok:
                log.info("[pack_inputs.seeds] replaced existing: %s", discovery_target.id)
            else:
                log.warning("[pack_inputs.seeds] could not delete existing: %s (continuing)", discovery_target.id)
        except Exception as e:
            log.warning("[pack_inputs.seeds] delete failed for %s: %s (continuing)", discovery_target.id, e)

    created_discovery = await svc.create(discovery_target, actor="seed")
    log.info("[pack_inputs.seeds] created: %s", created_discovery.id)
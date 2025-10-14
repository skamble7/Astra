from __future__ import annotations

import logging

from app.models import PackInputCreate
from app.services.pack_input_service import PackInputService

log = logging.getLogger("app.seeds.pack_inputs")


async def seed_pack_inputs() -> None:
    """
    Seed pack inputs.

    - Keeps the existing Renova input contract (form-based) AS IS.
    - Replaces the Astra Discovery input contract with a form-style schema
      whose root requires only "inputs" so it works with the current input_resolver,
      which validates {"inputs": <...>} against the schema.
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
    # Astra Discovery input (AVC/FSS/PSS) — FORM-STYLE ROOT
    # ─────────────────────────────────────────────────────────────
    # IMPORTANT: Root requires ONLY "inputs" so input_resolver's validation of {"inputs": <...>} passes.
    discovery_target = PackInputCreate(
        id="input.astra.discovery.avc-fss-pss",
        name="Astra – Discovery Inputs (AVC/FSS/PSS) – Form",
        description=(
            "Form-style input contract for Astra discovery runs combining AVC (vision/problem/goals/NFRs/"
            "context/constraints/assumptions/success criteria), FSS (feature/user stories), and PSS "
            "(architecture paradigm/style/tech stack). Designed to validate a payload shaped as "
            '{"inputs": <DiscoveryInputs>}, matching the current input_resolver.'
        ),
        tags=["astra", "discovery", "inputs", "avc", "fss", "pss", "form"],
        json_schema={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://astra.example/schemas/astra-discovery-avc-fss-pss.form.json",
            "title": "Astra Discovery – Inputs Form",
            "type": "object",
            "additionalProperties": False,
            "required": ["inputs"],
            "properties": {
                # The resolver passes {"inputs": <DiscoveryInputs>} to validation.
                "inputs": {"$ref": "#/$defs/DiscoveryInputs"},
                # Keep options available but NOT required; the resolver won't include it in the validated object.
                "options": {"$ref": "#/$defs/DiscoveryOptions"}
            },
            "$defs": {
                "AVCGoal": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "text"],
                    "properties": {
                        "id": {"type": "string", "minLength": 1},
                        "text": {"type": "string", "minLength": 1},
                        "metric": {"type": ["string", "null"]}
                    }
                },
                "AVCNonFunctional": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["type", "target"],
                    "properties": {
                        "type": {"type": "string", "minLength": 1},
                        "target": {"type": "string", "minLength": 1}
                    }
                },
                "AVCContext": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "domain": {"type": ["string", "null"]},
                        "actors": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": []
                        }
                    }
                },
                "AVCSuccessCriterion": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["kpi", "target"],
                    "properties": {
                        "kpi": {"type": "string", "minLength": 1},
                        "target": {"type": "string", "minLength": 1}
                    }
                },
                "AVC": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "vision": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": []
                        },
                        "problem_statements": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": []
                        },
                        "goals": {
                            "type": "array",
                            "items": {"$ref": "#/$defs/AVCGoal"},
                            "default": []
                        },
                        "non_functionals": {
                            "type": "array",
                            "items": {"$ref": "#/$defs/AVCNonFunctional"},
                            "default": []
                        },
                        "constraints": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": []
                        },
                        "assumptions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": []
                        },
                        "context": {
                            "allOf": [{"$ref": "#/$defs/AVCContext"}],
                            "default": {}
                        },
                        "success_criteria": {
                            "type": "array",
                            "items": {"$ref": "#/$defs/AVCSuccessCriterion"},
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
                        "key": {"type": "string", "minLength": 1},
                        "title": {"type": "string", "minLength": 1},
                        "description": {
                            "oneOf": [
                                {"type": "string"},
                                {"type": "array", "items": {"type": "string"}},
                                {"type": "null"}
                            ],
                            "description": "Freeform text or bullet list."
                        },
                        "acceptance_criteria": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": []
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
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
                            "items": {"$ref": "#/$defs/FSSStory"},
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
                        "paradigm": {"type": "string", "minLength": 1},
                        "style": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": []
                        },
                        "tech_stack": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": []
                        }
                    }
                },
                "DiscoveryInputs": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["avc", "fss", "pss"],
                    "properties": {
                        "avc": {"$ref": "#/$defs/AVC"},
                        "fss": {"$ref": "#/$defs/FSS"},
                        "pss": {"$ref": "#/$defs/PSS"}
                    }
                },
                "DiscoveryOptions": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "model": {"type": ["string", "null"]},
                        "dry_run": {"type": "boolean", "default": False},
                        "validate": {"type": "boolean", "default": True},
                        "pack_key": {"type": ["string", "null"]},
                        "pack_version": {"type": ["string", "null"]}
                    }
                }
            }
        },
        # Example shaped exactly how the resolver validates: {"inputs": ...}
        examples=[
            {
                "inputs": {
                    "avc": {
                        "vision": [
                            "Modernize COBOL CardDemo into secure, scalable microservices",
                            "Retain core capabilities for back-office operations and batch"
                        ],
                        "problem_statements": ["Tightly coupled monolith impedes feature velocity"],
                        "goals": [
                            {"id": "G1", "text": "Microservices with clear bounded contexts", "metric": "services decomposed by domain"}
                        ],
                        "non_functionals": [
                            {"type": "performance", "target": "p95<200ms"}
                        ],
                        "constraints": ["cloud: aws"],
                        "assumptions": ["Greenfield microservices can coexist with legacy batch for a period"],
                        "context": {"domain": "Cards", "actors": ["Customer", "BackOfficeUser"]},
                        "success_criteria": [{"kpi": "deployment_frequency", "target": ">= daily"}]
                    },
                    "fss": {
                        "stories": [
                            {"key": "CARD-101", "title": "As a user, I can log in and navigate the portal"}
                        ]
                    },
                    "pss": {
                        "paradigm": "Service-Based",
                        "style": ["Microservices"],
                        "tech_stack": ["FastAPI", "MongoDB"]
                    }
                }
            }
        ],
    )

    # Idempotent replace-by-id for Astra input
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
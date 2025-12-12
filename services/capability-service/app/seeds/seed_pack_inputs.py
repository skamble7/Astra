from __future__ import annotations

import logging

from app.models import PackInputCreate
from app.services.pack_input_service import PackInputService

log = logging.getLogger("app.seeds.pack_inputs")


async def seed_pack_inputs() -> None:
    """
    Seed pack inputs.

    - Keeps (and replaces-by-id) the Renova input contract (form-based).
    - Keeps (and replaces-by-id) the Astra Discovery input contract with a form-style root {"inputs": ...}.
    - Keeps (and replaces-by-id) the Renova Workspace Summary input contract for generating a COBOL artifacts summary.
    - Keeps (and replaces-by-id) the Data Engineering Architecture Guidance input contract.
    - ADDS a new "Raina – User Stories Source URL" input contract that points to the Raina Input Service.
    """
    svc = PackInputService()

    # ─────────────────────────────────────────────────────────────
    # Renova – Minimal COBOL Pack Run Form (REPLACE-BY-ID)
    # ─────────────────────────────────────────────────────────────
    renova_target = PackInputCreate(
        id="input.renova.repo",
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
                            "default": "https://github.com/skamble7/CardDemo_minimal",
                            "description": "HTTPS/SSH URL to the repository to clone."
                        },
                        "branch": {
                            "type": "string",
                            "title": "Branch",
                            "default": "master",
                            "minLength": 1,
                            "description": "Branch or ref to checkout."
                        },
                        "destination": {
                            "type": "string",
                            "title": "Local destination (folder)",
                            "default": "/workspace",
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
        examples=[],
    )

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
    # Astra Discovery input (AVC/FSS/PSS) — FORM-STYLE ROOT (REPLACE-BY-ID)
    # ─────────────────────────────────────────────────────────────
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
                "inputs": {"$ref": "#/$defs/DiscoveryInputs"},
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
                        "actors": {"type": "array", "items": {"type": "string"}, "default": []}
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
                        "vision": {"type": "array", "items": {"type": "string"}, "default": []},
                        "problem_statements": {"type": "array", "items": {"type": "string"}, "default": []},
                        "goals": {"type": "array", "items": {"$ref": "#/$defs/AVCGoal"}, "default": []},
                        "non_functionals": {"type": "array", "items": {"$ref": "#/$defs/AVCNonFunctional"}, "default": []},
                        "constraints": {"type": "array", "items": {"type": "string"}, "default": []},
                        "assumptions": {"type": "array", "items": {"type": "string"}, "default": []},
                        "context": {"allOf": [{"$ref": "#/$defs/AVCContext"}], "default": {}},
                        "success_criteria": {"type": "array", "items": {"$ref": "#/$defs/AVCSuccessCriterion"}, "default": []}
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
                            ]
                        },
                        "acceptance_criteria": {"type": "array", "items": {"type": "string"}, "default": []},
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
                        "stories": {"type": "array", "items": {"$ref": "#/$defs/FSSStory"}, "default": []}
                    },
                    "required": ["stories"]
                },
                "PSS": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["paradigm", "style", "tech_stack"],
                    "properties": {
                        "paradigm": {"type": "string", "minLength": 1},
                        "style": {"type": "array", "items": {"type": "string"}, "default": []},
                        "tech_stack": {"type": "array", "items": {"type": "string"}, "default": []}
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
                        "non_functionals": [{"type": "performance", "target": "p95<200ms"}],
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

    # ─────────────────────────────────────────────────────────────
    # Renova – COBOL Workspace Summary (REPLACE-BY-ID)
    # ─────────────────────────────────────────────────────────────
    workspace_summary = PackInputCreate(
        id="input.renova.workspace_summary",
        name="Renova – COBOL Workspace Summary",
        description="Input contract to generate a single Markdown document summarizing COBOL artifacts for a given workspace.",
        tags=["renova", "cobol", "summary", "inputs", "form"],
        json_schema={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://astra.example/schemas/cobol-workspace-summary-input.json",
            "title": "COBOL Workspace Summary – Input",
            "type": "object",
            "additionalProperties": False,
            "required": ["workspace_id"],
            "properties": {
                "workspace_id": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Workspace identifier to summarize.",
                    "examples": ["0084b4c5-b11b-44d3-8ec3-d616dfa3e873"]
                },
                "kind_id": {
                    "type": "string",
                    "const": "cam.asset.cobol_artifacts_summary",
                    "description": "Fixed to the COBOL workspace document kind."
                }
            }
        },
        examples=[
            {
                "workspace_id": "0084b4c5-b11b-44d3-8ec3-d616dfa3e873",
                "kind_id": "cam.asset.cobol_artifacts_summary"
            }
        ],
        schema_guide=(
            "Call the MCP server to generate a single Markdown document summarizing COBOL artifacts for the given workspace.\n"
            "- **workspace_id** (required): The workspace whose artifacts will be summarized.\n"
            "- **kind_id** (fixed): `cam.asset.cobol_artifacts_summary`."
        ),
    )

    try:
        existing_ws = await svc.get(workspace_summary.id)
    except Exception:
        existing_ws = None

    if existing_ws:
        try:
            ok = await svc.delete(workspace_summary.id, actor="seed")
            if ok:
                log.info("[pack_inputs.seeds] replaced existing: %s", workspace_summary.id)
            else:
                log.warning("[pack_inputs.seeds] could not delete existing: %s (continuing)", workspace_summary.id)
        except Exception as e:
            log.warning("[pack_inputs.seeds] delete failed for %s: %s (continuing)", workspace_summary.id, e)

    created_ws = await svc.create(workspace_summary, actor="seed")
    log.info("[pack_inputs.seeds] created: %s", created_ws.id)

    # ─────────────────────────────────────────────────────────────
    # Data Engineering – Architecture Guidance (REPLACE-BY-ID)
    # ─────────────────────────────────────────────────────────────
    data_eng_arch = PackInputCreate(
        id="input.data-eng.architecture-guide",
        name="Data Engineering – Architecture Guidance",
        description=(
            "Input contract to generate a single Markdown architecture guidance document grounded on the workspace’s "
            "discovered data-engineering artifacts (FSS, PSS, AVC, models, patterns, jobs, lineage, governance, SLAs, "
            "observability, topology, tech stack, products, deployment)."
        ),
        tags=["data-eng", "architecture", "guidance", "inputs", "form"],
        json_schema={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://astra.example/schemas/data-eng-arch-guidance-input.json",
            "title": "Data Pipeline Architecture Guidance – Input",
            "type": "object",
            "additionalProperties": False,
            "required": ["workspace_id"],
            "properties": {
                "workspace_id": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Workspace identifier to analyze for guidance generation.",
                    "examples": ["0084b4c5-b11b-44d3-8ec3-d616dfa3e873"]
                },
                "kind_id": {
                    "type": "string",
                    "const": "cam.documents.data-pipeline-arch-guidance",
                    "description": "Fixed to the data-engineering architecture guidance document kind."
                }
            }
        },
        examples=[
            {
                "workspace_id": "0084b4c5-b11b-44d3-8ec3-d616dfa3e873",
                "kind_id": "cam.documents.data-pipeline-arch-guidance"
            }
        ],
        schema_guide=(
            "Request the MCP server to produce a comprehensive data-engineering architecture guidance document, grounded "
            "in artifacts already present in the workspace (patterns, datasets, contracts, lineage, governance, SLAs, "
            "orchestration, topology, stack rankings, data products, and deployment plan).\n"
            "- **workspace_id** (required): Target workspace to read artifacts from.\n"
            "- **kind_id** (fixed): `cam.documents.data-pipeline-arch-guidance`."
        ),
    )

    try:
        existing_arch = await svc.get(data_eng_arch.id)
    except Exception:
        existing_arch = None

    if existing_arch:
        try:
            ok = await svc.delete(data_eng_arch.id, actor="seed")
            if ok:
                log.info("[pack_inputs.seeds] replaced existing: %s", data_eng_arch.id)
            else:
                log.warning("[pack_inputs.seeds] could not delete existing: %s (continuing)", data_eng_arch.id)
        except Exception as e:
            log.warning("[pack_inputs.seeds] delete failed for %s: %s (continuing)", data_eng_arch.id, e)

    created_arch = await svc.create(data_eng_arch, actor="seed")
    log.info("[pack_inputs.seeds] created: %s", created_arch.id)

    # ─────────────────────────────────────────────────────────────
    # NEW: Raina – User Stories Source URL (REPLACE-BY-ID)
    # ─────────────────────────────────────────────────────────────
    stories_url_input = PackInputCreate(
        id="input.raina.user-stories-url",
        name="Raina – User Stories Source URL",
        description=(
            "Input contract providing the URL endpoint that returns user stories (e.g., AVC, FSS, PSS) "
            "to be used by the Raina package."
        ),
        tags=["raina", "inputs", "user-stories", "url", "fetch"],
        json_schema={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://astra.example/schemas/raina-user-stories-url-input.json",
            "title": "Raina – User Stories Source URL",
            "type": "object",
            "additionalProperties": False,
            "required": ["stories_url"],
            "properties": {
                "stories_url": {
                    "type": "string",
                    "format": "uri",
                    "minLength": 1,
                    "title": "User Stories URL",
                    "description": "HTTP endpoint exposing user stories consumed by the Raina package.",
                    "default": "http://host.docker.internal:9023/raina-input/data-pipeline-arch%40v1.0",
                    "examples": [
                        "http://host.docker.internal:9023/raina-input/data-pipeline-arch%40v1.0"
                    ]
                }
            }
        },
        examples=[
            {
                "stories_url": "http://host.docker.internal:9023/raina-input/data-pipeline-arch%40v1.0"
            }
        ],
        schema_guide=(
            "Provide a single URL for the Raina package to fetch user stories (and related AVC/FSS/PSS). "
            "This service is typically backed by the Raina Input Service (`/raina-input/{pack_id}`)."
        ),
    )

    try:
        existing_stories = await svc.get(stories_url_input.id)
    except Exception:
        existing_stories = None

    if existing_stories:
        try:
            ok = await svc.delete(stories_url_input.id, actor="seed")
            if ok:
                log.info("[pack_inputs.seeds] replaced existing: %s", stories_url_input.id)
            else:
                log.warning("[pack_inputs.seeds] could not delete existing: %s (continuing)", stories_url_input.id)
        except Exception as e:
            log.warning("[pack_inputs.seeds] delete failed for %s: %s (continuing)", stories_url_input.id, e)

    created_stories = await svc.create(stories_url_input, actor="seed")
    log.info("[pack_inputs.seeds] created: %s", created_stories.id)
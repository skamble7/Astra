# app/seeds/seed_microservices_capabilities.py
from __future__ import annotations

import inspect
import logging

from app.models import GlobalCapabilityCreate, LlmExecution
from app.services import CapabilityService

log = logging.getLogger("app.seeds.microservices_capabilities")


async def _try_wipe_all(svc: CapabilityService) -> bool:
    """
    Best-effort collection wipe without relying on list_all().
    Tries common method names; returns True if any succeeded.
    """
    candidates = [
        "delete_all",
        "purge_all",
        "purge",
        "truncate",
        "clear",
        "reset",
        "drop_all",
        "wipe_all",
    ]
    for name in candidates:
        method = getattr(svc, name, None)
        if callable(method):
            try:
                result = method()
                if inspect.isawaitable(result):
                    await result
                log.info("[capability.seeds.microservices] wiped existing via CapabilityService.%s()", name)
                return True
            except Exception as e:
                log.warning("[capability.seeds.microservices] %s() failed: %s", name, e)
    return False


def _llm_cap(
    _id: str,
    name: str,
    description: str,
    produces_kinds: list[str],
    tags: list[str] | None = None,
) -> GlobalCapabilityCreate:
    """
    Standard LLM-based capability definition (OpenAI, api_key).
    """
    return GlobalCapabilityCreate(
        id=_id,
        name=name,
        description=description,
        tags=tags or ["astra", "raina", "microservices"],
        parameters_schema=None,
        produces_kinds=produces_kinds,
        agent=None,
        execution=LlmExecution(
            mode="llm",
            llm_config={
                "provider": "openai",
                "model": "gpt-4o-mini",
                "base_url": None,
                "organization": None,
                "headers": {},
                "query_params": {},
                "timeout_sec": 90,
                "retry": None,
                "parameters": {"temperature": 0, "top_p": None, "max_tokens": 4000},
                "auth": {
                    "method": "api_key",
                    "alias_token": None,
                    "alias_user": None,
                    "alias_password": None,
                    "alias_key": "PROVIDER_API_KEY",
                },
            },
            io=None,
            config_ref="dev.llm.openai.fast",
        ),
    )


def _mcp_cap_microservices_guidance() -> GlobalCapabilityCreate:
    """
    MCP-based capability to generate cam.documents.microservices-arch-guidance.

    NOTE: We use GlobalCapabilityCreate.model_validate(...) so we do not need to import
    MCP-specific Pydantic models in seed code; this matches the shape already stored
    in Mongo for your data-eng MCP capability.
    """
    return GlobalCapabilityCreate.model_validate(
        {
            "id": "cap.microservices.generate-arch-guidance",
            "name": "Generate Microservices Architecture Guidance Document",
            "description": (
                "Calls the MCP server to produce a Markdown microservices architecture guidance document grounded on "
                "discovered microservices artifacts and RUN INPUTS; emits cam.documents.microservices-arch-guidance "
                "with standard file metadata (and optional pre-signed download info)."
            ),
            "tags": ["microservices", "docs", "guidance", "mcp", "raina", "astra"],
            "parameters_schema": None,
            "produces_kinds": ["cam.documents.microservices-arch-guidance"],
            "agent": None,
            "execution": {
                "mode": "mcp",
                "transport": {
                    "kind": "http",
                    "base_url": "http://host.docker.internal:8002",
                    "headers": {},
                    "auth": {
                        "method": "none",
                        "alias_token": None,
                        "alias_user": None,
                        "alias_password": None,
                        "alias_key": None,
                    },
                    "timeout_sec": 180,
                    "verify_tls": False,
                    "retry": {"max_attempts": 2, "backoff_ms": 250, "jitter_ms": 50},
                    "health_path": "/health",
                    "protocol_path": "/mcp",
                },
                "tool_calls": [
                    {
                        "tool": "generate.workspace.document",
                        "args_schema": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["workspace_id"],
                            "properties": {
                                "workspace_id": {
                                    "type": "string",
                                    "minLength": 1,
                                    "description": "Workspace identifier whose discovered artifacts ground the guidance document.",
                                },
                                "kind_id": {
                                    "type": "string",
                                    "const": "cam.documents.microservices-arch-guidance",
                                    "description": "Driver kind for the document generation.",
                                },
                            },
                        },
                        "output_kinds": ["cam.documents.microservices-arch-guidance"],
                        "result_schema": None,
                        "timeout_sec": 3600,
                        "retries": 1,
                        "expects_stream": False,
                        "cancellable": True,
                    }
                ],
                "discovery": {
                    "validate_tools": True,
                    "validate_resources": False,
                    "validate_prompts": False,
                    "fail_fast": True,
                },
                "connection": {"singleton": True, "share_across_steps": True},
                "io": {
                    "input_contract": {
                        "json_schema": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["workspace_id"],
                            "properties": {
                                "workspace_id": {
                                    "type": "string",
                                    "minLength": 1,
                                    "description": (
                                        "Workspace identifier whose artifacts will be used to ground the microservices "
                                        "architecture guidance document."
                                    ),
                                    "examples": ["0084b4c5-b11b-44d3-8ec3-d616dfa3e873"],
                                },
                                "kind_id": {
                                    "type": "string",
                                    "const": "cam.documents.microservices-arch-guidance",
                                    "description": "Fixed to the microservices architecture guidance document kind.",
                                },
                            },
                        },
                        "schema_guide": (
                            "Call the MCP server to generate a single Markdown microservices architecture guidance "
                            "document grounded on the workspace's discovered artifacts and RUN INPUTS.\n"
                            "- **workspace_id** (required): The workspace to analyze.\n"
                            "- **kind_id** (fixed): `cam.documents.microservices-arch-guidance`."
                        ),
                    },
                    "output_contract": {
                        "artifact_type": "cam",
                        "kinds": ["cam.documents.microservices-arch-guidance"],
                        "result_schema": None,
                        "schema_guide": (
                            "The MCP server returns one artifact of kind `cam.documents.microservices-arch-guidance` "
                            "with file metadata and links:\n"
                            "- `storage_uri` and `download_url` (may be pre-signed).\n"
                            "- If pre-signed, `download_expires_at` may be present.\n"
                            "- Other fields include `filename`, `path`, `size_bytes`, `mime_type`, etc."
                        ),
                        "extra_schema": {"type": "object", "additionalProperties": True},
                    },
                },
            },
        }
    )


async def seed_microservices_capabilities() -> None:
    """
    Seeds microservices-architecture discovery capabilities.

    Notes:
    - cap.raina.fetch_input is reused and is seeded elsewhere (do not duplicate here).
    - This file seeds both LLM-based capabilities and the MCP-based guidance document capability.
    """
    log.info("[capability.seeds.microservices] Begin")

    svc = CapabilityService()

    # Optional wipe (best-effort; falls back to replace-by-id below)
    wiped = await _try_wipe_all(svc)
    if not wiped:
        log.info("[capability.seeds.microservices] No wipe method found; proceeding with replace-by-id")

    targets: list[GlobalCapabilityCreate] = [
        # ---- Domain decomposition ----
        _llm_cap(
            "cap.discover.ubiquitous_language",
            "Discover Ubiquitous Language",
            "Derives a concise ubiquitous language from cam.inputs.raina (AVC/FSS/PSS).",
            ["cam.domain.ubiquitous_language"],
            tags=["astra", "raina", "microservices", "domain"],
        ),
        _llm_cap(
            "cap.discover.bounded_contexts",
            "Discover Bounded Contexts",
            "Discovers bounded contexts and relationships using cam.inputs.raina and cam.domain.ubiquitous_language.",
            ["cam.domain.bounded_context_map"],
            tags=["astra", "raina", "microservices", "domain", "ddd"],
        ),
        _llm_cap(
            "cap.discover.microservices",
            "Discover Candidate Microservices",
            "Derives candidate microservices aligned to bounded contexts from cam.domain.bounded_context_map.",
            ["cam.catalog.microservice_inventory"],
            tags=["astra", "raina", "microservices", "service-design"],
        ),
        # ---- Contracts & interactions ----
        _llm_cap(
            "cap.define.service_apis",
            "Define Service API Contracts",
            "Defines APIs per service using cam.catalog.microservice_inventory and cam.inputs.raina user stories and constraints.",
            ["cam.api.service_api_contract"],
            tags=["astra", "raina", "microservices", "contracts", "api"],
        ),
        _llm_cap(
            "cap.define.event_catalog",
            "Define Event Catalog",
            "Defines domain events for services using cam.catalog.microservice_inventory and cam.domain.ubiquitous_language.",
            ["cam.events.event_catalog"],
            tags=["astra", "raina", "microservices", "events"],
        ),
        _llm_cap(
            "cap.define.data_ownership",
            "Define Service Data Ownership",
            "Assigns data ownership boundaries and persistence strategy per service using cam.catalog.microservice_inventory and cam.inputs.raina.",
            ["cam.data.service_data_ownership"],
            tags=["astra", "raina", "microservices", "data"],
        ),
        _llm_cap(
            "cap.map.service_interactions",
            "Map Service Interactions",
            "Maps service interactions based on service APIs and events (sync/async, direction, contracts).",
            ["cam.architecture.service_interaction_matrix"],
            tags=["astra", "raina", "microservices", "interactions"],
        ),
        # ---- Cross-cutting & synthesis ----
        _llm_cap(
            "cap.select.integration_patterns",
            "Select Integration Patterns",
            "Selects integration patterns (sync/async, saga, outbox, retries, idempotency) using interactions and data ownership.",
            ["cam.architecture.integration_patterns"],
            tags=["astra", "raina", "microservices", "integration"],
        ),
        _llm_cap(
            "cap.define.security_architecture",
            "Define Microservices Security Architecture",
            "Defines identity, edge security, service-to-service trust, data protection, and mitigations using service inventory, API contracts, and inputs.",
            ["cam.security.microservices_security_architecture"],
            tags=["astra", "raina", "microservices", "security"],
        ),
        _llm_cap(
            "cap.define.observability_spec",
            "Define Microservices Observability Spec",
            "Defines logs/metrics/traces, SLOs, and alerting using service inventory and interaction matrix.",
            ["cam.observability.microservices_observability_spec"],
            tags=["astra", "raina", "microservices", "observability"],
        ),
        _llm_cap(
            "cap.define.deployment_topology",
            "Define Microservices Deployment Topology",
            "Defines runtime topology, networking, environments, and dependencies using service inventory and security architecture.",
            ["cam.deployment.microservices_topology"],
            tags=["astra", "raina", "microservices", "deployment"],
        ),
        _llm_cap(
            "cap.rank.tech_stack",
            "Rank Tech Stack (Microservices)",
            "Ranks tech choices aligned to integration patterns, deployment topology, and cam.inputs.raina constraints/tech hints.",
            ["cam.catalog.tech_stack_rankings"],
            tags=["astra", "raina", "microservices", "tech-stack"],
        ),
        _llm_cap(
            "cap.assemble.microservices_architecture",
            "Assemble Microservices Architecture",
            "Synthesizes the end-to-end microservices architecture from all preceding artifacts into the primary deliverable.",
            ["cam.architecture.microservices_architecture"],
            tags=["astra", "raina", "microservices", "synthesis"],
        ),
        # ---- Delivery plan ----
        _llm_cap(
            "cap.plan.migration_rollout",
            "Plan Microservices Migration / Rollout",
            "Creates a phased migration and rollout plan using the final architecture and cam.inputs.raina constraints.",
            ["cam.deployment.microservices_migration_plan"],
            tags=["astra", "raina", "microservices", "migration"],
        ),
        # ---- NEW: Guidance document (MCP) ----
        _mcp_cap_microservices_guidance(),
    ]

    # Replace-by-id creation (idempotent)
    created = 0
    for cap in targets:
        try:
            existing = await svc.get(cap.id)
            if existing:
                try:
                    await svc.delete(cap.id, actor="seed")
                    log.info("[capability.seeds.microservices] replaced: %s (deleted old)", cap.id)
                except AttributeError:
                    log.warning(
                        "[capability.seeds.microservices] delete() not available; attempting create() which may fail on unique ID"
                    )
        except Exception:
            pass

        await svc.create(cap, actor="seed")
        log.info("[capability.seeds.microservices] created: %s", cap.id)
        created += 1

    log.info("[capability.seeds.microservices] Done (created=%d)", created)

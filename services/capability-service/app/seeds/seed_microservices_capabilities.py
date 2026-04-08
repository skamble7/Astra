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
            llm_config_ref="dev.llm.openai.fast",
        ),
    )


def _mcp_cap_microservices_guidance() -> GlobalCapabilityCreate:
    """
    MCP-based capability to generate cam.governance.microservices_arch_guidance.

    NOTE: We use GlobalCapabilityCreate.model_validate(...) so we do not need to import
    MCP-specific Pydantic models in seed code; this matches the shape already stored
    in Mongo for your data-eng MCP capability.
    """
    return GlobalCapabilityCreate.model_validate(
        {
            "id": "cap.architecture.generate_guidance",
            "name": "Generate Microservices Architecture Guidance Document",
            "description": (
                "Calls the MCP server to produce a Markdown microservices architecture guidance document grounded on "
                "discovered microservices artifacts and RUN INPUTS; emits cam.governance.microservices_arch_guidance "
                "with standard file metadata (and optional pre-signed download info)."
            ),
            "tags": ["microservices", "docs", "guidance", "mcp", "raina", "astra"],
            "parameters_schema": None,
            "produces_kinds": ["cam.governance.microservices_arch_guidance"],
            "agent": None,
            "execution": {
                "mode": "mcp",
                "transport": {
                    "kind": "http",
                    "base_url": "http://host.docker.internal:8004",
                    "timeout_sec": 180,
                    "verify_tls": False,
                    "protocol_path": "/mcp",
                },
                "tool_name": "generate_microservices_arch_guidance",
            },
        }
    )


async def seed_microservices_capabilities() -> None:
    """
    Seeds microservices-architecture discovery capabilities.

    Notes:
    - cap.asset.fetch_raina_input is reused and is seeded elsewhere (do not duplicate here).
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
            "cap.domain.discover_ubiquitous_language",
            "Discover Ubiquitous Language",
            "Derives a concise ubiquitous language from cam.asset.raina_input (AVC/FSS/PSS).",
            ["cam.domain.ubiquitous_language"],
            tags=["astra", "raina", "microservices", "domain"],
        ),
        _llm_cap(
            "cap.domain.discover_bounded_contexts",
            "Discover Bounded Contexts",
            "Discovers bounded contexts and relationships using cam.asset.raina_input and cam.domain.ubiquitous_language.",
            ["cam.domain.bounded_context_map"],
            tags=["astra", "raina", "microservices", "domain", "ddd"],
        ),
        _llm_cap(
            "cap.architecture.discover_microservices",
            "Discover Candidate Microservices",
            "Derives candidate microservices aligned to bounded contexts from cam.domain.bounded_context_map.",
            ["cam.catalog.microservice_inventory"],
            tags=["astra", "raina", "microservices", "service-design"],
        ),
        # ---- Contracts & interactions ----
        _llm_cap(
            "cap.contract.define_service_apis",
            "Define Service API Contracts",
            "Defines APIs per service using cam.catalog.microservice_inventory and cam.asset.raina_input user stories and constraints.",
            ["cam.contract.service_api"],
            tags=["astra", "raina", "microservices", "contracts", "api"],
        ),
        _llm_cap(
            "cap.contract.define_event_catalog",
            "Define Event Catalog",
            "Defines domain events for services using cam.catalog.microservice_inventory and cam.domain.ubiquitous_language.",
            ["cam.catalog.events"],
            tags=["astra", "raina", "microservices", "events"],
        ),
        _llm_cap(
            "cap.data.define_ownership",
            "Define Service Data Ownership",
            "Assigns data ownership boundaries and persistence strategy per service using cam.catalog.microservice_inventory and cam.asset.raina_input.",
            ["cam.data.service_data_ownership"],
            tags=["astra", "raina", "microservices", "data"],
        ),
        _llm_cap(
            "cap.architecture.map_service_interactions",
            "Map Service Interactions",
            "Maps service interactions based on service APIs and events (sync/async, direction, contracts).",
            ["cam.architecture.service_interaction_matrix"],
            tags=["astra", "raina", "microservices", "interactions"],
        ),
        # ---- Cross-cutting & synthesis ----
        _llm_cap(
            "cap.architecture.select_integration_patterns",
            "Select Integration Patterns",
            "Selects integration patterns (sync/async, saga, outbox, retries, idempotency) using interactions and data ownership.",
            ["cam.architecture.integration_patterns"],
            tags=["astra", "raina", "microservices", "integration"],
        ),
        _llm_cap(
            "cap.security.define_architecture",
            "Define Microservices Security Architecture",
            "Defines identity, edge security, service-to-service trust, data protection, and mitigations using service inventory, API contracts, and inputs.",
            ["cam.security.microservices_security_architecture"],
            tags=["astra", "raina", "microservices", "security"],
        ),
        _llm_cap(
            "cap.observability.define_spec",
            "Define Microservices Observability Spec",
            "Defines logs/metrics/traces, SLOs, and alerting using service inventory and interaction matrix.",
            ["cam.observability.microservices_observability_spec"],
            tags=["astra", "raina", "microservices", "observability"],
        ),
        _llm_cap(
            "cap.deployment.define_topology",
            "Define Microservices Deployment Topology",
            "Defines runtime topology, networking, environments, and dependencies using service inventory and security architecture.",
            ["cam.deployment.microservices_topology"],
            tags=["astra", "raina", "microservices", "deployment"],
        ),
        _llm_cap(
            "cap.catalog.rank_tech_stack",
            "Rank Tech Stack (Microservices)",
            "Ranks tech choices aligned to integration patterns, deployment topology, and cam.asset.raina_input constraints/tech hints.",
            ["cam.catalog.tech_stack_rankings"],
            tags=["astra", "raina", "microservices", "tech-stack"],
        ),
        _llm_cap(
            "cap.architecture.assemble_microservices",
            "Assemble Microservices Architecture",
            "Synthesizes the end-to-end microservices architecture from all preceding artifacts into the primary deliverable.",
            ["cam.architecture.microservices_architecture"],
            tags=["astra", "raina", "microservices", "synthesis"],
        ),
        # ---- Delivery plan ----
        _llm_cap(
            "cap.deployment.plan_migration",
            "Plan Microservices Migration / Rollout",
            "Creates a phased migration and rollout plan using the final architecture and cam.asset.raina_input constraints.",
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

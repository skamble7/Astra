# app/seeds/seed_microservices_capabilities.py
from __future__ import annotations

import logging
import inspect

from app.models import (
    GlobalCapabilityCreate,
    LlmExecution,
)
from app.services import CapabilityService

log = logging.getLogger("app.seeds.microservices_capabilities")


async def _try_wipe_all(svc: CapabilityService) -> bool:
    """
    Best-effort collection wipe without relying on list_all().
    Tries common method names; returns True if any succeeded.
    """
    candidates = [
        "delete_all", "purge_all", "purge", "truncate", "clear",
        "reset", "drop_all", "wipe_all"
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
                    "alias_key": "OPENAI_API_KEY",
                },
            },
            io=None,
        ),
    )


async def seed_microservices_capabilities() -> None:
    """
    Seeds ONLY microservices-architecture discovery LLM capabilities.
    Note: cap.raina.fetch_input is reused and is seeded elsewhere (do not duplicate here).
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

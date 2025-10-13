# services/capability-registry/app/seeds/capabilities_raina.py
from __future__ import annotations

import logging
import inspect

from app.models import (
    GlobalCapabilityCreate,
    LlmExecution,
)
from app.services import CapabilityService

log = logging.getLogger("app.seeds.capabilities_raina")


async def _try_wipe_all(svc: CapabilityService) -> bool:
    """
    Try to clear the collection via common wipe methods.
    Returns True if any succeeded.
    """
    candidates = ["delete_all", "purge_all", "purge", "truncate", "clear", "reset", "drop_all", "wipe_all"]
    for name in candidates:
        method = getattr(svc, name, None)
        if callable(method):
            try:
                result = method()
                if inspect.isawaitable(result):
                    await result
                log.info("[capability_raina.seeds] wiped existing via CapabilityService.%s()", name)
                return True
            except Exception as e:
                log.warning("[capability_raina.seeds] %s() failed: %s", name, e)
    return False


async def seed_capabilities_raina() -> None:
    """
    Seeds the RainaV2 discovery and design capabilities.
    Adapted for Astra’s GlobalCapability model using LLM execution.
    """
    log.info("[capability_raina.seeds] Begin")

    svc = CapabilityService()

    # Optional: wipe existing entries for clean dev seeding
    wiped = await _try_wipe_all(svc)
    if not wiped:
        log.info("[capability_raina.seeds] No wipe method found; continuing with replace-by-id")

    LLM_DEFAULT = LlmExecution(
        mode="llm",
        llm_config={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "parameters": {"temperature": 0, "max_tokens": 2000},
            "auth": {"method": "api_key", "alias_key": "OPENAI_API_KEY"},
        },
    )

    # ─────────────────────────────────────────────────────────────
    # RainaV2 Discovery + Design Capabilities (now pure LLM)
    # ─────────────────────────────────────────────────────────────
    targets = [
        GlobalCapabilityCreate(
            id="cap.discover.context_map",
            name="Discover Context Map",
            description="Identify bounded contexts and their relationships within the domain.",
            tags=["raina", "discovery", "context-map"],
            parameters_schema=None,
            produces_kinds=["cam.diagram.context"],
            agent=None,
            execution=LLM_DEFAULT,
        ),
        GlobalCapabilityCreate(
            id="cap.data.dictionary",
            name="Domain Dictionary",
            description="Derive ubiquitous language and key domain terms from business and technical inputs.",
            tags=["raina", "discovery", "data", "dictionary"],
            produces_kinds=["cam.data.dictionary"],
            agent=None,
            execution=LLM_DEFAULT,
        ),
        GlobalCapabilityCreate(
            id="cap.catalog.services",
            name="Build Service Catalog",
            description="Identify service boundaries and compile a catalog of core and supporting services.",
            tags=["raina", "catalog", "services"],
            produces_kinds=["cam.catalog.service"],
            agent=None,
            execution=LLM_DEFAULT,
        ),
        GlobalCapabilityCreate(
            id="cap.generate.class_diagram",
            name="Generate Class/ER Diagram",
            description="Generate logical class or entity-relationship diagrams for key domain entities.",
            tags=["raina", "diagram", "class"],
            produces_kinds=["cam.diagram.class"],
            agent=None,
            execution=LLM_DEFAULT,
        ),
        GlobalCapabilityCreate(
            id="cap.diagram.activity",
            name="Key Flows (Activity)",
            description="Produce BPMN-like activity diagrams representing key business workflows.",
            tags=["raina", "diagram", "activity"],
            produces_kinds=["cam.diagram.activity"],
            agent=None,
            execution=LLM_DEFAULT,
        ),
        GlobalCapabilityCreate(
            id="cap.contracts.event",
            name="Event Contracts",
            description="Define event-driven interfaces, topics, and message schemas for asynchronous communication.",
            tags=["raina", "contracts", "event"],
            produces_kinds=["cam.contract.event"],
            agent=None,
            execution=LLM_DEFAULT,
        ),
        GlobalCapabilityCreate(
            id="cap.contracts.api",
            name="API Contracts",
            description="Generate service API contracts including endpoints, operations, and payloads.",
            tags=["raina", "contracts", "api"],
            produces_kinds=["cam.contract.api"],
            agent=None,
            execution=LLM_DEFAULT,
        ),
        GlobalCapabilityCreate(
            id="cap.data.model",
            name="Logical Data Model",
            description="Derive the logical data model from discovered entities, attributes, and relationships.",
            tags=["raina", "data", "model"],
            produces_kinds=["cam.data.model"],
            agent=None,
            execution=LLM_DEFAULT,
        ),
        GlobalCapabilityCreate(
            id="cap.diagram.deployment",
            name="Deployment View",
            description="Generate deployment topology showing services, environments, and communication paths.",
            tags=["raina", "diagram", "deployment"],
            produces_kinds=["cam.diagram.deployment"],
            agent=None,
            execution=LLM_DEFAULT,
        ),
        GlobalCapabilityCreate(
            id="cap.asset.service_inventory",
            name="Service Inventory",
            description="Generate a canonical inventory of services identified across the discovered landscape.",
            tags=["raina", "asset", "inventory", "service"],
            produces_kinds=["cam.asset.service_inventory"],
            agent=None,
            execution=LLM_DEFAULT,
        ),
        GlobalCapabilityCreate(
            id="cap.asset.dependency_inventory",
            name="Dependency Inventory",
            description="Document service-to-service dependencies and upstream/downstream relationships.",
            tags=["raina", "asset", "inventory", "dependency"],
            produces_kinds=["cam.asset.dependency_inventory"],
            agent=None,
            execution=LLM_DEFAULT,
        ),
        GlobalCapabilityCreate(
            id="cap.asset.api_inventory",
            name="API Inventory",
            description="Produce a flattened inventory of all discovered APIs and endpoints.",
            tags=["raina", "asset", "inventory", "api"],
            produces_kinds=["cam.asset.api_inventory"],
            agent=None,
            execution=LLM_DEFAULT,
        ),
    ]

    created = 0
    for cap in targets:
        try:
            existing = await svc.get(cap.id)
            if existing:
                try:
                    await svc.delete(cap.id, actor="seed")
                    log.info("[capability_raina.seeds] replaced existing capability: %s", cap.id)
                except Exception:
                    log.warning("[capability_raina.seeds] delete() failed for %s; proceeding with create()", cap.id)
        except Exception:
            pass  # not found

        await svc.create(cap, actor="seed")
        created += 1
        log.info("[capability_raina.seeds] created capability: %s", cap.id)

    log.info("[capability_raina.seeds] Completed (created=%d)", created)
# services/capability-service/app/seeds/seed_microservices_packs.py
from __future__ import annotations

import logging
import os
from typing import Iterable

from app.models import CapabilityPackCreate
from app.services import PackService  # ✅ fixed import

log = logging.getLogger("app.seeds.packs.microservices")


async def _replace_by_id(svc: PackService, pack: CapabilityPackCreate) -> None:
    """
    Idempotently replace a pack by its id (key@version).
    """
    try:
        existing = await svc.get(pack.id)
    except Exception:
        existing = None

    if existing:
        try:
            ok = await svc.delete(pack.id, actor="seed")
            if ok:
                log.info("[packs.seeds.microservices] replaced existing: %s", pack.id)
            else:
                log.warning("[packs.seeds.microservices] delete returned falsy for %s; continuing to create", pack.id)
        except Exception as e:
            log.warning("[packs.seeds.microservices] delete failed for %s: %s (continuing)", pack.id, e)

    created = await svc.create(pack, actor="seed")
    log.info("[packs.seeds.microservices] created: %s", created.id)


async def _publish_all(svc: PackService, ids: Iterable[str]) -> None:
    for pack_id in ids:
        try:
            published = await svc.publish(pack_id, actor="seed")
            if published:
                log.info("[packs.seeds.microservices] published: %s", published.id)
        except Exception as e:
            log.warning("[packs.seeds.microservices] publish failed for %s: %s", pack_id, e)


async def seed_microservices_packs() -> None:
    """
    Seeds RAINA Microservices Architecture Discovery capability pack.

    v1.0.0:
      - Uses input contract: input.raina.user-stories-url
      - First step fetches cam.asset.raina_input via shared MCP capability cap.asset.fetch_raina_input
      - Then runs the microservices discovery chain and emits cam.architecture.microservices_architecture
      - Adds an OPTIONAL guidance playbook that generates cam.governance.microservices_arch_guidance (MCP)
        from a workspace_id-based input contract (input.microservices.architecture-guide).
    """
    svc = PackService()

    publish_on_seed = os.getenv("PACK_SEED_PUBLISH", "1").lower() in ("1", "true", "yes")

    pack_v1_0_0 = CapabilityPackCreate(
        id="raina-microservices-arch@v1.0.0",
        key="raina-microservices-arch",
        version="v1.0.0",
        title="Microservices Architecture Discovery Pack (v1.0.0)",
        description=(
            "Discovers a target microservices architecture from Raina inputs (AVC/FSS/PSS). "
            "The playbook fetches and validates the input via MCP, decomposes the domain into bounded contexts, "
            "derives candidate microservices, defines service APIs and domain events, assigns data ownership, "
            "maps interactions, selects integration patterns, defines security/observability/deployment topology, "
            "ranks the tech stack, synthesizes the final architecture, and produces a phased migration plan."
        ),
        capability_ids=[
            "cap.asset.fetch_raina_input",
            "cap.domain.discover_ubiquitous_language",
            "cap.domain.discover_bounded_contexts",
            "cap.architecture.discover_microservices",
            "cap.contract.define_service_apis",
            "cap.contract.define_event_catalog",
            "cap.data.define_ownership",
            "cap.architecture.map_service_interactions",
            "cap.architecture.select_integration_patterns",
            "cap.security.define_architecture",
            "cap.observability.define_spec",
            "cap.deployment.define_topology",
            "cap.catalog.rank_tech_stack",
            "cap.architecture.assemble_microservices",
            "cap.deployment.plan_migration",
            # ✅ NEW: MCP guidance capability (produces cam.governance.microservices_arch_guidance)
            "cap.architecture.generate_guidance",
        ],
        agent_capability_ids=[
            "cap.diagram.mermaid",
        ],
        playbooks=[
            {
                "id": "pb.raina.microservices-arch.v1",
                "name": "Microservices Architecture Discovery (v1.0.0)",
                "description": (
                    "End-to-end flow: fetch inputs → ubiquitous language → bounded contexts → microservices → "
                    "APIs/events/data ownership → interactions → integration patterns → security → observability → "
                    "deployment topology → tech stack ranking → assemble architecture → migration plan."
                ),
                "steps": [
                    {
                        "id": "fetch-1",
                        "name": "Fetch Raina Input (AVC/FSS/PSS)",
                        "capability_id": "cap.asset.fetch_raina_input",
                        "description": "Fetch and validate the Raina input JSON (emits cam.asset.raina_input).",
                    },
                    {
                        "id": "dom-1",
                        "name": "Discover Ubiquitous Language",
                        "capability_id": "cap.domain.discover_ubiquitous_language",
                        "description": None,
                    },
                    {
                        "id": "dom-2",
                        "name": "Discover Bounded Contexts",
                        "capability_id": "cap.domain.discover_bounded_contexts",
                        "description": None,
                    },
                    {
                        "id": "svc-1",
                        "name": "Discover Candidate Microservices",
                        "capability_id": "cap.architecture.discover_microservices",
                        "description": None,
                    },
                    {
                        "id": "ctr-1",
                        "name": "Define Service API Contracts",
                        "capability_id": "cap.contract.define_service_apis",
                        "description": None,
                    },
                    {
                        "id": "ctr-2",
                        "name": "Define Event Catalog",
                        "capability_id": "cap.contract.define_event_catalog",
                        "description": None,
                    },
                    {
                        "id": "data-1",
                        "name": "Define Service Data Ownership",
                        "capability_id": "cap.data.define_ownership",
                        "description": None,
                    },
                    {
                        "id": "int-1",
                        "name": "Map Service Interactions",
                        "capability_id": "cap.architecture.map_service_interactions",
                        "description": None,
                    },
                    {
                        "id": "int-2",
                        "name": "Select Integration Patterns",
                        "capability_id": "cap.architecture.select_integration_patterns",
                        "description": None,
                    },
                    {
                        "id": "sec-1",
                        "name": "Define Security Architecture",
                        "capability_id": "cap.security.define_architecture",
                        "description": None,
                    },
                    {
                        "id": "obs-1",
                        "name": "Define Observability Spec",
                        "capability_id": "cap.observability.define_spec",
                        "description": None,
                    },
                    {
                        "id": "dep-1",
                        "name": "Define Deployment Topology",
                        "capability_id": "cap.deployment.define_topology",
                        "description": None,
                    },
                    {
                        "id": "stk-1",
                        "name": "Rank Tech Stack",
                        "capability_id": "cap.catalog.rank_tech_stack",
                        "description": None,
                    },
                    {
                        "id": "asm-1",
                        "name": "Assemble Microservices Architecture",
                        "capability_id": "cap.architecture.assemble_microservices",
                        "description": None,
                    },
                    {
                        "id": "mig-1",
                        "name": "Plan Migration / Rollout",
                        "capability_id": "cap.deployment.plan_migration",
                        "description": None,
                    },
                ],
            },
            # ✅ NEW: Guidance-only playbook (mirrors data-pipeline guidance pattern)
            {
                "id": "pb.raina.microservices-arch.guidance.v1",
                "name": "Microservices Architecture Guidance (v1)",
                "description": (
                    "Generate a comprehensive, prose-style microservices architecture guidance document grounded in the "
                    "artifacts produced by the discovery flow (services, APIs/events, interactions, security, observability, "
                    "topology, tech stack rankings, final architecture, migration plan, etc.)."
                ),
                "steps": [
                    {
                        "id": "guide-1",
                        "name": "Generate Microservices Architecture Guidance Document",
                        "capability_id": "cap.architecture.generate_guidance",
                        "description": None,
                    }
                ],
            },
        ],
        status="published",
        created_by="seed",
        updated_by="seed",
    )

    await _replace_by_id(svc, pack_v1_0_0)

    if publish_on_seed:
        await _publish_all(svc, ids=("raina-microservices-arch@v1.0.0",))

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

    v1.0:
      - Uses input contract: input.raina.user-stories-url
      - First step fetches cam.inputs.raina via shared MCP capability cap.raina.fetch_input
      - Then runs the microservices discovery chain and emits cam.architecture.microservices_architecture
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
        # Uses the same URL-based input contract used by the data-pipeline v1.1 pack
        pack_input_ids=[
            "input.raina.user-stories-url",
        ],
        # Capabilities used by this pack (includes shared MCP capability)
        capability_ids=[
            "cap.raina.fetch_input",
            "cap.discover.ubiquitous_language",
            "cap.discover.bounded_contexts",
            "cap.discover.microservices",
            "cap.define.service_apis",
            "cap.define.event_catalog",
            "cap.define.data_ownership",
            "cap.map.service_interactions",
            "cap.select.integration_patterns",
            "cap.define.security_architecture",
            "cap.define.observability_spec",
            "cap.define.deployment_topology",
            "cap.rank.tech_stack",
            "cap.assemble.microservices_architecture",
            "cap.plan.migration_rollout",
        ],
        # Optional agent capabilities (mirror your existing pattern)
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
                "input_id": "input.raina.user-stories-url",
                "steps": [
                    {
                        "id": "fetch-1",
                        "name": "Fetch Raina Input (AVC/FSS/PSS)",
                        "capability_id": "cap.raina.fetch_input",
                        "description": "Fetch and validate the Raina input JSON (emits cam.inputs.raina).",
                    },
                    {
                        "id": "dom-1",
                        "name": "Discover Ubiquitous Language",
                        "capability_id": "cap.discover.ubiquitous_language",
                    },
                    {
                        "id": "dom-2",
                        "name": "Discover Bounded Contexts",
                        "capability_id": "cap.discover.bounded_contexts",
                    },
                    {
                        "id": "svc-1",
                        "name": "Discover Candidate Microservices",
                        "capability_id": "cap.discover.microservices",
                    },
                    {
                        "id": "ctr-1",
                        "name": "Define Service API Contracts",
                        "capability_id": "cap.define.service_apis",
                    },
                    {
                        "id": "ctr-2",
                        "name": "Define Event Catalog",
                        "capability_id": "cap.define.event_catalog",
                    },
                    {
                        "id": "data-1",
                        "name": "Define Service Data Ownership",
                        "capability_id": "cap.define.data_ownership",
                    },
                    {
                        "id": "int-1",
                        "name": "Map Service Interactions",
                        "capability_id": "cap.map.service_interactions",
                    },
                    {
                        "id": "int-2",
                        "name": "Select Integration Patterns",
                        "capability_id": "cap.select.integration_patterns",
                    },
                    {
                        "id": "sec-1",
                        "name": "Define Security Architecture",
                        "capability_id": "cap.define.security_architecture",
                    },
                    {
                        "id": "obs-1",
                        "name": "Define Observability Spec",
                        "capability_id": "cap.define.observability_spec",
                    },
                    {
                        "id": "dep-1",
                        "name": "Define Deployment Topology",
                        "capability_id": "cap.define.deployment_topology",
                    },
                    {
                        "id": "stk-1",
                        "name": "Rank Tech Stack",
                        "capability_id": "cap.rank.tech_stack",
                    },
                    {
                        "id": "asm-1",
                        "name": "Assemble Microservices Architecture",
                        "capability_id": "cap.assemble.microservices_architecture",
                    },
                    {
                        "id": "mig-1",
                        "name": "Plan Migration / Rollout",
                        "capability_id": "cap.plan.migration_rollout",
                    },
                ],
            }
        ],
        status="published",
        created_by="seed",
        updated_by="seed",
    )

    await _replace_by_id(svc, pack_v1_0_0)

    if publish_on_seed:
        await _publish_all(svc, ids=("raina-microservices-arch@v1.0.0",))

from __future__ import annotations

import logging
import os

from app.models import CapabilityPackCreate, Playbook, PlaybookStep
from app.services import PackService

log = logging.getLogger("app.seeds.packs.raina")


async def _delete_pack_if_exists(svc: PackService, key: str, version: str) -> None:
    """
    Best-effort delete/replace-by-id like other seeds, tolerant of different service method signatures.
    """
    try:
        existing = await svc.get_by_key_version(key, version)
    except Exception:
        existing = None
    if not existing:
        return
    for meth_name in ("delete", "remove", "archive"):
        m = getattr(svc, meth_name, None)
        if callable(m):
            try:
                try:
                    await m(f"{key}@{version}", actor="seed")
                    log.info("[capability.seeds.packs.raina] %s('%s@%s') ok", meth_name, key, version)
                    return
                except TypeError:
                    try:
                        await m(existing.id, actor="seed")
                        log.info("[capability.seeds.packs.raina] %s(id=%s) ok", meth_name, existing.id)
                        return
                    except TypeError:
                        await m(key, version, actor="seed")
                        log.info("[capability.seeds.packs.raina] %s('%s','%s') ok", meth_name, key, version)
                        return
            except Exception as e:
                log.warning("[capability.seeds.packs.raina] %s failed: %s", meth_name, e)
    log.warning(
        "[capability.seeds.packs.raina] Could not delete existing pack %s@%s; continuing with create()",
        key, version,
    )


async def _create_and_maybe_publish(svc: PackService, payload: CapabilityPackCreate, publish_on_seed: bool) -> None:
    created = await svc.create(payload, actor="seed")
    log.info(
        "[capability.seeds.packs.raina] created: %s@%s (id=%s)",
        payload.key, payload.version, getattr(created, "id", None),
    )
    if publish_on_seed:
        published = await svc.publish(f"{payload.key}@{payload.version}", actor="seed")
        if published:
            log.info("[capability.seeds.packs.raina] published: %s", published.id)
        else:
            log.warning(
                "[capability.seeds.packs.raina] publish failed or pack not found for %s@%s",
                payload.key, payload.version,
            )
    else:
        log.info(
            "[capability.seeds.packs.raina] publish skipped via env for %s@%s",
            payload.key, payload.version,
        )


async def seed_packs_raina() -> None:
    """
    Seeds the RainaV2 'Service-Based + Microservices Pack (Lean v1.4)'.

    Uses Raina capability IDs (LLM-only, OpenAI/api_key in capability registry) and the
    new artifact kinds. Pack input contract: 'input.astra.discovery.avc-fss-pss'.
    """
    log.info("[capability.seeds.packs.raina] Begin")

    publish_on_seed = os.getenv("PACK_SEED_PUBLISH", "1") in ("1", "true", "True")
    svc = PackService()

    pack_key = "svc-micro"
    pack_version = "v1.4"
    pack_input_id = "input.astra.discovery.avc-fss-pss"  # per request

    # Remove any existing pack@version to ensure clean replace
    await _delete_pack_if_exists(svc, pack_key, pack_version)

    # Playbook (exact flow from RainaV2 with minimal params; keep ids stable)
    pb_micro_plus = Playbook(
        id="pb.micro.plus",
        name="Microservices Discovery (Lean v1.4)",
        description="Essentials-only flow using validated CAM kinds.",
        steps=[
            PlaybookStep(
                id="ctx-1",
                name="Discover Context Map",
                capability_id="cap.discover.context_map",
                description=None,
                params={},
            ),
            PlaybookStep(
                id="dict-1",
                name="Domain Dictionary",
                capability_id="cap.data.dictionary",
                description=None,
                params={},
            ),
            PlaybookStep(
                id="svc-1",
                name="Build Service Catalog",
                capability_id="cap.catalog.services",
                description=None,
                params={},
            ),
            PlaybookStep(
                id="erd-1",
                name="Generate Class/ER Diagram",
                capability_id="cap.generate.class_diagram",
                description=None,
                params={},
            ),
            PlaybookStep(
                id="act-1",
                name="Key Flows (Activity)",
                capability_id="cap.diagram.activity",
                description=None,
                params={
                    # Optional guidance example from the pack; keep lightweight
                    "flows": ["Card Activation", "Refund"],
                },
            ),
            PlaybookStep(
                id="evt-1",
                name="Event Contracts",
                capability_id="cap.contracts.event",
                description=None,
                params={},
            ),
            PlaybookStep(
                id="api-1",
                name="API Contracts",
                capability_id="cap.contracts.api",
                description=None,
                params={},
            ),
            PlaybookStep(
                id="data-1",
                name="Logical Data Model",
                capability_id="cap.data.model",
                description=None,
                params={},
            ),
            PlaybookStep(
                id="dep-1",
                name="Deployment View",
                capability_id="cap.diagram.deployment",
                description=None,
                params={},
            ),
            PlaybookStep(
                id="inv-1",
                name="Service Inventory",
                capability_id="cap.asset.service_inventory",
                description=None,
                params={},
            ),
            PlaybookStep(
                id="inv-2",
                name="Dependency Inventory",
                capability_id="cap.asset.dependency_inventory",
                description=None,
                params={},
            ),
            PlaybookStep(
                id="inv-3",
                name="API Inventory",
                capability_id="cap.asset.api_inventory",
                description=None,
                params={},
            ),
        ],
    )

    # Capability IDs for the pack (must align with those seeded from RainaV2)
    capability_ids = [
        "cap.discover.context_map",
        "cap.data.dictionary",
        "cap.catalog.services",
        "cap.generate.class_diagram",
        "cap.diagram.activity",
        "cap.contracts.event",
        "cap.contracts.api",
        "cap.data.model",
        "cap.diagram.deployment",
        "cap.asset.service_inventory",
        "cap.asset.dependency_inventory",
        "cap.asset.api_inventory",
    ]

    payload = CapabilityPackCreate(
        key=pack_key,
        version=pack_version,
        title="Service-Based + Microservices Pack (Lean v1.4)",
        description=(
            "Focused microservices discovery using only validated CAM kinds: "
            "context → services → interactions → contracts → data → deployment → inventories."
        ),
        pack_input_id=pack_input_id,
        capability_ids=capability_ids,
        # No agent-only capabilities specified for this pack; add later if needed
        agent_capability_ids=["cap.diagram.mermaid"],
        playbooks=[pb_micro_plus],
    )

    await _create_and_maybe_publish(svc, payload, publish_on_seed)
    log.info("[capability.seeds.packs.raina] Done (seeded %s@%s)", pack_key, pack_version)
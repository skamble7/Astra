# services/capability-service/app/seeds/seed_data_pipeline_packs.py
from __future__ import annotations

import logging
import os
from typing import Iterable

from app.models import CapabilityPackCreate
from app.services import PackService  # ✅ fixed import

log = logging.getLogger("app.seeds.packs.data_pipeline")


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
                log.info("[packs.seeds.data_pipeline] replaced existing: %s", pack.id)
            else:
                log.warning("[packs.seeds.data_pipeline] delete returned falsy for %s; continuing to create", pack.id)
        except Exception as e:
            log.warning("[packs.seeds.data_pipeline] delete failed for %s: %s (continuing)", pack.id, e)

    created = await svc.create(pack, actor="seed")
    log.info("[packs.seeds.data_pipeline] created: %s", created.id)


async def _publish_all(svc: PackService, ids: Iterable[str]) -> None:
    for pack_id in ids:
        try:
            published = await svc.publish(pack_id, actor="seed")
            if published:
                log.info("[packs.seeds.data_pipeline] published: %s", published.id)
        except Exception as e:
            log.warning("[packs.seeds.data_pipeline] publish failed for %s: %s", pack_id, e)


async def seed_data_pipeline_packs() -> None:
    """
    Seeds Data Engineering Architecture Discovery capability packs.

    Maintains v1.0 (no MCP fetch step) and adds v1.1 where the first step fetches
    the Raina input JSON via the new MCP capability `cap.raina.fetch_input`.
    """
    svc = PackService()  # ✅ fixed class name

    publish_on_seed = os.getenv("PACK_SEED_PUBLISH", "1").lower() in ("1", "true", "yes")

    # -----------------------------
    # v1.0 (existing, unchanged)
    # -----------------------------
    pack_v1_0 = CapabilityPackCreate(
        id="data-pipeline-arch@v1.0",
        key="data-pipeline-arch",
        version="v1.0",
        title="Data Engineering Architecture Discovery Pack (v1.0)",
        description=(
            "Generates an implementation-ready data pipeline architecture from AVC/FSS/PSS inputs, including patterns "
            "(batch/stream/lambda/event-driven), dataset contracts, transformations, lineage, governance, SLAs/observability, "
            "orchestration, topology, tech stack ranking, data products, a concrete deployment plan, and an optional "
            "architecture guidance document grounded in discovered artifacts."
        ),
        # v1.0 used the generic discovery input id
        pack_input_ids=[
            "input.astra.discovery.avc-fss-pss",
            "input.data-eng.architecture-guide",
        ],
        capability_ids=[
            "cap.inventory.sources_sinks",
            "cap.discover.business_flows",
            "cap.discover.logical_data_model",
            "cap.select.pipeline_patterns",
            "cap.define.dataset_contracts",
            "cap.spec.transforms",
            "cap.spec.batch_job",
            "cap.spec.stream_job",
            "cap.orchestration.define",
            "cap.map.lineage",
            "cap.policy.governance",
            "cap.policy.access_control",
            "cap.policy.masking",
            "cap.sla.quality",
            "cap.observability.define",
            "cap.diagram.topology",
            "cap.rank.tech_stack",
            "cap.catalog.data_products",
            "cap.assemble.pipeline_architecture",
            "cap.plan.deployment",
            # include guidance capability for guidance playbook
            "cap.data-eng.generate-arch-diagram",
        ],
        agent_capability_ids=[
            "cap.diagram.mermaid",
        ],
        playbooks=[
            {
                "id": "pb.data-arch.v1",
                "name": "Data Engineering Architecture Discovery (v1)",
                "description": (
                    "End-to-end flow: sources → flows → model → patterns → contracts → transforms → jobs → orchestration → "
                    "lineage → governance & security → SLAs/observability → topology → stack ranking → data products → "
                    "assembly → deployment plan."
                ),
                "input_id": "input.astra.discovery.avc-fss-pss",
                "steps": [
                    {"id": "src-1", "name": "Inventory Sources & Sinks", "capability_id": "cap.inventory.sources_sinks"},
                    {"id": "flow-1", "name": "Discover Business Flows", "capability_id": "cap.discover.business_flows"},
                    {"id": "model-1", "name": "Derive Logical Data Model", "capability_id": "cap.discover.logical_data_model"},
                    {"id": "pat-1", "name": "Select Pipeline Architecture Patterns", "capability_id": "cap.select.pipeline_patterns"},
                    {"id": "contract-1", "name": "Define Dataset Contracts", "capability_id": "cap.define.dataset_contracts"},
                    {"id": "tfm-1", "name": "Specify Transformations", "capability_id": "cap.spec.transforms"},
                    {"id": "batch-1", "name": "Generate Batch Job Spec", "capability_id": "cap.spec.batch_job"},
                    {"id": "stream-1", "name": "Generate Stream Job Spec", "capability_id": "cap.spec.stream_job"},
                    {"id": "orc-1", "name": "Define Orchestration", "capability_id": "cap.orchestration.define"},
                    {"id": "lin-1", "name": "Map Lineage", "capability_id": "cap.map.lineage"},
                    {"id": "gov-1", "name": "Derive Governance Policies", "capability_id": "cap.policy.governance"},
                    {"id": "sec-1", "name": "Access Control", "capability_id": "cap.policy.access_control"},
                    {"id": "sec-2", "name": "Masking & Anonymization", "capability_id": "cap.policy.masking"},
                    {"id": "sla-1", "name": "Define SLAs & DQ Targets", "capability_id": "cap.sla.quality"},
                    {"id": "obs-1", "name": "Observability Spec", "capability_id": "cap.observability.define"},
                    {"id": "topo-1", "name": "Platform Topology", "capability_id": "cap.diagram.topology"},
                    {"id": "rank-1", "name": "Rank Tech Stack", "capability_id": "cap.rank.tech_stack"},
                    {"id": "dap-1", "name": "Compose Data Products", "capability_id": "cap.catalog.data_products"},
                    {"id": "asm-1", "name": "Assemble Pipeline Architecture", "capability_id": "cap.assemble.pipeline_architecture"},
                    {"id": "dep-1", "name": "Deployment Plan", "capability_id": "cap.plan.deployment"},
                ],
            },
            {
                "id": "pb.data-arch.guidance.v1",
                "name": "Data Pipeline Architecture Guidance (v1)",
                "description": (
                    "Generate a comprehensive, prose-style architecture guidance document grounded in the artifacts "
                    "produced by the discovery flow (patterns, datasets, lineage, SLAs, topology, etc.)."
                ),
                "input_id": "input.data-eng.architecture-guide",
                "steps": [
                    {
                        "id": "guide-1",
                        "name": "Generate Architecture Guidance Document",
                        "capability_id": "cap.data-eng.generate-arch-diagram",
                    }
                ],
            },
        ],
        status="published",
        created_by="seed",
        updated_by="seed",
    )

    # -----------------------------
    # v1.1 (NEW) – first step fetches Raina input via MCP
    # -----------------------------
    pack_v1_1 = CapabilityPackCreate(
        id="data-pipeline-arch@v1.1",
        key="data-pipeline-arch",
        version="v1.1",
        title="Data Engineering Architecture Discovery Pack (v1.1)",
        description=(
            "Generates an implementation-ready data pipeline architecture from AVC/FSS/PSS inputs, including patterns "
            "(batch/stream/lambda/event-driven), dataset contracts, transformations, lineage, governance, SLAs/observability, "
            "orchestration, topology, tech stack ranking, data products, a concrete deployment plan, and an optional "
            "architecture guidance document grounded in discovered artifacts. This version fetches the Raina input via MCP as the first step."
        ),
        # v1.1 uses the explicit URL-based Raina input contract
        pack_input_ids=[
            "input.raina.user-stories-url",
            "input.data-eng.architecture-guide",
        ],
        capability_ids=[
            "cap.raina.fetch_input",  # NEW
            "cap.inventory.sources_sinks",
            "cap.discover.business_flows",
            "cap.discover.logical_data_model",
            "cap.select.pipeline_patterns",
            "cap.define.dataset_contracts",
            "cap.spec.transforms",
            "cap.spec.batch_job",
            "cap.spec.stream_job",
            "cap.orchestration.define",
            "cap.map.lineage",
            "cap.policy.governance",
            "cap.policy.access_control",
            "cap.policy.masking",
            "cap.sla.quality",
            "cap.observability.define",
            "cap.diagram.topology",
            "cap.rank.tech_stack",
            "cap.catalog.data_products",
            "cap.assemble.pipeline_architecture",
            "cap.plan.deployment",
            "cap.data-eng.generate-arch-diagram",
        ],
        agent_capability_ids=[
            "cap.diagram.mermaid",
        ],
        playbooks=[
            {
                "id": "pb.data-arch.v1.1",
                "name": "Data Engineering Architecture Discovery (v1.1)",
                "description": (
                    "End-to-end flow starting by fetching AVC/FSS/PSS via MCP: fetch → sources → flows → model → patterns "
                    "→ contracts → transforms → jobs → orchestration → lineage → governance & security → SLAs/observability "
                    "→ topology → stack ranking → data products → assembly → deployment plan."
                ),
                "input_id": "input.raina.user-stories-url",
                "steps": [
                    {
                        "id": "fetch-1",
                        "name": "Fetch Raina Input (AVC/FSS/PSS)",
                        "capability_id": "cap.raina.fetch_input",
                        "description": "Fetch and validate the Raina input JSON (emits cam.inputs.raina)."
                    },
                    {"id": "src-1", "name": "Inventory Sources & Sinks", "capability_id": "cap.inventory.sources_sinks"},
                    {"id": "flow-1", "name": "Discover Business Flows", "capability_id": "cap.discover.business_flows"},
                    {"id": "model-1", "name": "Derive Logical Data Model", "capability_id": "cap.discover.logical_data_model"},
                    {"id": "pat-1", "name": "Select Pipeline Architecture Patterns", "capability_id": "cap.select.pipeline_patterns"},
                    {"id": "contract-1", "name": "Define Dataset Contracts", "capability_id": "cap.define.dataset_contracts"},
                    {"id": "tfm-1", "name": "Specify Transformations", "capability_id": "cap.spec.transforms"},
                    {"id": "batch-1", "name": "Generate Batch Job Spec", "capability_id": "cap.spec.batch_job"},
                    {"id": "stream-1", "name": "Generate Stream Job Spec", "capability_id": "cap.spec.stream_job"},
                    {"id": "orc-1", "name": "Define Orchestration", "capability_id": "cap.orchestration.define"},
                    {"id": "lin-1", "name": "Map Lineage", "capability_id": "cap.map.lineage"},
                    {"id": "gov-1", "name": "Derive Governance Policies", "capability_id": "cap.policy.governance"},
                    {"id": "sec-1", "name": "Access Control", "capability_id": "cap.policy.access_control"},
                    {"id": "sec-2", "name": "Masking & Anonymization", "capability_id": "cap.policy.masking"},
                    {"id": "sla-1", "name": "Define SLAs & DQ Targets", "capability_id": "cap.sla.quality"},
                    {"id": "obs-1", "name": "Observability Spec", "capability_id": "cap.observability.define"},
                    {"id": "topo-1", "name": "Platform Topology", "capability_id": "cap.diagram.topology"},
                    {"id": "rank-1", "name": "Rank Tech Stack", "capability_id": "cap.rank.tech_stack"},
                    {"id": "dap-1", "name": "Compose Data Products", "capability_id": "cap.catalog.data_products"},
                    {"id": "asm-1", "name": "Assemble Pipeline Architecture", "capability_id": "cap.assemble.pipeline_architecture"},
                    {"id": "dep-1", "name": "Deployment Plan", "capability_id": "cap.plan.deployment"},
                ],
            },
            {
                "id": "pb.data-arch.guidance.v1",
                "name": "Data Pipeline Architecture Guidance (v1)",
                "description": (
                    "Generate a comprehensive, prose-style architecture guidance document grounded in the artifacts "
                    "produced by the discovery flow (patterns, datasets, lineage, SLAs, topology, etc.)."
                ),
                "input_id": "input.data-eng.architecture-guide",
                "steps": [
                    {
                        "id": "guide-1",
                        "name": "Generate Architecture Guidance Document",
                        "capability_id": "cap.data-eng.generate-arch-diagram",
                    }
                ],
            },
        ],
        status="published",
        created_by="seed",
        updated_by="seed",
    )

    # Seed both versions
    await _replace_by_id(svc, pack_v1_0)
    await _replace_by_id(svc, pack_v1_1)

    if publish_on_seed:
        await _publish_all(svc, ids=("data-pipeline-arch@v1.0", "data-pipeline-arch@v1.1"))
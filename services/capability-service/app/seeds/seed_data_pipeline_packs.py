# services/capability-service/app/seeds/seed_data_pipeline_packs.py
from __future__ import annotations

import logging
import os

from app.models import CapabilityPackCreate
from app.services import PackService  # ✅ fixed import

log = logging.getLogger("app.seeds.packs.data_pipeline")


async def seed_data_pipeline_packs() -> None:
    """
    Seeds the Data Engineering Architecture Discovery capability pack.

    Pack key: data-pipeline-arch@v1.0
    Depends on pack input: input.astra.discovery.avc-fss-pss
    """
    svc = PackService()  # ✅ fixed class name

    publish_on_seed = os.getenv("PACK_SEED_PUBLISH", "1") in ("1", "true", "True")

    target = CapabilityPackCreate(
        id="data-pipeline-arch@v1.0",
        key="data-pipeline-arch",
        version="v1.0",
        title="Data Engineering Architecture Discovery Pack (v1.0)",
        description=(
            "Generates an implementation-ready data pipeline architecture from AVC/FSS/PSS inputs, including patterns "
            "(batch/stream/lambda/event-driven), dataset contracts, transformations, lineage, governance, SLAs/observability, "
            "orchestration, topology, tech stack ranking, data products, and a concrete deployment plan."
        ),
        pack_input_id="input.astra.discovery.avc-fss-pss",
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
            }
        ],
        status="published",
        created_by="seed",
        updated_by="seed",
    )

    # Idempotent replace-by-id
    try:
        existing = await svc.get(target.id)
    except Exception:
        existing = None

    if existing:
        try:
            ok = await svc.delete(target.id, actor="seed")
            if ok:
                log.info("[packs.seeds.data_pipeline] replaced existing: %s", target.id)
            else:
                log.warning("[packs.seeds.data_pipeline] could not delete existing: %s (continuing)", target.id)
        except Exception as e:
            log.warning("[packs.seeds.data_pipeline] delete failed for %s: %s (continuing)", target.id, e)

    created = await svc.create(target, actor="seed")
    log.info("[packs.seeds.data_pipeline] created: %s", created.id)

    if publish_on_seed:
        try:
            published = await svc.publish(f"{target.key}@{target.version}", actor="seed")
            if published:
                log.info("[packs.seeds.data_pipeline] published: %s", published.id)
        except Exception as e:
            log.warning("[packs.seeds.data_pipeline] publish failed: %s", e)
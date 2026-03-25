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
    the Raina input JSON via the new MCP capability `cap.asset.fetch_raina_input`.
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
        capability_ids=[
            "cap.catalog.inventory_sources",
            "cap.workflow.discover_business_flows",
            "cap.data.discover_logical_model",
            "cap.architecture.select_pipeline_patterns",
            "cap.contract.define_dataset",
            "cap.data.spec_transforms",
            "cap.workflow.spec_batch_job",
            "cap.workflow.spec_stream_job",
            "cap.workflow.define_orchestration",
            "cap.data.map_lineage",
            "cap.governance.derive_policies",
            "cap.security.define_access_control",
            "cap.security.define_masking",
            "cap.qa.define_data_sla",
            "cap.observability.define_spec",
            "cap.diagram.topology",
            "cap.catalog.rank_tech_stack",
            "cap.catalog.data_products",
            "cap.architecture.assemble_pipeline",
            "cap.deployment.plan_pipeline",
            # include guidance capability for guidance playbook
            "cap.diagram.generate_arch",
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
                    {"id": "src-1", "name": "Inventory Sources & Sinks", "capability_id": "cap.catalog.inventory_sources"},
                    {"id": "flow-1", "name": "Discover Business Flows", "capability_id": "cap.workflow.discover_business_flows"},
                    {"id": "model-1", "name": "Derive Logical Data Model", "capability_id": "cap.data.discover_logical_model"},
                    {"id": "pat-1", "name": "Select Pipeline Architecture Patterns", "capability_id": "cap.architecture.select_pipeline_patterns"},
                    {"id": "contract-1", "name": "Define Dataset Contracts", "capability_id": "cap.contract.define_dataset"},
                    {"id": "tfm-1", "name": "Specify Transformations", "capability_id": "cap.data.spec_transforms"},
                    {"id": "batch-1", "name": "Generate Batch Job Spec", "capability_id": "cap.workflow.spec_batch_job"},
                    {"id": "stream-1", "name": "Generate Stream Job Spec", "capability_id": "cap.workflow.spec_stream_job"},
                    {"id": "orc-1", "name": "Define Orchestration", "capability_id": "cap.workflow.define_orchestration"},
                    {"id": "lin-1", "name": "Map Lineage", "capability_id": "cap.data.map_lineage"},
                    {"id": "gov-1", "name": "Derive Governance Policies", "capability_id": "cap.governance.derive_policies"},
                    {"id": "sec-1", "name": "Access Control", "capability_id": "cap.security.define_access_control"},
                    {"id": "sec-2", "name": "Masking & Anonymization", "capability_id": "cap.security.define_masking"},
                    {"id": "sla-1", "name": "Define SLAs & DQ Targets", "capability_id": "cap.qa.define_data_sla"},
                    {"id": "obs-1", "name": "Observability Spec", "capability_id": "cap.observability.define_spec"},
                    {"id": "topo-1", "name": "Platform Topology", "capability_id": "cap.diagram.topology"},
                    {"id": "rank-1", "name": "Rank Tech Stack", "capability_id": "cap.catalog.rank_tech_stack"},
                    {"id": "dap-1", "name": "Compose Data Products", "capability_id": "cap.catalog.data_products"},
                    {"id": "asm-1", "name": "Assemble Pipeline Architecture", "capability_id": "cap.architecture.assemble_pipeline"},
                    {"id": "dep-1", "name": "Deployment Plan", "capability_id": "cap.deployment.plan_pipeline"},
                ],
            },
            {
                "id": "pb.data-arch.guidance.v1",
                "name": "Data Pipeline Architecture Guidance (v1)",
                "description": (
                    "Generate a comprehensive, prose-style architecture guidance document grounded in the artifacts "
                    "produced by the discovery flow (patterns, datasets, lineage, SLAs, topology, etc.)."
                ),
                "steps": [
                    {
                        "id": "guide-1",
                        "name": "Generate Architecture Guidance Document",
                        "capability_id": "cap.diagram.generate_arch",
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
        capability_ids=[
            "cap.asset.fetch_raina_input",  # NEW
            "cap.catalog.inventory_sources",
            "cap.workflow.discover_business_flows",
            "cap.data.discover_logical_model",
            "cap.architecture.select_pipeline_patterns",
            "cap.contract.define_dataset",
            "cap.data.spec_transforms",
            "cap.workflow.spec_batch_job",
            "cap.workflow.spec_stream_job",
            "cap.workflow.define_orchestration",
            "cap.data.map_lineage",
            "cap.governance.derive_policies",
            "cap.security.define_access_control",
            "cap.security.define_masking",
            "cap.qa.define_data_sla",
            "cap.observability.define_spec",
            "cap.diagram.topology",
            "cap.catalog.rank_tech_stack",
            "cap.catalog.data_products",
            "cap.architecture.assemble_pipeline",
            "cap.deployment.plan_pipeline",
            "cap.diagram.generate_arch",
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
                "steps": [
                    {
                        "id": "fetch-1",
                        "name": "Fetch Raina Input (AVC/FSS/PSS)",
                        "capability_id": "cap.asset.fetch_raina_input",
                        "description": "Fetch and validate the Raina input JSON (emits cam.asset.raina_input)."
                    },
                    {"id": "src-1", "name": "Inventory Sources & Sinks", "capability_id": "cap.catalog.inventory_sources"},
                    {"id": "flow-1", "name": "Discover Business Flows", "capability_id": "cap.workflow.discover_business_flows"},
                    {"id": "model-1", "name": "Derive Logical Data Model", "capability_id": "cap.data.discover_logical_model"},
                    {"id": "pat-1", "name": "Select Pipeline Architecture Patterns", "capability_id": "cap.architecture.select_pipeline_patterns"},
                    {"id": "contract-1", "name": "Define Dataset Contracts", "capability_id": "cap.contract.define_dataset"},
                    {"id": "tfm-1", "name": "Specify Transformations", "capability_id": "cap.data.spec_transforms"},
                    {"id": "batch-1", "name": "Generate Batch Job Spec", "capability_id": "cap.workflow.spec_batch_job"},
                    {"id": "stream-1", "name": "Generate Stream Job Spec", "capability_id": "cap.workflow.spec_stream_job"},
                    {"id": "orc-1", "name": "Define Orchestration", "capability_id": "cap.workflow.define_orchestration"},
                    {"id": "lin-1", "name": "Map Lineage", "capability_id": "cap.data.map_lineage"},
                    {"id": "gov-1", "name": "Derive Governance Policies", "capability_id": "cap.governance.derive_policies"},
                    {"id": "sec-1", "name": "Access Control", "capability_id": "cap.security.define_access_control"},
                    {"id": "sec-2", "name": "Masking & Anonymization", "capability_id": "cap.security.define_masking"},
                    {"id": "sla-1", "name": "Define SLAs & DQ Targets", "capability_id": "cap.qa.define_data_sla"},
                    {"id": "obs-1", "name": "Observability Spec", "capability_id": "cap.observability.define_spec"},
                    {"id": "topo-1", "name": "Platform Topology", "capability_id": "cap.diagram.topology"},
                    {"id": "rank-1", "name": "Rank Tech Stack", "capability_id": "cap.catalog.rank_tech_stack"},
                    {"id": "dap-1", "name": "Compose Data Products", "capability_id": "cap.catalog.data_products"},
                    {"id": "asm-1", "name": "Assemble Pipeline Architecture", "capability_id": "cap.architecture.assemble_pipeline"},
                    {"id": "dep-1", "name": "Deployment Plan", "capability_id": "cap.deployment.plan_pipeline"},
                ],
            },
            {
                "id": "pb.data-arch.guidance.v1",
                "name": "Data Pipeline Architecture Guidance (v1)",
                "description": (
                    "Generate a comprehensive, prose-style architecture guidance document grounded in the artifacts "
                    "produced by the discovery flow (patterns, datasets, lineage, SLAs, topology, etc.)."
                ),
                "steps": [
                    {
                        "id": "guide-1",
                        "name": "Generate Architecture Guidance Document",
                        "capability_id": "cap.diagram.generate_arch",
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
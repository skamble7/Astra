# app/seeds/seed_data_pipeline_capabilities.py
from __future__ import annotations

import logging
import inspect
from datetime import datetime

from app.models import (
    GlobalCapabilityCreate,
    LlmExecution,
)
from app.services import CapabilityService

log = logging.getLogger("app.seeds.data_pipeline_capabilities")


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
                log.info("[capability.seeds.data-pipeline] wiped existing via CapabilityService.%s()", name)
                return True
            except Exception as e:
                log.warning("[capability.seeds.data-pipeline] %s() failed: %s", name, e)
    return False


def _llm_cap(
    _id: str,
    name: str,
    description: str,
    produces_kinds: list[str],
    tags: list[str] | None = None,
) -> GlobalCapabilityCreate:
    return GlobalCapabilityCreate(
        id=_id,
        name=name,
        description=description,
        tags=tags or ["astra", "data", "pipeline"],
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
                "auth": {"method": "api_key", "alias_token": None, "alias_user": None, "alias_password": None, "alias_key": "OPENAI_API_KEY"},
            },
            io=None,
        ),
    )


async def seed_capabilities() -> None:
    """
    Seeds data-pipeline LLM capabilities (OpenAI, api_key).
    """
    log.info("[capability.seeds.data-pipeline] Begin")

    svc = CapabilityService()

    # Optional wipe (best-effort; falls back to replace-by-id below)
    wiped = await _try_wipe_all(svc)
    if not wiped:
        log.info("[capability.seeds.data-pipeline] No wipe method found; proceeding with replace-by-id")

    targets: list[GlobalCapabilityCreate] = [
        _llm_cap(
            "cap.discover.logical_data_model",
            "Discover Logical Data Model",
            "Derives entities, attributes, keys, and relationships from AVC/FSS/PSS and goals/NFRs.",
            ["cam.data.model_logical"],
            tags=["astra", "data", "modeling"],
        ),
        _llm_cap(
            "cap.discover.business_flows",
            "Discover Business Flows",
            "Extracts actor-centric flows mapped to datasets from AVC/FSS and architectural context.",
            ["cam.flow.business_flow_catalog"],
            tags=["astra", "workflow", "discovery"],
        ),
        _llm_cap(
            "cap.select.pipeline_patterns",
            "Select Pipeline Architecture Patterns",
            "Evaluates Batch/Stream/Lambda/Microservices/Event-driven patterns against FR/NFRs and constraints.",
            ["cam.architecture.pipeline_patterns"],
            tags=["astra", "architecture", "patterns"],
        ),
        _llm_cap(
            "cap.define.dataset_contracts",
            "Define Dataset Contracts",
            "Produces implementation-grade dataset contracts with schema, keys, PII flags, stewardship, quality rules, and retention.",
            ["cam.data.dataset_contract"],
            tags=["astra", "data", "contracts"],
        ),
        _llm_cap(
            "cap.assemble.pipeline_architecture",
            "Assemble Data Pipeline Architecture",
            "Synthesizes stages, routing, idempotency strategy, SLAs, and ranked tech stack recommendations.",
            ["cam.workflow.data_pipeline_architecture"],
            tags=["astra", "workflow", "architecture"],
        ),
        _llm_cap(
            "cap.spec.batch_job",
            "Generate Batch Job Spec",
            "Creates batch job schedules and steps (ETL/ELT/validate) aligned to pipeline SLAs and idempotency.",
            ["cam.workflow.batch_job_spec"],
            tags=["astra", "workflow", "batch"],
        ),
        _llm_cap(
            "cap.spec.stream_job",
            "Generate Stream Job Spec",
            "Defines streaming jobs with sources, sinks, windowing, processing ops, and consistency settings.",
            ["cam.workflow.stream_job_spec"],
            tags=["astra", "workflow", "streaming"],
        ),
        _llm_cap(
            "cap.spec.transforms",
            "Define Data Transformations",
            "Specifies dataset-to-dataset transforms with logic and associated data quality checks.",
            ["cam.workflow.transform_spec"],
            tags=["astra", "data", "transform"],
        ),
        _llm_cap(
            "cap.map.lineage",
            "Map Data Lineage",
            "Builds dataset/job/source lineage graph (reads/writes/derives/publishes) from specs and contracts.",
            ["cam.data.lineage_map"],
            tags=["astra", "data", "lineage"],
        ),
        _llm_cap(
            "cap.policy.governance",
            "Derive Data Governance Policies",
            "Outputs classification, access/retention, and lineage requirements from AVC/NFR and contracts.",
            ["cam.governance.data_governance_policies"],
            tags=["astra", "governance", "policy"],
        ),
        _llm_cap(
            "cap.policy.access_control",
            "Derive Data Access Control",
            "Generates dataset-role access rules (read/write/admin/mask) from classifications and governance policy.",
            ["cam.security.data_access_control"],
            tags=["astra", "security", "policy"],
        ),
        _llm_cap(
            "cap.policy.masking",
            "Define Masking & Anonymization",
            "Emits field-level masking/tokenization/generalization policies for PII and sensitive data.",
            ["cam.security.data_masking_policy"],
            tags=["astra", "security", "privacy"],
        ),
        _llm_cap(
            "cap.sla.quality",
            "Define Data Quality & SLA",
            "Sets SLA targets and monitoring plan (freshness, latency, availability, DQ pass rate).",
            ["cam.quality.data_sla"],
            tags=["astra", "quality", "sla"],
        ),
        _llm_cap(
            "cap.observability.define",
            "Define Data Observability Spec",
            "Declares required metrics, logs, traces, and exporters to enforce SLAs and diagnose issues.",
            ["cam.observability.data_observability_spec"],
            tags=["astra", "observability", "otel"],
        ),
        _llm_cap(
            "cap.orchestration.define",
            "Define Data Orchestration",
            "Wires batch/stream jobs into a dependency graph with failure policy, consistent with selected orchestrator.",
            ["cam.workflow.orchestration_spec"],
            tags=["astra", "workflow", "orchestration"],
        ),
        _llm_cap(
            "cap.rank.tech_stack",
            "Rank Tech Stack",
            "Produces category-wise ranked tooling (streaming, batch compute, storage, orchestration, DQ, catalog, observability) with rationale.",
            ["cam.catalog.tech_stack_rankings"],
            tags=["astra", "architecture", "stack"],
        ),
        _llm_cap(
            "cap.inventory.sources_sinks",
            "Inventory Sources & Sinks",
            "Enumerates principal data sources and sinks implied by flows, entities, and constraints.",
            ["cam.catalog.data_source_inventory"],
            tags=["astra", "data", "inventory"],
        ),
        _llm_cap(
            "cap.catalog.data_products",
            "Compose Data Products",
            "Bundles datasets into Data-as-a-Product entries with ownership and SLO commitment.",
            ["cam.data_product.catalog"],
            tags=["astra", "data", "product"],
        ),
        _llm_cap(
            "cap.diagram.topology",
            "Define Data Platform Topology",
            "Declares platform components and links (ingest, queue, compute, storage, orchestration, catalog, DQ, observability) across environments.",
            ["cam.deployment.data_platform_topology"],
            tags=["astra", "deployment", "topology"],
        ),
        _llm_cap(
            "cap.plan.deployment",
            "Plan Pipeline Deployment",
            "Creates deployment plan with phased rollout, backfill/migration, and backout across environments.",
            ["cam.deployment.pipeline_deployment_plan"],
            tags=["astra", "deployment", "plan"],
        ),
    ]

    # Replace-by-id creation
    created = 0
    for cap in targets:
        try:
            existing = await svc.get(cap.id)
            if existing:
                try:
                    await svc.delete(cap.id, actor="seed")
                    log.info("[capability.seeds.data-pipeline] replaced: %s (deleted old)", cap.id)
                except AttributeError:
                    log.warning("[capability.seeds.data-pipeline] delete() not available; attempting create() which may fail on unique ID")
        except Exception:
            # get() missing or failed -> treat as non-existent
            pass

        await svc.create(cap, actor="seed")
        log.info("[capability.seeds.data-pipeline] created: %s", cap.id)
        created += 1

    log.info("[capability.seeds.data-pipeline] Done (created=%d)", created)
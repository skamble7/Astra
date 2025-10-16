from __future__ import annotations

import logging
import os

from app.models import CapabilityPackCreate, Playbook, PlaybookStep
from app.services import PackService

log = logging.getLogger("app.seeds.packs")


async def _delete_pack_if_exists(svc: PackService, key: str, version: str) -> None:
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
                    log.info("[capability.seeds.packs] %s('%s@%s') ok", meth_name, key, version)
                    return
                except TypeError:
                    try:
                        await m(existing.id, actor="seed")
                        log.info("[capability.seeds.packs] %s(id=%s) ok", meth_name, existing.id)
                        return
                    except TypeError:
                        await m(key, version, actor="seed")
                        log.info("[capability.seeds.packs] %s('%s','%s') ok", meth_name, key, version)
                        return
            except Exception as e:
                log.warning("[capability.seeds.packs] %s failed: %s", meth_name, e)
    log.warning("[capability.seeds.packs] Could not delete existing pack %s@%s; continuing with create()", key, version)


async def _create_and_maybe_publish(svc: PackService, payload: CapabilityPackCreate, publish_on_seed: bool) -> None:
    key = payload.key
    version = payload.version
    created = await svc.create(payload, actor="seed")
    log.info("[capability.seeds.packs] created: %s@%s (id=%s)", key, version, getattr(created, "id", None))
    if publish_on_seed:
        published = await svc.publish(f"{key}@{version}", actor="seed")
        if published:
            log.info("[capability.seeds.packs] published: %s", published.id)
        else:
            log.warning("[capability.seeds.packs] publish failed or pack not found for %s@%s", key, version)
    else:
        log.info("[capability.seeds.packs] publish skipped via env for %s@%s", key, version)


async def seed_packs() -> None:
    log.info("[capability.seeds.packs] Begin")

    publish_on_seed = os.getenv("PACK_SEED_PUBLISH", "1") in ("1", "true", "True")
    svc = PackService()

    # Pack input contracts
    renova_input_id = "input.renova.repo"
    summary_input_id = "input.renova.workspace_summary"  # NEW

    pack_key = "cobol-mainframe"
    full_version = "v1.0.1"
    mini_version = "v1.0.2"
    mini_v103 = "v1.0.3"  # minimal three-step pack

    # -------------------------------
    # Pack #1: Full-flow v1.0.1
    # -------------------------------
    await _delete_pack_if_exists(svc, pack_key, full_version)

    pb_main = Playbook(
        id="pb.main",
        name="Main COBOL Learning Flow",
        description="Topologically ordered steps to parse, index, enrich, and render the enterprise flow.",
        input_id=renova_input_id,   # must be in pack_input_ids
        steps=[
            PlaybookStep(
                id="s1.clone",
                name="Clone Repo",
                capability_id="cap.repo.clone",
                description="Clone source repository; records commit and paths_root.",
            ),
            PlaybookStep(
                id="s2.cobol",
                name="Parse COBOL",
                capability_id="cap.cobol.parse",
                description="ProLeap/cb2xml parse of programs and copybooks into normalized CAM kinds.",
            ),
            PlaybookStep(
                id="s3.jcl",
                name="Parse JCL",
                capability_id="cap.jcl.parse",
                description="Parse JCL jobs/steps and DDs.",
            ),
            PlaybookStep(
                id="s4.cics",
                name="Discover CICS (optional)",
                capability_id="cap.cics.catalog",
                description="If configured, discover transaction→program mapping.",
            ),
            PlaybookStep(
                id="s5.db2",
                name="Export DB2 Catalog (optional)",
                capability_id="cap.db2.catalog",
                description="Load DB2 schema via connection alias or DDL folder.",
            ),
            PlaybookStep(
                id="s6.graph",
                name="Index Enterprise Graph",
                capability_id="cap.graph.index",
                description="Build service/dependency inventories from parsed facts.",
            ),
            PlaybookStep(
                id="s7.entities",
                name="Detect Entities & Terms",
                capability_id="cap.entity.detect",
                description="Lift copybooks/physical into logical data model and domain dictionary.",
            ),
            PlaybookStep(
                id="s8.lineage",
                name="Derive Data Lineage",
                capability_id="cap.lineage.derive",
                description="Conservative field-level lineage from IO ops and steps.",
            ),
            PlaybookStep(
                id="s9.batch",
                name="Mine Batch Workflows",
                capability_id="cap.workflow.mine_batch",
                description="Deterministic stitching of job flows + call graph.",
            ),
            PlaybookStep(
                id="s10.entity",
                name="Mine Entity Workflows",
                capability_id="cap.workflow.mine_entity",
                description="Entity-centric slicing and business-readable flows.",
            ),
            PlaybookStep(
                id="s11.diagrams",
                name="Render Diagrams",
                capability_id="cap.diagram.render",
                description="Render activity/sequence/component/deployment/state diagrams.",
            ),
        ],
    )

    payload_full = CapabilityPackCreate(
        key=pack_key,
        version=full_version,
        title="COBOL Mainframe Modernization",
        description="Deterministic MCP parsing + LLM enrichment to discover inventories, data lineage, and workflows from COBOL/JCL estates.",
        pack_input_ids=[renova_input_id],
        capability_ids=[
            "cap.repo.clone",
            "cap.cobol.parse",
            "cap.jcl.parse",
            "cap.cics.catalog",
            "cap.db2.catalog",
            "cap.graph.index",
            "cap.entity.detect",
            "cap.lineage.derive",
            "cap.workflow.mine_batch",
            "cap.workflow.mine_entity",
            "cap.diagram.render",
        ],
        agent_capability_ids=["cap.diagram.mermaid"],
        playbooks=[pb_main],
    )

    await _create_and_maybe_publish(svc, payload_full, publish_on_seed)

    # -------------------------------
    # Pack #2: Minimal two-step v1.0.2
    # -------------------------------
    await _delete_pack_if_exists(svc, pack_key, mini_version)

    # Existing core playbook (unchanged)
    pb_core = Playbook(
        id="pb.core",
        name="Core Clone + Parse",
        description="Minimal flow to clone a repo and parse COBOL sources.",
        input_id=renova_input_id,
        steps=[
            PlaybookStep(
                id="s1.clone",
                name="Clone Repo",
                capability_id="cap.repo.clone",
                description="Clone source repository; records commit and paths_root.",
            ),
            PlaybookStep(
                id="s2.cobol",
                name="Parse COBOL",
                capability_id="cap.cobol.parse",
                description="ProLeap/cb2xml parse of programs and copybooks into normalized CAM kinds.",
            ),
        ],
    )

    # NEW: single-step playbook for workspace summary doc
    pb_summary = Playbook(
        id="pb.summary",
        name="Generate COBOL Workspace Summary",
        description="Generate a Markdown document summarizing COBOL artifacts for the workspace.",
        input_id=summary_input_id,  # must be present in pack_input_ids
        steps=[
            PlaybookStep(
                id="s1.workspace_doc",
                name="Workspace Summary Document",
                capability_id="cap.cobol.workspace_doc",
                description="Produce cam.asset.cobol_artifacts_summary for the workspace.",
            )
        ],
    )

    payload_mini = CapabilityPackCreate(
        key=pack_key,
        version=mini_version,
        title="COBOL Mainframe Modernization (Core)",
        description="Derived minimal pack with a two-step playbook (clone + parse) and an optional workspace summary generator.",
        # UPDATED: include both inputs (repo + workspace_summary)
        pack_input_ids=[renova_input_id, summary_input_id],
        capability_ids=[
            "cap.repo.clone",
            "cap.cobol.parse",
            # NEW: make the capability discoverable/resolvable for pb.summary
            "cap.cobol.workspace_doc",
        ],
        agent_capability_ids=["cap.diagram.mermaid"],
        # UPDATED: include the new summary playbook
        playbooks=[pb_core, pb_summary],
    )

    await _create_and_maybe_publish(svc, payload_mini, publish_on_seed)

    # -------------------------------
    # Pack #3: Minimal three-step v1.0.3
    # -------------------------------
    await _delete_pack_if_exists(svc, pack_key, mini_v103)

    pb_core_v103 = Playbook(
        id="pb.core",
        name="Core Clone + Parse + Entities",
        description="Clone a repository, parse COBOL sources, then lift entities and a domain dictionary.",
        input_id=renova_input_id,
        steps=[
            PlaybookStep(
                id="s1.clone",
                name="Clone Repo",
                capability_id="cap.repo.clone",
                description="Clone source repository; records commit and paths_root.",
            ),
            PlaybookStep(
                id="s2.cobol",
                name="Parse COBOL",
                capability_id="cap.cobol.parse",
                description="ProLeap/cb2xml parse of programs and copybooks into normalized CAM kinds.",
            ),
            PlaybookStep(
                id="s3.entities",
                name="Detect Entities & Domain Terms",
                capability_id="cap.entity.detect",
                description="Derive a logical data model and a domain dictionary from parsed copybooks and DB2 schemas.",
            ),
        ],
    )

    payload_mini_v103 = CapabilityPackCreate(
        key=pack_key,
        version=mini_v103,
        title="COBOL Mainframe Modernization (Core)",
        description="Derived minimal pack with a three-step playbook: clone a repo, parse COBOL, then detect entities and domain terms.",
        pack_input_ids=[renova_input_id],
        capability_ids=[
            "cap.repo.clone",
            "cap.cobol.parse",
            "cap.entity.detect",
        ],
        agent_capability_ids=["cap.diagram.mermaid"],
        playbooks=[pb_core_v103],
    )

    await _create_and_maybe_publish(svc, payload_mini_v103, publish_on_seed)

    log.info(
        "[capability.seeds.packs] Done (seeded %s@%s, %s@%s, %s@%s)",
        pack_key, full_version,
        pack_key, mini_version,
        pack_key, mini_v103,
    )
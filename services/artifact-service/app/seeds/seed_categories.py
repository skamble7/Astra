# services/artifact-service/app/seeds/seed_categories.py
from __future__ import annotations

from typing import Dict, List
from datetime import datetime

from app.dal.category_dal import ensure_indexes
from motor.motor_asyncio import AsyncIOMotorDatabase

CATEGORY_KEYS: List[str] = [
    # ── Cross-cutting (all use cases) ──────────────────────────────────────
    "diagram",      # Visual diagram artifacts (context, class, sequence, component, …)
    "contract",     # API, event, service, dataset contracts
    "catalog",      # Service catalogs, tech stack rankings, data product catalogs
    "workflow",     # Process flows, pipelines, orchestration specs, state machines
    "data",         # Data models, dictionaries, lineage, ownership, governance policies
    "ops",          # Runbooks, playbooks, postmortems, on-call rosters
    "asset",        # Source repo snapshots, source index, inventories, raina inputs
    "domain",       # Domain models, bounded contexts, ubiquitous language
    "governance",   # ADRs, standards, compliance matrices, stakeholder maps, RTMs
    "qa",           # Test plans, test cases, coverage matrices, quality SLAs
    "risk",         # Risk registers, matrices, mitigation plans
    "performance",  # Benchmark reports, capacity plans, load profiles
    "finops",       # Cost models, budgets, usage reports, chargeback policies
    # ── Architecture Discovery (RAINA) ─────────────────────────────────────
    "architecture",   # Architecture overviews, service interactions, integration patterns
    "security",       # Security architecture, policies, access control, data masking
    "deployment",     # Deployment topologies, migration and rollout plans
    "observability",  # Observability specs, SLOs, dashboards, alerting policies
    "infra",          # Infrastructure topology, K8s manifests, network/scaling policies
    # ── Agile Artifact Authoring (SABA) ────────────────────────────────────
    "agile",   # Epics, features, user stories, tasks, sprint plans, MoSCoW
    # ── Legacy Code Modernization (Neozeta) ────────────────────────────────
    "cobol",  # COBOL programs, copybooks, AST/ASG parse results
    "jcl",    # JCL jobs, steps
    "cics",   # CICS transactions and programs
    "db2",    # DB2 schema and catalog artifacts
]

ICONS: Dict[str, str] = {
    "diagram":      '<svg ...>...</svg>',
    "contract":     '<svg ...>...</svg>',
    "catalog":      '<svg ...>...</svg>',
    "workflow":     '<svg ...>...</svg>',
    "data":         '<svg ...>...</svg>',
    "ops":          '<svg ...>...</svg>',
    "asset":        '<svg ...>...</svg>',
    "domain":       '<svg ...>...</svg>',
    "governance":   '<svg ...>...</svg>',
    "qa":           '<svg ...>...</svg>',
    "risk":         '<svg ...>...</svg>',
    "performance":  '<svg ...>...</svg>',
    "finops":       '<svg ...>...</svg>',
    "architecture": '<svg ...>...</svg>',
    "security":     '<svg ...>...</svg>',
    "deployment":   '<svg ...>...</svg>',
    "observability": '<svg ...>...</svg>',
    "infra":        '<svg ...>...</svg>',
    "agile":        '<svg ...>...</svg>',
    "cobol":        '<svg ...>...</svg>',
    "jcl":          '<svg ...>...</svg>',
    "cics":         '<svg ...>...</svg>',
    "db2":          '<svg ...>...</svg>',
}

def _build_doc(key: str, name: str, description: str, icon_svg: str) -> dict:
    now = datetime.utcnow()
    return {
        "_id": f"cat:{key}",
        "key": key,
        "name": name,
        "description": description,
        "icon_svg": icon_svg,
        "created_at": now,
        "updated_at": now,
    }

async def ensure_categories_seed(db: AsyncIOMotorDatabase) -> dict:
    await ensure_indexes(db)
    col = db["cam_categories"]

    existing_keys = {d["key"] async for d in col.find({}, {"key": 1, "_id": 0})}
    to_seed = [k for k in CATEGORY_KEYS if k not in existing_keys]

    seeded = 0
    for key in to_seed:
        name = key.title()
        desc = f"Category for CAM artifacts with key '{key}'."
        icon = ICONS.get(key, ICONS["diagram"])
        await col.insert_one(_build_doc(key, name, desc, icon))
        seeded += 1

    return {"existing": len(existing_keys), "seeded": seeded, "total": len(CATEGORY_KEYS)}

# services/capability-service/app/seeds/seed_agile_capabilities.py
from __future__ import annotations

import logging

from app.models import GlobalCapabilityCreate, LlmExecution
from app.services import CapabilityService

log = logging.getLogger("app.seeds.agile_capabilities")


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
        tags=tags or ["astra", "agile"],
        parameters_schema=None,
        produces_kinds=produces_kinds,
        agent=None,
        execution=LlmExecution(
            mode="llm",
            llm_config_ref="dev.llm.openai.fast",
        ),
    )


async def seed_agile_capabilities() -> None:
    """
    Seeds agile artifact authoring capabilities (SABA use case).
    """
    log.info("[capability.seeds.agile] Begin")

    svc = CapabilityService()

    targets: list[GlobalCapabilityCreate] = [
        _llm_cap(
            "cap.agile.generate_epics",
            "Generate Epics",
            "Derives a set of epics from domain context, business goals, and NFRs.",
            ["cam.agile.epic"],
            tags=["astra", "agile", "epics"],
        ),
        _llm_cap(
            "cap.agile.generate_features",
            "Generate Features",
            "Breaks epics into discrete features with descriptions, acceptance criteria, and priority.",
            ["cam.agile.feature"],
            tags=["astra", "agile", "features"],
        ),
        _llm_cap(
            "cap.agile.generate_stories",
            "Generate User Stories",
            "Generates structured user stories (As a… / I want… / So that…) from features and actor analysis.",
            ["cam.agile.story"],
            tags=["astra", "agile", "stories"],
        ),
        _llm_cap(
            "cap.agile.generate_tasks",
            "Generate Tasks",
            "Decomposes user stories into granular implementation tasks with effort estimates.",
            ["cam.agile.task"],
            tags=["astra", "agile", "tasks"],
        ),
        _llm_cap(
            "cap.agile.generate_acceptance_criteria",
            "Generate Acceptance Criteria",
            "Produces Given/When/Then acceptance criteria for user stories.",
            ["cam.agile.acceptance_criteria"],
            tags=["astra", "agile", "acceptance-criteria"],
        ),
    ]

    created = 0
    for cap in targets:
        try:
            existing = await svc.get(cap.id)
            if existing:
                try:
                    await svc.delete(cap.id, actor="seed")
                    log.info("[capability.seeds.agile] replaced: %s (deleted old)", cap.id)
                except AttributeError:
                    log.warning(
                        "[capability.seeds.agile] delete() not available; attempting create() which may fail on unique ID"
                    )
        except Exception:
            pass

        await svc.create(cap, actor="seed")
        log.info("[capability.seeds.agile] created: %s", cap.id)
        created += 1

    log.info("[capability.seeds.agile] Done (created=%d)", created)

# services/capability-service/app/seeds/__init__.py
from __future__ import annotations

import logging
import os

from app.seeds.seed_capabilities import seed_capabilities
# from app.seeds.seed_capabilities_raina import seed_capabilities_raina  # disabled

from app.seeds.seed_packs import seed_packs
# from app.seeds.seed_packs_raina import seed_packs_raina  # disabled

from app.seeds.seed_data_pipeline_capabilities import seed_capabilities as seed_capabilities_data_pipeline
from app.seeds.seed_data_pipeline_packs import seed_data_pipeline_packs

from app.seeds.seed_microservices_capabilities import seed_microservices_capabilities
from app.seeds.seed_microservices_packs import seed_microservices_packs  # ✅ NEW (now enabled)

from app.seeds.seed_agile_capabilities import seed_agile_capabilities

log = logging.getLogger("app.seeds")


async def run_all_seeds() -> None:
    """
    Run all seeders in a safe, idempotent manner.
    Controlled by env flags:

      SEED_CAPABILITIES=1                   -> enable core capabilities seeding (default: 1)
      SEED_CAPABILITIES_RAINA=1             -> enable RainaV2 LLM capabilities seeding (default: disabled)
      SEED_CAPABILITIES_DATA_PIPELINE=1     -> enable Data Pipeline capabilities seeding (default: 1)
      SEED_CAPABILITIES_MICROSERVICES=1     -> enable Microservices pack capabilities seeding (default: 1)
      SEED_CAPABILITIES_AGILE=1             -> enable Agile capabilities seeding (default: 1)

      SEED_PACKS=1                          -> enable core packs seeding (default: 1)
      SEED_PACKS_RAINA=1                    -> enable RainaV2 pack seeding (default: disabled)
      SEED_PACKS_DATA_PIPELINE=1            -> enable Data Pipeline pack seeding (default: 1)
      SEED_PACKS_MICROSERVICES=1            -> enable Microservices pack seeding (default: disabled; enable when needed)
    """

    do_capabilities = os.getenv("SEED_CAPABILITIES", "1") in ("1", "true", "True")
    # do_capabilities_raina = os.getenv("SEED_CAPABILITIES_RAINA", "0") in ("1", "true", "True")
    do_capabilities_data_pipeline = os.getenv("SEED_CAPABILITIES_DATA_PIPELINE", "1") in ("1", "true", "True")
    do_capabilities_microservices = os.getenv("SEED_CAPABILITIES_MICROSERVICES", "1") in ("1", "true", "True")
    do_capabilities_agile = os.getenv("SEED_CAPABILITIES_AGILE", "1") in ("1", "true", "True")

    do_packs = os.getenv("SEED_PACKS", "1") in ("1", "true", "True")
    # do_packs_raina = os.getenv("SEED_PACKS_RAINA", "0") in ("1", "true", "True")
    do_packs_data_pipeline = os.getenv("SEED_PACKS_DATA_PIPELINE", "1") in ("1", "true", "True")
    do_packs_microservices = os.getenv("SEED_PACKS_MICROSERVICES", "1") in ("1", "true", "True")

    # ---- Core capabilities ----
    if do_capabilities:
        await seed_capabilities()
    else:
        log.info("[capability.seeds.capabilities] Skipped via env")

    # Commented out as requested
    # if do_capabilities_raina:
    #     await seed_capabilities_raina()
    # else:
    #     log.info("[capability.seeds.capabilities_raina] Skipped via env")

    # ---- Pack-specific capabilities ----
    if do_capabilities_data_pipeline:
        await seed_capabilities_data_pipeline()
    else:
        log.info("[capability.seeds.data_pipeline_capabilities] Skipped via env")

    if do_capabilities_microservices:
        await seed_microservices_capabilities()
    else:
        log.info("[capability.seeds.microservices_capabilities] Skipped via env")

    if do_capabilities_agile:
        await seed_agile_capabilities()
    else:
        log.info("[capability.seeds.agile_capabilities] Skipped via env")

    # ---- Core packs ----
    if do_packs:
        await seed_packs()
    else:
        log.info("[capability.seeds.packs] Skipped via env")

    # Commented out as requested
    # if do_packs_raina:
    #     await seed_packs_raina()
    # else:
    #     log.info("[capability.seeds.packs_raina] Skipped via env")

    # ---- Pack-specific packs ----
    if do_packs_data_pipeline:
        await seed_data_pipeline_packs()
    else:
        log.info("[capability.seeds.data_pipeline_packs] Skipped via env")

    if do_packs_microservices:
        await seed_microservices_packs()
    else:
        log.info("[capability.seeds.microservices_packs] Skipped via env")

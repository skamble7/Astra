from __future__ import annotations

import logging
import os

from app.seeds.seed_capabilities import seed_capabilities
from app.seeds.seed_capabilities_raina import seed_capabilities_raina  # existing
from app.seeds.seed_pack_inputs import seed_pack_inputs
from app.seeds.seed_packs import seed_packs
from app.seeds.seed_packs_raina import seed_packs_raina  # NEW

log = logging.getLogger("app.seeds")


async def run_all_seeds() -> None:
    """
    Run all seeders in a safe, idempotent manner.
    Controlled by env flags:

      SEED_CAPABILITIES=1          -> enable core capabilities seeding (default: 1)
      SEED_CAPABILITIES_RAINA=1    -> enable RainaV2 LLM capabilities seeding (default: 1)
      SEED_PACK_INPUTS=1           -> enable pack inputs seeding (default: 1)
      SEED_PACKS=1                 -> enable core packs seeding (default: 1)
      SEED_PACKS_RAINA=1           -> enable RainaV2 pack seeding (default: 1)
    """

    do_capabilities = os.getenv("SEED_CAPABILITIES", "1") in ("1", "true", "True")
    do_capabilities_raina = os.getenv("SEED_CAPABILITIES_RAINA", "1") in ("1", "true", "True")
    do_pack_inputs = os.getenv("SEED_PACK_INPUTS", "1") in ("1", "true", "True")
    do_packs = os.getenv("SEED_PACKS", "1") in ("1", "true", "True")
    do_packs_raina = os.getenv("SEED_PACKS_RAINA", "1") in ("1", "true", "True")  # NEW

    if do_capabilities:
        await seed_capabilities()
    else:
        log.info("[capability.seeds.capabilities] Skipped via env")

    if do_capabilities_raina:
        await seed_capabilities_raina()
    else:
        log.info("[capability.seeds.capabilities_raina] Skipped via env")

    if do_pack_inputs:
        await seed_pack_inputs()
    else:
        log.info("[capability.seeds.pack_inputs] Skipped via env")

    if do_packs:
        await seed_packs()
    else:
        log.info("[capability.seeds.packs] Skipped via env")

    if do_packs_raina:
        await seed_packs_raina()
    else:
        log.info("[capability.seeds.packs_raina] Skipped via env")
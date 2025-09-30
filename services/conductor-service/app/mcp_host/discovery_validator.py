# services/conductor-service/app/mcp_host/discovery_validator.py

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable

from app.mcp_host.types import DiscoveryReport

logger = logging.getLogger("app.mcp.discovery")


async def validate(
    *,
    discovery: DiscoveryReport,
    required_tools: Iterable[str] | None,
    policy: Dict[str, Any] | None,
) -> None:
    """
    Validate server features per capability execution policy.
    policy: { validate_tools: bool, validate_resources: bool, validate_prompts: bool, fail_fast: bool }
    """
    policy = policy or {}
    validate_tools = bool(policy.get("validate_tools", True))
    fail_fast = bool(policy.get("fail_fast", True))

    missing: list[str] = []
    if validate_tools and required_tools:
        available = set(discovery.tools or [])
        for t in required_tools:
            if t not in available:
                missing.append(t)

    if missing and fail_fast:
        raise RuntimeError(f"MCP discovery validation failed; missing tools: {missing}")

    if missing:
        logger.warning("MCP discovery: missing tools but continuing: %s", missing)
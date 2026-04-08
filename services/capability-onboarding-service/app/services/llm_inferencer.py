from __future__ import annotations

import json
import logging
import re
from typing import Optional

from fastapi import HTTPException
from polyllm import LLMClient, RemoteConfigLoader

from app.config import settings
from app.models.mcp_onboarding_models import DiscoveredTool, InferredArtifactKind, InferredCapabilityMeta

logger = logging.getLogger("app.services.llm_inferencer")

_SYSTEM_PROMPT = """You are an ASTRA capability metadata specialist.
ASTRA organizes work using GlobalCapabilities and Artifact Kinds.

Naming conventions (MUST follow exactly):

  Capability IDs: cap.<group>.<action>
    Valid groups: domain, data, diagram, catalog, contract, asset, microservices
    Examples: cap.domain.discover_context_map, cap.data.parse_dictionary, cap.asset.fetch_raina_input

  Artifact Kind IDs: cam.<category>.<name>
    Valid categories: diagram, data, catalog, contract, asset
    Examples: cam.diagram.context_map, cam.data.dictionary, cam.asset.repo_snapshot

Given an MCP tool name, description, its JSON input schema, and optionally its output schema,
infer the ASTRA capability metadata that best represents this tool.

Rules:
- id must follow cap.<group>.<action> — use snake_case for action
- kind_id must follow cam.<category>.<name> — use snake_case for name
- group (embedded in id) and category must be one of the valid values listed above
- tags should be 3-6 lowercase strings relevant to the tool's domain
- produces_kinds should list the artifact kinds this capability produces (usually 1-2)
- description should be 1-2 sentences explaining what the capability does
- json_schema in each produces_kinds entry MUST accurately reflect the artifact's data structure:
    * If a Tool Output Schema is provided, derive json_schema directly from its properties
    * If no output schema is provided, infer a realistic schema from the tool's purpose —
      do NOT fall back to a trivial { "result": { "type": "string" } } schema
    * Include the meaningful top-level fields that the artifact would realistically contain
- Choose category based on the artifact's nature:
    * Use "diagram" ONLY if the tool genuinely generates visual diagrams (Mermaid, PlantUML, etc.)
    * Use "data" for structured data, parsed outputs, models, indexes
    * Use "asset" for files, snapshots, raw fetched content
    * Use "catalog" for inventories, registries, discovery results
    * Use "contract" for API specs, interface definitions, schemas

Respond ONLY with a single valid JSON object. No markdown fences, no commentary.
The JSON must have exactly these keys:
{
  "id":          "cap.<group>.<action>",
  "name":        "Human Readable Name",
  "description": "1-2 sentence description.",
  "tags":        ["tag1", "tag2", "tag3"],
  "produces_kinds": [
    {
      "kind_id":     "cam.<category>.<name>",
      "kind_name":   "Human Readable Kind Name",
      "category":    "data",
      "description": "One sentence describing this artifact kind.",
      "json_schema": {
        "type": "object",
        "title": "Human Readable Kind Name",
        "properties": {
          "field_name": { "type": "string", "description": "What this field contains" }
        },
        "required": ["field_name"],
        "additionalProperties": false
      }
    }
  ]
}"""

_FENCE_PATTERN = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.MULTILINE)


async def _build_llm_client() -> LLMClient:
    loader = RemoteConfigLoader()  # reads CONFIG_FORGE_URL from environment
    return await loader.load(settings.llm_config_ref)


class LLMInferencer:
    """Uses polyllm to infer capability metadata from an MCP tool schema."""

    def __init__(self) -> None:
        self._client: Optional[LLMClient] = None

    async def _get_client(self) -> LLMClient:
        if self._client is None:
            self._client = await _build_llm_client()
        return self._client

    async def infer(self, tool: DiscoveredTool) -> InferredCapabilityMeta:
        output_section = (
            f"\nTool Output Schema (JSON):\n{json.dumps(tool.output_schema, indent=2)}\n"
            if tool.output_schema else ""
        )
        user_message = (
            f"MCP Tool Name: {tool.name}\n\n"
            f"Tool Description:\n{tool.description or '(no description provided)'}\n\n"
            f"Tool Input Schema (JSON):\n{json.dumps(tool.input_schema, indent=2)}\n"
            f"{output_section}\n"
            "Infer the ASTRA capability metadata for this tool."
        )

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        logger.info("[LLMInferencer] Running inference for tool: %s", tool.name)

        client = await self._get_client()
        result = await client.chat(messages)
        raw_text = (result.text or "").strip()

        logger.debug("[LLMInferencer] Raw LLM response: %s", raw_text[:500])

        parsed = _parse_json_response(raw_text, tool.name)

        # Validate and coerce via Pydantic
        try:
            meta = InferredCapabilityMeta(
                id=parsed["id"],
                name=parsed["name"],
                description=parsed["description"],
                tags=parsed.get("tags", []),
                produces_kinds=[
                    InferredArtifactKind(
                        kind_id=k["kind_id"],
                        kind_name=k["kind_name"],
                        category=k["category"],
                        description=k.get("description"),
                        json_schema=k.get("json_schema"),
                    )
                    for k in parsed.get("produces_kinds", [])
                ],
            )
        except (KeyError, TypeError) as e:
            logger.error("[LLMInferencer] LLM response missing required fields: %s | raw=%s", e, raw_text[:300])
            raise HTTPException(
                status_code=502,
                detail=f"LLM response was missing required fields: {e}",
            )

        logger.info(
            "[LLMInferencer] Inferred capability: %s → %s",
            tool.name,
            meta.id,
        )
        return meta


def _parse_json_response(text: str, tool_name: str) -> dict:
    """Attempt to parse JSON from the LLM response, with fence-stripping fallback."""
    # First try: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Second try: strip markdown fences
    match = _FENCE_PATTERN.search(text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    logger.error(
        "[LLMInferencer] Could not parse LLM response as JSON for tool '%s': %s",
        tool_name,
        text[:400],
    )
    raise HTTPException(
        status_code=502,
        detail="LLM returned an unparseable response. Please retry.",
    )

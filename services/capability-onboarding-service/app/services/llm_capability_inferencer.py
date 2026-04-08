from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

from fastapi import HTTPException
from polyllm import LLMClient, RemoteConfigLoader

from app.config import settings
from app.models.llm_onboarding_models import InferredLLMCapabilityMeta, LLMInferRequest

logger = logging.getLogger("app.services.llm_capability_inferencer")

_SYSTEM_PROMPT = """You are an ASTRA capability metadata specialist.
ASTRA organizes work using GlobalCapabilities and Artifact Kinds.

Naming conventions (MUST follow exactly):

  Capability IDs: cap.<group>.<action>
    Valid groups: domain, data, diagram, catalog, contract, asset, microservices
    Examples: cap.domain.discover_context_map, cap.data.parse_dictionary, cap.asset.fetch_raina_input

  Artifact Kind IDs: cam.<category>.<name>
    Valid categories: diagram, data, catalog, contract, asset
    Examples: cam.diagram.context_map, cam.data.dictionary, cam.asset.repo_snapshot

Given a free-text description of what an LLM capability should do, infer the ASTRA capability and artifact kind metadata.

Rules:
- capability_id must follow cap.<group>.<action> — use snake_case for action
- kind_id must follow cam.<category>.<name> — use snake_case for name
- group (embedded in capability_id) must be one of: domain, data, diagram, catalog, contract, asset, microservices
- kind_category must be one of: diagram, data, catalog, contract, asset
- tags should be 3-6 lowercase strings relevant to the capability's domain
- description should be 1-2 sentences explaining what the capability does
- output_schema MUST accurately reflect the artifact's data structure:
    * Derive meaningful top-level fields the artifact would realistically contain
    * Do NOT fall back to a trivial { "result": { "type": "string" } } schema
    * Include proper types, descriptions, and required fields
- system_prompt should be a clear, concise instruction to an LLM for generating this artifact kind,
  referencing the key fields it must produce
- natural_key should be the field name in output_schema that best serves as a stable identity
  for the artifact (e.g. "id", "name", "key") — null if no obvious identity field
- strict_json: true unless the output is inherently open-ended (e.g. free text)
- Choose kind_category based on the artifact's nature:
    * "diagram" ONLY if the output is a visual diagram (Mermaid, PlantUML, etc.)
    * "data" for structured data, parsed outputs, models, indexes
    * "asset" for files, snapshots, raw fetched content
    * "catalog" for inventories, registries, discovery results
    * "contract" for API specs, interface definitions, schemas

Respond ONLY with a single valid JSON object. No markdown fences, no commentary.
The JSON must have exactly these keys:
{
  "capability_id": "cap.<group>.<action>",
  "name":          "Human Readable Name",
  "description":   "1-2 sentence description.",
  "group":         "<group>",
  "tags":          ["tag1", "tag2", "tag3"],
  "kind_id":       "cam.<category>.<name>",
  "kind_title":    "Human Readable Kind Name",
  "kind_category": "<category>",
  "kind_aliases":  [],
  "natural_key":   "<field_name or null>",
  "output_schema": {
    "type": "object",
    "title": "Human Readable Kind Name",
    "properties": {
      "field_name": { "type": "string", "description": "What this field contains" }
    },
    "required": ["field_name"],
    "additionalProperties": false
  },
  "system_prompt": "Generate a <kind_title> artifact. Include: <key fields>.",
  "strict_json":   true
}"""

_SYSTEM_PROMPT_WITH_SCHEMA = """You are an ASTRA capability metadata specialist.
ASTRA organizes work using GlobalCapabilities and Artifact Kinds.

Naming conventions (MUST follow exactly):

  Capability IDs: cap.<group>.<action>
    Valid groups: domain, data, diagram, catalog, contract, asset, microservices
    Examples: cap.domain.discover_context_map, cap.data.parse_dictionary, cap.asset.fetch_raina_input

  Artifact Kind IDs: cam.<category>.<name>
    Valid categories: diagram, data, catalog, contract, asset
    Examples: cam.diagram.context_map, cam.data.dictionary, cam.asset.repo_snapshot

The user has provided their own JSON Schema for the output. Your job is to infer the capability and kind metadata AROUND that schema — do NOT modify the schema, use it verbatim as output_schema.

Rules:
- capability_id must follow cap.<group>.<action> — use snake_case for action
- kind_id must follow cam.<category>.<name> — use snake_case for name
- group must be one of: domain, data, diagram, catalog, contract, asset, microservices
- kind_category must be one of: diagram, data, catalog, contract, asset
- tags should be 3-6 lowercase strings relevant to the capability's domain
- description should be 1-2 sentences explaining what the capability does
- system_prompt should be a clear instruction for generating this artifact kind, aligned with the provided schema
- natural_key: the field name in the schema that best serves as stable identity — null if none obvious
- strict_json: true unless the schema explicitly allows additionalProperties

Respond ONLY with a single valid JSON object. No markdown fences, no commentary.
The JSON must have exactly these keys:
{
  "capability_id": "cap.<group>.<action>",
  "name":          "Human Readable Name",
  "description":   "1-2 sentence description.",
  "group":         "<group>",
  "tags":          ["tag1", "tag2", "tag3"],
  "kind_id":       "cam.<category>.<name>",
  "kind_title":    "Human Readable Kind Name",
  "kind_category": "<category>",
  "kind_aliases":  [],
  "natural_key":   "<field_name or null>",
  "output_schema": { "<verbatim user-provided schema>" },
  "system_prompt": "Generate a <kind_title> artifact. Include: <key fields>.",
  "strict_json":   true
}"""

_FENCE_PATTERN = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.MULTILINE)


async def _build_llm_client() -> LLMClient:
    loader = RemoteConfigLoader()  # reads CONFIG_FORGE_URL from environment
    return await loader.load(settings.llm_config_ref)


class LLMCapabilityInferencer:
    """
    Uses the service's own polyllm client to infer LLM capability metadata
    from a free-text intent description and an optional user-provided schema.
    """

    def __init__(self) -> None:
        self._client: Optional[LLMClient] = None

    async def _get_client(self) -> LLMClient:
        if self._client is None:
            self._client = await _build_llm_client()
        return self._client

    async def infer(self, req: LLMInferRequest) -> InferredLLMCapabilityMeta:
        if req.has_schema:
            system_prompt = _SYSTEM_PROMPT_WITH_SCHEMA
            schema_section = (
                f"\nUser-Provided Output Schema (JSON):\n{json.dumps(req.user_schema, indent=2)}\n"
            )
        else:
            system_prompt = _SYSTEM_PROMPT
            schema_section = ""

        user_message = (
            f"Capability Intent:\n{req.intent_text}\n"
            f"{schema_section}\n"
            "Infer the ASTRA capability and artifact kind metadata."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        logger.info("[LLMCapabilityInferencer] Running inference (has_schema=%s)", req.has_schema)

        client = await self._get_client()
        result = await client.chat(messages)
        raw_text = (result.text or "").strip()

        logger.debug("[LLMCapabilityInferencer] Raw LLM response: %s", raw_text[:500])

        parsed = _parse_json_response(raw_text)

        # When user provided their own schema, override the LLM's output_schema with it
        if req.has_schema and req.user_schema:
            parsed["output_schema"] = req.user_schema

        schema_inferred = not req.has_schema

        try:
            meta = InferredLLMCapabilityMeta(
                capability_id=parsed["capability_id"],
                name=parsed["name"],
                description=parsed["description"],
                group=parsed["group"],
                tags=parsed.get("tags", []),
                kind_id=parsed["kind_id"],
                kind_title=parsed["kind_title"],
                kind_category=parsed["kind_category"],
                kind_aliases=parsed.get("kind_aliases", []),
                natural_key=parsed.get("natural_key"),
                output_schema=parsed["output_schema"],
                system_prompt=parsed["system_prompt"],
                strict_json=parsed.get("strict_json", True),
                schema_inferred=schema_inferred,
            )
        except (KeyError, TypeError) as e:
            logger.error(
                "[LLMCapabilityInferencer] LLM response missing required fields: %s | raw=%s",
                e,
                raw_text[:300],
            )
            raise HTTPException(
                status_code=502,
                detail=f"LLM response was missing required fields: {e}",
            )

        logger.info(
            "[LLMCapabilityInferencer] Inferred capability: %s → kind: %s",
            meta.capability_id,
            meta.kind_id,
        )
        return meta


def _parse_json_response(text: str) -> Dict[str, Any]:
    """Attempt to parse JSON from the LLM response, with fence-stripping fallback."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = _FENCE_PATTERN.search(text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    logger.error(
        "[LLMCapabilityInferencer] Could not parse LLM response as JSON: %s",
        text[:400],
    )
    raise HTTPException(
        status_code=502,
        detail="LLM returned an unparseable response. Please retry.",
    )

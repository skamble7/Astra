from __future__ import annotations

import logging

from app.models import PackInputCreate
from app.services.pack_input_service import PackInputService

log = logging.getLogger("app.seeds.pack_inputs")


async def seed_pack_inputs() -> None:
    """
    Seed the Renova input contract.

    Final shape (as provided by frontends/agents):
    {
      "inputs": {
        "repos": [
          {
            "url": "...",
            "revision": "main",
            "subdir": "src",
            "shallow": true,
            "include_globs": ["**/*.cob"],
            "exclude_globs": ["**/test/**"]
          }
        ],
        "extra_context": {
          "...": {}
        }
      }
    }
    """
    svc = PackInputService()

    target = PackInputCreate(
        id="input.renova.repo",
        name="Renova – Repository Inputs",
        description=(
            "Generic repository-driven input for Renova runs. "
            "Defines a list of repositories with revision/subdir/filters and an arbitrary extra_context bag."
        ),
        tags=["renova", "repo", "git", "inputs"],
        json_schema={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "Renova Repository Input",
            "type": "object",
            "additionalProperties": False,
            "required": ["inputs"],
            "properties": {
                "inputs": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["repos"],
                    "properties": {
                        "repos": {
                            "type": "array",
                            "minItems": 1,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["url"],
                                "properties": {
                                    "url": {
                                        "type": "string",
                                        "minLength": 1,
                                        "description": "Repository URL (https/ssh/etc)."
                                    },
                                    "revision": {
                                        "type": "string",
                                        "description": "Branch, tag, or commit-ish (e.g., 'main')."
                                    },
                                    "subdir": {
                                        "type": "string",
                                        "description": "Optional subdirectory where sources live."
                                    },
                                    "shallow": {
                                        "type": "boolean",
                                        "default": True,
                                        "description": "Prefer shallow clone/fetch when supported."
                                    },
                                    "include_globs": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Optional allow-list of glob patterns."
                                    },
                                    "exclude_globs": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Optional deny-list of glob patterns."
                                    }
                                }
                            },
                            "description": "List of repositories to load."
                        },
                        "extra_context": {
                            "type": "object",
                            "additionalProperties": {},
                            "description": "Free-form context map; keys and values are user-defined."
                        }
                    }
                }
            }
        },
        examples=[
            {
                "inputs": {
                    "repos": [
                        {
                            "url": "https://github.com/aws-samples/aws-mainframe-modernization-carddemo",
                            "revision": "main",
                            "subdir": "",
                            "shallow": True,
                            "include_globs": ["**/*.cob", "**/*.cpy"],
                            "exclude_globs": ["**/test/**", "**/.github/**"]
                        }
                    ],
                    "extra_context": {
                        "workspace_mount": "/mnt/src"
                    }
                }
            }
        ],
    )

    # Idempotent replace-by-id
    try:
        existing = await svc.get(target.id)
    except Exception:
        existing = None

    if existing:
        try:
            ok = await svc.delete(target.id, actor="seed")
            if ok:
                log.info("[pack_inputs.seeds] replaced existing: %s", target.id)
            else:
                log.warning("[pack_inputs.seeds] could not delete existing: %s (continuing)", target.id)
        except Exception as e:
            log.warning("[pack_inputs.seeds] delete failed for %s: %s (continuing)", target.id, e)

    created = await svc.create(target, actor="seed")
    log.info("[pack_inputs.seeds] created: %s", created.id)
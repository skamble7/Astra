from __future__ import annotations

import logging

from app.models import PackInputCreate
from app.services.pack_input_service import PackInputService

log = logging.getLogger("app.seeds.pack_inputs")


async def seed_pack_inputs() -> None:
    """
    Seed the Renova input contract (Form-based).

    This schema represents the UI form in the screenshot. Frontends can map it
    to the underlying runner inputs (e.g., populate inputs.repos[0] and inputs.extra).
    """
    svc = PackInputService()

    target = PackInputCreate(
        id="input.renova.repo",  # keep the same ID to replace the existing one
        name="Renova – Minimal COBOL Pack Run Form",
        description=(
            "Form definition for a minimal COBOL pack run. Captures title, description, "
            "shallow clone option, repository (URL/branch/destination), and execution options. "
            "Frontends map this to the lower-level run inputs (e.g., inputs.repos[0], inputs.extra)."
        ),
        tags=["renova", "repo", "git", "inputs", "form"],
        json_schema={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://astra.example/schemas/minimal-cobol-pack-run-form.json",
            "title": "Minimal COBOL Pack Run – Form",
            "type": "object",
            "additionalProperties": False,
            "required": ["title", "repository"],
            "properties": {
                "title": {
                    "type": "string",
                    "title": "Title",
                    "minLength": 1,
                    "default": "Minimal COBOL Pack Run",
                    "description": "Human-friendly name of the run."
                },
                "description": {
                    "type": "string",
                    "title": "Description",
                    "default": "Clone + Parse using MCP servers",
                    "description": "Optional notes about the run."
                },
                "shallowClone": {
                    "type": "boolean",
                    "title": "Shallow clone",
                    "default": True,
                    "description": "Use a shallow git clone (e.g., --depth=1)."
                },
                "repository": {
                    "type": "object",
                    "title": "Repository",
                    "additionalProperties": False,
                    "required": ["gitUrl", "branch", "destination"],
                    "properties": {
                        "gitUrl": {
                            "type": "string",
                            "title": "Git URL",
                            "format": "uri",
                            "default": "https://github.com/aws-samples/aws-mainframe-modernization-carddemo",
                            "description": "HTTPS/SSH URL to the repository to clone."
                        },
                        "branch": {
                            "type": "string",
                            "title": "Branch",
                            "default": "main",
                            "minLength": 1,
                            "description": "Branch or ref to checkout."
                        },
                        "destination": {
                            "type": "string",
                            "title": "Local destination (folder)",
                            "default": "/mnt/src",
                            "minLength": 1,
                            "description": "Filesystem path where the repo will be cloned."
                        }
                    }
                },
                "options": {
                    "type": "object",
                    "title": "Options",
                    "additionalProperties": False,
                    "properties": {
                        "validate": {
                            "type": "boolean",
                            "title": "Validate",
                            "default": True,
                            "description": "Validate against the pack input schema before starting."
                        },
                        "strictJson": {
                            "type": "boolean",
                            "title": "Strict JSON",
                            "default": True,
                            "description": "Require strictly valid JSON when generating inputs."
                        }
                    }
                }
            }
        },
        # Remove existing example value(s)
        examples=[],
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

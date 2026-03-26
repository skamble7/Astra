# services/artifact-service/app/seeds/seed_agile_registry.py
from __future__ import annotations

from typing import Any, Dict, List

LATEST = "1.0.0"

DEFAULT_NARRATIVES_SPEC: Dict[str, Any] = {
    "allowed_formats": ["markdown", "asciidoc"],
    "default_format": "markdown",
    "max_length_chars": 20000,
    "allowed_locales": ["en-US"],
}

KIND_DOCS: List[Dict[str, Any]] = [
    # -------------------------------------------------------------------------
    # Agile Artifact Kinds  (category: agile)
    # -------------------------------------------------------------------------
    {
        "_id": "cam.agile.epic",
        "title": "Epic",
        "category": "agile",
        "aliases": [],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["title", "description"],
                    "properties": {
                        "title": {"type": "string", "minLength": 1},
                        "description": {"type": "string", "minLength": 1},
                        "business_value": {"type": ["string", "null"]},
                        "acceptance_criteria": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": [],
                        },
                        "priority": {
                            "type": ["string", "null"],
                            "enum": ["must-have", "should-have", "could-have", "wont-have", None],
                        },
                        "features": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": [],
                            "description": "IDs or titles of child features.",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": [],
                        },
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": (
                        "Generate a structured agile epic from domain context, business goals, "
                        "and NFRs. Output JSON strictly matching the schema."
                    ),
                    "strict_json": True,
                },
            }
        ],
        "narratives_spec": DEFAULT_NARRATIVES_SPEC,
    },
    {
        "_id": "cam.agile.feature",
        "title": "Feature",
        "category": "agile",
        "aliases": [],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["title", "description"],
                    "properties": {
                        "title": {"type": "string", "minLength": 1},
                        "description": {"type": "string", "minLength": 1},
                        "epic_ref": {
                            "type": ["string", "null"],
                            "description": "Parent epic ID or title.",
                        },
                        "business_value": {"type": ["string", "null"]},
                        "acceptance_criteria": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": [],
                        },
                        "priority": {
                            "type": ["string", "null"],
                            "enum": ["must-have", "should-have", "could-have", "wont-have", None],
                        },
                        "stories": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": [],
                            "description": "IDs or titles of child user stories.",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": [],
                        },
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": (
                        "Break the provided epic into discrete features with descriptions, "
                        "acceptance criteria, and priority. Output JSON strictly matching the schema."
                    ),
                    "strict_json": True,
                },
            }
        ],
        "narratives_spec": DEFAULT_NARRATIVES_SPEC,
    },
    {
        "_id": "cam.agile.story",
        "title": "User Story",
        "category": "agile",
        "aliases": ["cam.agile.user_story"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["title", "as_a", "i_want", "so_that"],
                    "properties": {
                        "title": {"type": "string", "minLength": 1},
                        "as_a": {
                            "type": "string",
                            "minLength": 1,
                            "description": "Actor/persona (e.g. 'registered user').",
                        },
                        "i_want": {
                            "type": "string",
                            "minLength": 1,
                            "description": "The capability or action desired.",
                        },
                        "so_that": {
                            "type": "string",
                            "minLength": 1,
                            "description": "The benefit or outcome.",
                        },
                        "feature_ref": {
                            "type": ["string", "null"],
                            "description": "Parent feature ID or title.",
                        },
                        "acceptance_criteria": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": [],
                        },
                        "story_points": {"type": ["integer", "null"], "minimum": 0},
                        "priority": {
                            "type": ["string", "null"],
                            "enum": ["must-have", "should-have", "could-have", "wont-have", None],
                        },
                        "tasks": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": [],
                            "description": "IDs or titles of child tasks.",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": [],
                        },
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": (
                        "Generate structured user stories in 'As a / I want / So that' format "
                        "from features and actor analysis. Output JSON strictly matching the schema."
                    ),
                    "strict_json": True,
                },
            }
        ],
        "narratives_spec": DEFAULT_NARRATIVES_SPEC,
    },
    {
        "_id": "cam.agile.task",
        "title": "Task",
        "category": "agile",
        "aliases": [],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["title", "description"],
                    "properties": {
                        "title": {"type": "string", "minLength": 1},
                        "description": {"type": "string", "minLength": 1},
                        "story_ref": {
                            "type": ["string", "null"],
                            "description": "Parent user story ID or title.",
                        },
                        "assignee": {"type": ["string", "null"]},
                        "estimate_hours": {"type": ["number", "null"], "minimum": 0},
                        "status": {
                            "type": ["string", "null"],
                            "enum": ["todo", "in-progress", "done", "blocked", None],
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": [],
                        },
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": (
                        "Decompose the provided user story into granular implementation tasks "
                        "with effort estimates. Output JSON strictly matching the schema."
                    ),
                    "strict_json": True,
                },
            }
        ],
        "narratives_spec": DEFAULT_NARRATIVES_SPEC,
    },
    {
        "_id": "cam.agile.acceptance_criteria",
        "title": "Acceptance Criteria",
        "category": "agile",
        "aliases": [],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["story_ref", "criteria"],
                    "properties": {
                        "story_ref": {
                            "type": "string",
                            "minLength": 1,
                            "description": "ID or title of the parent user story.",
                        },
                        "criteria": {
                            "type": "array",
                            "minItems": 1,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["given", "when", "then"],
                                "properties": {
                                    "given": {"type": "string", "minLength": 1},
                                    "when": {"type": "string", "minLength": 1},
                                    "then": {"type": "string", "minLength": 1},
                                    "label": {"type": ["string", "null"]},
                                },
                            },
                        },
                        "notes": {"type": ["string", "null"]},
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": (
                        "Produce Given/When/Then acceptance criteria for the provided user story. "
                        "Output JSON strictly matching the schema."
                    ),
                    "strict_json": True,
                },
            }
        ],
        "narratives_spec": DEFAULT_NARRATIVES_SPEC,
    },
    {
        "_id": "cam.agile.sprint_plan",
        "title": "Sprint Plan",
        "category": "agile",
        "aliases": [],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["sprint_number", "goal", "stories"],
                    "properties": {
                        "sprint_number": {"type": "integer", "minimum": 1},
                        "goal": {
                            "type": "string",
                            "minLength": 1,
                            "description": "Sprint goal — one-sentence statement of intent.",
                        },
                        "start_date": {"type": ["string", "null"], "format": "date"},
                        "end_date": {"type": ["string", "null"], "format": "date"},
                        "stories": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["title"],
                                "properties": {
                                    "title": {"type": "string", "minLength": 1},
                                    "story_points": {"type": ["integer", "null"], "minimum": 0},
                                    "priority": {
                                        "type": ["string", "null"],
                                        "enum": ["must-have", "should-have", "could-have", "wont-have", None],
                                    },
                                    "assignee": {"type": ["string", "null"]},
                                    "status": {
                                        "type": ["string", "null"],
                                        "enum": ["todo", "in-progress", "done", "blocked", None],
                                    },
                                },
                            },
                        },
                        "capacity_points": {"type": ["integer", "null"], "minimum": 0},
                        "team_members": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": [],
                        },
                        "notes": {"type": ["string", "null"]},
                    },
                },
                "additional_props_policy": "forbid",
                "prompt": {
                    "system": (
                        "Compose a sprint plan from the provided backlog stories, team capacity, "
                        "and sprint goal. Output JSON strictly matching the schema."
                    ),
                    "strict_json": True,
                },
            }
        ],
        "narratives_spec": DEFAULT_NARRATIVES_SPEC,
    },
]

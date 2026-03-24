from __future__ import annotations

from typing import Any, Dict, List

# ─────────────────────────────────────────────────────────────────────────────
# Static Mermaid diagram recipe templates served by GET /onboarding/llm/diagram-recipe-templates.
# These map directly to DiagramRecipeSpec from libs/astra-models.
# The "id" field is used as a stable key to reference selected recipes.
# ─────────────────────────────────────────────────────────────────────────────

DIAGRAM_RECIPE_TEMPLATES: List[Dict[str, Any]] = [
    {
        "id": "mermaid.flowchart",
        "title": "Flowchart",
        "view": "flowchart",
        "language": "mermaid",
        "description": "High-level data flow or process overview.",
        "prompt": {
            "system": (
                "Generate a Mermaid flowchart (LR direction) that visualises the key data "
                "flows or processing steps in this artifact. Use meaningful node labels drawn "
                "from the artifact's fields."
            ),
            "strict_text": True,
            "prompt_rev": 1,
        },
    },
    {
        "id": "mermaid.mindmap",
        "title": "Mindmap",
        "view": "mindmap",
        "language": "mermaid",
        "description": "Hierarchical concept map of the artifact's structure.",
        "prompt": {
            "system": (
                "Generate a Mermaid mindmap for this artifact. Use the artifact name or kind "
                "as the root and expand key fields as branches."
            ),
            "strict_text": True,
            "prompt_rev": 1,
        },
    },
    {
        "id": "mermaid.sequence",
        "title": "Sequence Diagram",
        "view": "sequence",
        "language": "mermaid",
        "description": "Sequence of interactions (useful for workflow or process artifacts).",
        "prompt": {
            "system": (
                "Generate a Mermaid sequence diagram that shows how components or actors "
                "in this artifact interact with each other."
            ),
            "strict_text": True,
            "prompt_rev": 1,
        },
    },
    {
        "id": "mermaid.er",
        "title": "Entity Relationship",
        "view": "er",
        "language": "mermaid",
        "description": "Entity-relationship diagram (useful for data/catalog artifacts).",
        "prompt": {
            "system": (
                "Generate a Mermaid ER diagram for the entities and relationships described "
                "in this artifact."
            ),
            "strict_text": True,
            "prompt_rev": 1,
        },
    },
    {
        "id": "mermaid.class",
        "title": "Class Diagram",
        "view": "class",
        "language": "mermaid",
        "description": "Class or domain model diagram (useful for contract/domain artifacts).",
        "prompt": {
            "system": (
                "Generate a Mermaid class diagram that models the types, fields, and "
                "relationships described in this artifact."
            ),
            "strict_text": True,
            "prompt_rev": 1,
        },
    },
]

# Lookup by ID for fast access during registration
DIAGRAM_RECIPE_TEMPLATES_BY_ID: Dict[str, Dict[str, Any]] = {
    t["id"]: t for t in DIAGRAM_RECIPE_TEMPLATES
}

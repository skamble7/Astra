# services/artifact-service/app/seeds/seed_kind_registry_cobol_modernization.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from app.dal.kind_registry_dal import upsert_kind

LATEST = "1.0.0"

DEFAULT_NARRATIVES_SPEC: Dict[str, Any] = {
    "allowed_formats": ["markdown", "asciidoc"],
    "default_format": "markdown",
    "max_length_chars": 20000,
    "allowed_locales": ["en-US"],
}

# ─────────────────────────────────────────────────────────────
# COBOL Modernization kinds only
# ─────────────────────────────────────────────────────────────
KIND_DOCS: List[Dict[str, Any]] = [
    {
        "_id": "cam.cobol.program",
        "title": "COBOL Program",
        "category": "cobol",
        "aliases": [],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": True,
                    "required": ["program_id", "source"],
                    "properties": {
                        "program_id": {"type": ["string", "null"]},
                        "source": {
                            "type": ["object", "null"],
                            "additionalProperties": True,
                            "properties": {
                                "relpath": {"type": ["string", "null"]},
                                "sha256": {"type": ["string", "null"]},
                            },
                        },
                        "divisions": {
                            "type": ["object", "null"],
                            "additionalProperties": True,
                            "properties": {
                                "identification": {
                                    "type": ["object", "null"],
                                    "additionalProperties": True,
                                },
                                "environment": {
                                    "type": ["object", "null"],
                                    "additionalProperties": True,
                                },
                                "data": {
                                    "type": ["object", "null"],
                                    "additionalProperties": True,
                                },
                                "procedure": {
                                    "type": ["object", "null"],
                                    "additionalProperties": True,
                                },
                            },
                        },
                        "paragraphs": {
                            "type": ["array", "null"],
                            "items": {
                                "type": "object",
                                "additionalProperties": True,
                                "required": ["name"],
                                "properties": {
                                    "name": {"type": ["string", "null"]},
                                    "performs": {
                                        "type": ["array", "null"],
                                        "items": {"type": "string"},
                                    },
                                    "calls": {
                                        "type": ["array", "null"],
                                        "items": {
                                            "type": "object",
                                            "additionalProperties": True,
                                            "properties": {
                                                "target": {
                                                    "type": ["string", "null"],
                                                    "description": "PROGRAM-ID if resolvable, else literal",
                                                },
                                                "dynamic": {
                                                    "type": [
                                                        "boolean",
                                                        "string",
                                                        "null",
                                                    ]
                                                },
                                            },
                                        },
                                    },
                                    "io_ops": {
                                        "type": ["array", "null"],
                                        "items": {
                                            "type": "object",
                                            "additionalProperties": True,
                                            "properties": {
                                                "op": {"type": ["string", "null"]},
                                                "dataset_ref": {
                                                    "type": ["string", "null"]
                                                },
                                                "fields": {
                                                    "type": ["array", "null"],
                                                    "items": {"type": "string"},
                                                },
                                            },
                                        },
                                    },
                                },
                            },
                        },
                        "copybooks_used": {
                            "type": ["array", "null"],
                            "items": {"type": "string"},
                        },
                        "notes": {
                            "type": ["array", "null"],
                            "items": {"type": "string"},
                        },
                    },
                },
                "additional_props_policy": "allow",
                "prompt": {
                    "system": "Normalize ProLeap/cb2xml output into this canonical shape. Preserve names; do not invent CALL targets.",
                    "strict_json": True,
                },
                "depends_on": {
                    "hard": ["cam.asset.source_index"],
                    "soft": ["cam.cobol.copybook"],
                    "context_hint": "Map `source.relpath` to a file in Source Index. Collect copybook names used.",
                },
                "identity": {"natural_key": ["program_id"]},
                "examples": [
                    {
                        "program_id": "POSTTRAN",
                        "source": {"relpath": "batch/POSTTRAN.cbl", "sha256": "..."},
                        "divisions": {
                            "identification": {},
                            "environment": {},
                            "data": {},
                            "procedure": {},
                        },
                        "paragraphs": [
                            {
                                "name": "MAIN",
                                "performs": ["VALIDATE-INPUT"],
                                "calls": [],
                                "io_ops": [],
                            }
                        ],
                    }
                ],
                "diagram_recipes": [
                    {
                        "id": "program.mindmap",
                        "title": "Program → Divisions → Paragraphs (Mindmap)",
                        "view": "mindmap",
                        "language": "mermaid",
                        "description": "High-level overview: program root, divisions, and paragraph nodes.",
                        "template": """mindmap
  root(({{ data.program_id }}))
  {% if data.divisions and data.divisions.identification %}Identification{% endif %}
  {% if data.divisions and data.divisions.environment %}Environment{% endif %}
  {% if data.divisions and data.divisions.data %}Data{% endif %}
  Procedure
    {% for p in (data.paragraphs or []) %}{{ p.name }}
    {% endfor %}
classDef divisions fill:#eee,stroke:#999;""",
                    },
                    {
                        "id": "program.sequence",
                        "title": "Paragraph CALL / PERFORM Sequence",
                        "view": "sequence",
                        "language": "mermaid",
                        "description": "Dynamic interaction across paragraphs and called programs.",
                        "prompt": {
                            "system": "Given the canonical cam.cobol.program JSON, emit Mermaid sequence diagram instructions describing PERFORM and CALL interactions. Use paragraph names and PROGRAM-ID targets. Do not fabricate nodes.",
                            "strict_text": True,
                        },
                        "renderer_hints": {"wrap": True},
                    },
                    {
                        "id": "program.flowchart",
                        "title": "Paragraph PERFORM Flow",
                        "view": "flowchart",
                        "language": "mermaid",
                        "description": "Control flow between paragraphs via PERFORM edges.",
                        "template": """flowchart TD
  START([{{ data.program_id }} START])
  {% for p in (data.paragraphs or []) %}
  {{ p.name | replace("-", "_") }}([{{ p.name }}])
  {% endfor %}
  {% if (data.paragraphs or [])|length > 0 %}START --> {{ data.paragraphs[0].name | replace("-", "_") }}{% endif %}
  {% for p in (data.paragraphs or []) %}
    {% for t in (p.performs or []) %}
  {{ p.name | replace("-", "_") }} --> {{ t | replace("-", "_") }}
    {% endfor %}
  {% endfor %}
  END([END])""",
                    },
                ],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
            }
        ],
    },
    {
        "_id": "cam.cobol.copybook",
        "title": "COBOL Copybook",
        "category": "cobol",
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": True,
                    "required": ["name", "source", "items"],
                    "properties": {
                        "name": {"type": ["string", "null"]},
                        "source": {
                            "type": ["object", "null"],
                            "additionalProperties": True,
                            "properties": {
                                "relpath": {"type": ["string", "null"]},
                                "sha256": {"type": ["string", "null"]},
                            },
                        },
                        "items": {
                            "type": ["array", "null"],
                            "items": {"$ref": "#/$defs/CopyItem"},
                        },
                    },
                    "$defs": {
                        "CopyItem": {
                            "type": "object",
                            "additionalProperties": True,
                            "required": ["level", "name"],
                            "properties": {
                                "level": {"type": ["string", "integer", "null"]},
                                "name": {"type": ["string", "null"]},
                                "picture": {"type": ["string", "null"], "default": ""},
                                "occurs": {
                                    "type": ["integer", "string", "object", "null"]
                                },
                                "children": {
                                    "type": ["array", "null"],
                                    "items": {"$ref": "#/$defs/CopyItem"},
                                },
                            },
                        }
                    },
                },
                "additional_props_policy": "allow",
                "prompt": {
                    "system": "Normalize copybook AST into a strict tree. Do not lose levels or PIC clauses.",
                    "strict_json": True,
                },
                "depends_on": {"hard": ["cam.asset.source_index"]},
                "identity": {"natural_key": ["name"]},
                "examples": [
                    {
                        "name": "CUSTREC",
                        "source": {"relpath": "copy/CUSTREC.cpy", "sha256": "..."},
                        "items": [
                            {
                                "level": "01",
                                "name": "CUST-REC",
                                "picture": "",
                                "children": [
                                    {
                                        "level": "05",
                                        "name": "CUST-ID",
                                        "picture": "X(10)",
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "diagram_recipes": [
                    {
                        "id": "copybook.mindmap",
                        "title": "Copybook Fields Mindmap",
                        "view": "mindmap",
                        "language": "mermaid",
                        "description": "Hierarchy of fields by levels.",
                        "template": """mindmap
  root(({{ data.name }}))
  {% for item in (data.items or []) %}
  {{ item.level }} {{ item.name }}
    {% for c in (item.children or []) %}{{ c.level }} {{ c.name }}
    {% endfor %}
  {% endfor %}""",
                    }
                ],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
            }
        ],
    },
    {
        "_id": "cam.jcl.job",
        "title": "JCL Job",
        "category": "cobol",
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": True,
                    "required": ["job_name", "source", "steps"],
                    "properties": {
                        "job_name": {"type": ["string", "null"]},
                        "source": {
                            "type": ["object", "null"],
                            "additionalProperties": True,
                            "properties": {
                                "relpath": {"type": ["string", "null"]},
                                "sha256": {"type": ["string", "null"]},
                            },
                        },
                        "steps": {
                            "type": ["array", "null"],
                            "items": {
                                "type": "object",
                                "additionalProperties": True,
                                "required": ["step_name"],
                                "properties": {
                                    "step_name": {"type": ["string", "null"]},
                                    "seq": {"type": ["integer", "string", "null"]},
                                    "program": {"type": ["string", "null"]},
                                    "condition": {"type": ["string", "null"]},
                                    "dds": {
                                        "type": ["array", "null"],
                                        "items": {
                                            "type": "object",
                                            "additionalProperties": True,
                                            "required": ["ddname"],
                                            "properties": {
                                                "ddname": {"type": ["string", "null"]},
                                                "dataset": {"type": ["string", "null"]},
                                                "direction": {
                                                    "type": ["string", "null"]
                                                },
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
                "additional_props_policy": "allow",
                "prompt": {
                    "system": "Parse JCL into an ordered list of steps with DD statements. Keep program names as written.",
                    "strict_json": True,
                },
                "depends_on": {"hard": ["cam.asset.source_index"]},
                "identity": {"natural_key": ["job_name"]},
                "examples": [
                    {
                        "job_name": "POSTTRAN",
                        "source": {"relpath": "batch/POSTTRAN.jcl", "sha256": "..."},
                        "steps": [
                            {
                                "step_name": "STEP1",
                                "seq": 1,
                                "program": "POSTTRAN",
                                "dds": [
                                    {
                                        "ddname": "INFILE",
                                        "dataset": "TRAN.IN",
                                        "direction": "IN",
                                    },
                                    {
                                        "ddname": "OUTFILE",
                                        "dataset": "LEDGER.OUT",
                                        "direction": "OUT",
                                    },
                                ],
                            }
                        ],
                    }
                ],
                "diagram_recipes": [
                    {
                        "id": "jcl.flow",
                        "title": "JCL Job Flow (Steps)",
                        "view": "flowchart",
                        "language": "mermaid",
                        "description": "Simple TD flow through steps by seq, annotated with program names.",
                        "template": """flowchart TD
  START([{{ data.job_name }} START])
  {% for s in (data.steps or [])|sort(attribute='seq') %}
  {{ s.step_name }}([{{ s.step_name }}\\n{{ s.program }}])
  {% endfor %}
  {% for s in (data.steps or [])|sort(attribute='seq') %}
    {% set next = loop.index0 + 1 %}
    {% if next < ((data.steps or [])|length) %}
  {{ data.steps[loop.index0].step_name }} --> {{ data.steps[next].step_name }}
    {% endif %}
  {% endfor %}
  END([END])""",
                    }
                ],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
            }
        ],
    },
    {
        "_id": "cam.jcl.step",
        "title": "JCL Step",
        "category": "cobol",
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": True,
                    "required": ["job_name", "step_name"],
                    "properties": {
                        "job_name": {"type": ["string", "null"]},
                        "step_name": {"type": ["string", "null"]},
                        "seq": {"type": ["integer", "string", "null"]},
                        "program": {"type": ["string", "null"]},
                        "dds": {
                            "type": ["array", "null"],
                            "items": {
                                "type": "object",
                                "additionalProperties": True,
                                "required": ["ddname"],
                                "properties": {
                                    "ddname": {"type": ["string", "null"]},
                                    "dataset": {"type": ["string", "null"]},
                                    "direction": {"type": ["string", "null"]},
                                },
                            },
                        },
                    },
                },
                "additional_props_policy": "allow",
                "prompt": {
                    "system": "Emit one strict record per JCL step to simplify graph indexing.",
                    "strict_json": True,
                },
                "depends_on": {"hard": ["cam.jcl.job"]},
                "identity": {"natural_key": ["job_name", "step_name"]},
                "examples": [
                    {
                        "job_name": "POSTTRAN",
                        "step_name": "STEP1",
                        "seq": 1,
                        "program": "POSTTRAN",
                        "dds": [
                            {
                                "ddname": "INFILE",
                                "dataset": "TRAN.IN",
                                "direction": "IN",
                            }
                        ],
                    }
                ],
                "diagram_recipes": [
                    {
                        "id": "jcl.step.io",
                        "title": "JCL Step IO",
                        "view": "flowchart",
                        "language": "mermaid",
                        "description": "Visualize datasets in/out of a step.",
                        "template": """flowchart LR
  {{ data.step_name }}([{{ data.step_name }}\\n{{ data.program }}])
  {% for d in (data.dds or []) %}
    {% if d.direction == "IN" or d.direction == "INOUT" %}
  {{ d.ddname | replace("-", "_") }}([{{ d.dataset or d.ddname }}]) --> {{ data.step_name }}
    {% endif %}
    {% if d.direction == "OUT" or d.direction == "INOUT" %}
  {{ data.step_name }} --> {{ d.ddname | replace("-", "_") }}([{{ d.dataset or d.ddname }}])
    {% endif %}
  {% endfor %}""",
                    }
                ],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
            }
        ],
    },
    {
        "_id": "cam.cics.transaction",
        "title": "CICS Transaction Map",
        "category": "cobol",
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": True,
                    "required": ["region", "transactions"],
                    "properties": {
                        "region": {"type": ["string", "null"]},
                        "transactions": {
                            "type": ["array", "null"],
                            "items": {
                                "type": "object",
                                "additionalProperties": True,
                                "required": ["tranid"],
                                "properties": {
                                    "tranid": {"type": ["string", "null"]},
                                    "program": {"type": ["string", "null"]},
                                    "mapset": {"type": ["string", "null"]},
                                    "commarea": {"type": ["string", "null"]},
                                },
                            },
                        },
                    },
                },
                "additional_props_policy": "allow",
                "prompt": {
                    "system": "Normalize CICS catalogs into a simple transaction map.",
                    "strict_json": True,
                },
                "depends_on": {"soft": ["cam.asset.source_index"]},
                "identity": {"natural_key": ["region"]},
                "examples": [
                    {
                        "region": "CICSPROD",
                        "transactions": [
                            {"tranid": "PAY1", "program": "PAYMENT"},
                            {"tranid": "BAL1", "program": "BALENQ"},
                        ],
                    }
                ],
                "diagram_recipes": [
                    {
                        "id": "cics.map",
                        "title": "CICS Transaction → Program",
                        "view": "flowchart",
                        "language": "mermaid",
                        "description": "Map tranid to program; optional mapset/commarea labels.",
                        "template": """flowchart LR
  subgraph {{ data.region }}
  {% for t in (data.transactions or []) %}
  {{ t.tranid }}([{{ t.tranid }}]) --> {{ (t.program or "UNKNOWN") | replace("-", "_") }}([{{ t.program or "UNKNOWN" }}])
  {% endfor %}
  end""",
                    }
                ],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
            }
        ],
    },
    {
        "_id": "cam.cobol.ast_proleap",
        "title": "COBOL AST (ProLeap)",
        "category": "cobol",
        "aliases": ["ext.proleap.ast", "cam.cobol.ast.proleap"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": True,
                    "required": ["parser", "source", "ast"],
                    "properties": {
                        "parser": {
                            "type": "object",
                            "additionalProperties": True,
                            "required": ["name", "version"],
                            "properties": {
                                "name": {
                                    "type": ["string", "null"],
                                    "const": "proleap",
                                },
                                "version": {"type": ["string", "null"]},
                                "grammar": {"type": ["string", "null"]},
                                "flags": {
                                    "type": ["array", "null"],
                                    "items": {"type": "string"},
                                },
                            },
                        },
                        "source": {
                            "type": "object",
                            "additionalProperties": True,
                            "required": ["relpath"],
                            "properties": {
                                "relpath": {"type": ["string", "null"]},
                                "sha256": {"type": ["string", "null"]},
                                "language_hint": {"type": ["string", "null"]},
                                "encoding": {"type": ["string", "null"]},
                            },
                        },
                        "ast": {
                            "type": ["object", "array", "null"],
                            "description": "ProLeap AST as JSON (preserve original node kinds and fields).",
                            "additionalProperties": True,
                        },
                        "index": {
                            "type": ["object", "null"],
                            "description": "Optional node index: id→{kind, range, parent, children}.",
                            "additionalProperties": True,
                        },
                        "ranges": {
                            "type": ["object", "null"],
                            "description": "Optional text ranges map: nodeId → {start:{line,col,offset}, end:{...}}",
                            "additionalProperties": True,
                        },
                        "stats": {
                            "type": ["object", "null"],
                            "properties": {
                                "node_count": {"type": ["integer", "string", "null"]},
                                "kinds_histogram": {
                                    "type": ["object", "null"],
                                    "additionalProperties": {"type": "integer"},
                                },
                            },
                            "additionalProperties": True,
                        },
                        "issues": {
                            "type": ["array", "null"],
                            "items": {
                                "type": "object",
                                "additionalProperties": True,
                                "properties": {
                                    "severity": {
                                        "type": ["string", "null"],
                                        "enum": ["error", "warning", "info", None],
                                    },
                                    "message": {"type": ["string", "null"]},
                                    "range": {
                                        "type": ["object", "null"],
                                        "additionalProperties": True,
                                    },
                                },
                            },
                        },
                    },
                },
                "additional_props_policy": "allow",
                "prompt": {
                    "system": "Do not transform—store ProLeap AST verbatim in `ast`. Only add lightweight metadata in `parser`, `source`, `stats`, `issues`.",
                    "strict_json": True,
                },
                "depends_on": {
                    "hard": ["cam.asset.source_index"],
                    "context_hint": "Map `source.relpath` to Source Index; attach file hash if available.",
                },
                "identity": {"natural_key": ["source.relpath", "parser.version"]},
                "examples": [
                    {
                        "parser": {
                            "name": "proleap",
                            "version": "1.10.0",
                            "grammar": "COBOL85",
                        },
                        "source": {"relpath": "batch/POSTTRAN.cbl", "sha256": "..."},
                        "ast": {"type": "CompilationUnit", "children": []},
                        "stats": {"node_count": 4821},
                    }
                ],
                "diagram_recipes": [
                    {
                        "id": "ast.kinds.mindmap",
                        "title": "AST Node Kinds (Mindmap)",
                        "view": "mindmap",
                        "language": "mermaid",
                        "description": "Top node kinds grouped by frequency.",
                        "prompt": {
                            "system": "From `stats.kinds_histogram`, emit a Mermaid mindmap with root 'AST' and child nodes as kinds with counts.",
                            "strict_text": True,
                        },
                    },
                    {
                        "id": "ast.flowchart",
                        "title": "High-level AST Shape",
                        "view": "flowchart",
                        "language": "mermaid",
                        "description": "CompilationUnit → Divisions → Sections → Paragraphs.",
                        "prompt": {
                            "system": "Summarize the top 2–3 levels of the AST into a flowchart. Do not list more than 50 nodes.",
                            "strict_text": True,
                        },
                    },
                ],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
            }
        ],
    },
    {
        "_id": "cam.cobol.asg_proleap",
        "title": "COBOL ASG (ProLeap)",
        "category": "cobol",
        "aliases": ["ext.proleap.asg", "cam.cobol.asg.proleap"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [
            {
                "version": LATEST,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": True,
                    "required": ["parser", "source", "asg"],
                    "properties": {
                        "parser": {
                            "type": "object",
                            "additionalProperties": True,
                            "required": ["name", "version"],
                            "properties": {
                                "name": {
                                    "type": ["string", "null"],
                                    "const": "proleap",
                                },
                                "version": {"type": ["string", "null"]},
                                "grammar": {"type": ["string", "null"]},
                            },
                        },
                        "source": {
                            "type": "object",
                            "additionalProperties": True,
                            "required": ["relpath"],
                            "properties": {
                                "relpath": {"type": ["string", "null"]},
                                "sha256": {"type": ["string", "null"]},
                            },
                        },
                        "asg": {
                            "type": ["object", "null"],
                            "description": "Abstract Semantic Graph (symbols, references, cross-links, calls, I/O, copybook binds).",
                            "additionalProperties": True,
                        },
                        "symbol_table": {
                            "type": ["object", "null"],
                            "description": "Optional extracted symbol table: name→descriptor.",
                            "additionalProperties": True,
                        },
                        "xrefs": {
                            "type": ["array", "null"],
                            "description": "Optional cross-references list (symbol↔uses).",
                            "items": {
                                "type": "object",
                                "additionalProperties": True,
                                "properties": {
                                    "symbol": {"type": ["string", "null"]},
                                    "kind": {"type": ["string", "null"]},
                                    "uses": {
                                        "type": ["array", "null"],
                                        "items": {
                                            "type": "object",
                                            "additionalProperties": True,
                                            "properties": {
                                                "range": {
                                                    "type": ["object", "null"],
                                                    "additionalProperties": True,
                                                },
                                                "context": {"type": ["string", "null"]},
                                            },
                                        },
                                    },
                                },
                            },
                        },
                        "call_graph": {
                            "type": ["object", "null"],
                            "description": "Call graph summary for this source: nodes, edges, dynamic flags.",
                            "additionalProperties": True,
                        },
                        "io_catalog": {
                            "type": ["array", "null"],
                            "description": "Detected file/table interactions.",
                            "items": {
                                "type": "object",
                                "additionalProperties": True,
                                "properties": {
                                    "op": {"type": ["string", "null"]},
                                    "dataset_ref": {"type": ["string", "null"]},
                                    "fields": {
                                        "type": ["array", "null"],
                                        "items": {"type": "string"},
                                    },
                                },
                            },
                        },
                        "issues": {
                            "type": ["array", "null"],
                            "items": {
                                "type": "object",
                                "additionalProperties": True,
                                "properties": {
                                    "severity": {
                                        "type": ["string", "null"],
                                        "enum": ["error", "warning", "info", None],
                                    },
                                    "message": {"type": ["string", "null"]},
                                },
                            },
                        },
                    },
                },
                "additional_props_policy": "allow",
                "prompt": {
                    "system": "Store ProLeap ASG verbatim in `asg`. If only AST is available, derive minimal ASG (symbols, refs, calls) without altering names.",
                    "strict_json": True,
                },
                "depends_on": {
                    "hard": ["cam.cobol.ast_proleap"],
                    "soft": ["cam.asset.source_index"],
                    "context_hint": "If the ASG is computed from AST, record the parser version used for derivation.",
                },
                "identity": {"natural_key": ["source.relpath", "parser.version"]},
                "examples": [
                    {
                        "parser": {
                            "name": "proleap",
                            "version": "1.10.0",
                            "grammar": "COBOL85",
                        },
                        "source": {"relpath": "batch/POSTTRAN.cbl", "sha256": "..."},
                        "asg": {
                            "program_id": "POSTTRAN",
                            "symbols": {"WS-VAR-1": {"kind": "data", "level": "77"}},
                            "calls": [{"target": "VALIDATE", "dynamic": False}],
                            "performs": [{"from": "MAIN", "to": "VALIDATE-INPUT"}],
                        },
                        "call_graph": {
                            "nodes": ["MAIN", "VALIDATE-INPUT"],
                            "edges": [["MAIN", "VALIDATE-INPUT"]],
                        },
                    }
                ],
                "diagram_recipes": [
                    {
                        "id": "asg.callgraph.sequence",
                        "title": "Call / Perform Sequence",
                        "view": "sequence",
                        "language": "mermaid",
                        "description": "Sequence of PERFORM and CALL interactions.",
                        "prompt": {
                            "system": "Render a Mermaid sequence diagram from `asg.calls` and `asg.performs`. Do not invent nodes.",
                            "strict_text": True,
                        },
                    },
                    {
                        "id": "asg.symbols.class",
                        "title": "Symbols & Scopes (Class Diagram)",
                        "view": "class",
                        "language": "mermaid",
                        "description": "Key symbols grouped by scope.",
                        "prompt": {
                            "system": "Summarize top symbols into a Mermaid class diagram grouped by SECTION/DIVISION where possible.",
                            "strict_text": True,
                        },
                    },
                ],
                "narratives_spec": DEFAULT_NARRATIVES_SPEC,
            }
        ],
    },
    {
        "_id": "cam.cobol.parse_report",
        "title": "COBOL Parse Report",
        "category": "cobol",
        "aliases": ["ext.parser.report", "cam.asset.parse_report"],
        "status": "active",
        "latest_schema_version": "1.0.0",
        "schema_versions": [
            {
                "version": "1.0.0",
                "json_schema": {
                    "type": "object",
                    "additionalProperties": True,
                    "required": ["parser", "source"],
                    "properties": {
                        "parser": {
                            "type": "object",
                            "additionalProperties": True,
                            "required": ["name", "version"],
                            "properties": {
                                "name": {"type": ["string", "null"]},
                                "version": {"type": ["string", "null"]},
                            },
                        },
                        "source": {
                            "type": "object",
                            "additionalProperties": True,
                            "required": ["relpath"],
                            "properties": {
                                "relpath": {"type": ["string", "null"]},
                                "sha256": {"type": ["string", "null"]},
                            },
                        },
                        "timings_ms": {
                            "type": ["object", "null"],
                            "properties": {
                                "lex": {"type": ["number", "null"]},
                                "parse": {"type": ["number", "null"]},
                                "postprocess": {"type": ["number", "null"]},
                            },
                            "additionalProperties": True,
                        },
                        "counters": {
                            "type": ["object", "null"],
                            "properties": {
                                "tokens": {"type": ["integer", "string", "null"]},
                                "nodes": {"type": ["integer", "string", "null"]},
                                "errors": {"type": ["integer", "string", "null"]},
                                "warnings": {"type": ["integer", "string", "null"]},
                            },
                            "additionalProperties": True,
                        },
                        "messages": {
                            "type": ["array", "null"],
                            "items": {
                                "type": "object",
                                "additionalProperties": True,
                                "properties": {
                                    "severity": {
                                        "type": ["string", "null"],
                                        "enum": ["error", "warning", "info", "null"],
                                    },
                                    "message": {"type": ["string", "null"]},
                                    "range": {
                                        "type": ["object", "null"],
                                        "additionalProperties": True,
                                    },
                                },
                            },
                        },
                    },
                },
                "additional_props_policy": "allow",
                "prompt": {
                    "system": "Store ProLeap parse telemetry and diagnostics tied to a COBOL file.",
                    "strict_json": True,
                },
                "depends_on": {"hard": ["cam.asset.source_index"]},
                "identity": {"natural_key": ["source.relpath", "parser.version"]},
                "examples": [
                    {
                        "parser": {"name": "proleap", "version": "1.10.0"},
                        "source": {"relpath": "batch/POSTTRAN.cbl", "sha256": "..."},
                        "timings_ms": {"parse": 215.4},
                        "counters": {"nodes": 4821, "errors": 0, "warnings": 2},
                    }
                ],
                "diagram_recipes": [
                    {
                        "id": "parse.report.flow",
                        "title": "Parse Phases",
                        "view": "flowchart",
                        "language": "mermaid",
                        "description": "Lex → Parse → Postprocess with timings.",
                        "prompt": {
                            "system": "Emit a Mermaid flowchart with phase nodes and annotated timings from `timings_ms`.",
                            "strict_text": True,
                        },
                    }
                ],
                "narratives_spec": {
                    "allowed_formats": ["markdown", "asciidoc"],
                    "default_format": "markdown",
                    "max_length_chars": 20000,
                    "allowed_locales": ["en-US"],
                },
            }
        ],
    },
]


# Seeder
# ─────────────────────────────────────────────────────────────
def seed_registry() -> None:
    now = datetime.utcnow()
    for doc in KIND_DOCS:
        doc.setdefault("aliases", [])
        doc.setdefault("policies", {})
        doc["created_at"] = doc.get("created_at", now)
        doc["updated_at"] = now
        upsert_kind(doc)


if __name__ == "__main__":
    seed_registry()
    print(f"Seeded {len(KIND_DOCS)} COBOL modernization kinds into registry.")

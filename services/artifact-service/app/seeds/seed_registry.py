# services/artifact-service/app/seeds/seed_registry.py
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
# Canonical seed docs (with diagram_recipes + narratives_spec)
# Loosened schemas across all kinds
# ─────────────────────────────────────────────────────────────
KIND_DOCS: List[Dict[str, Any]] = [
    {
        "_id": "cam.asset.repo_snapshot",
        "title": "Repository Snapshot",
        "category": "generic",
        "aliases": ["cam.asset.git_snapshot"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [{
            "version": LATEST,
            "json_schema": {
                "type": "object",
                "additionalProperties": True,
                "required": ["repo"],
                "properties": {
                    "repo": {"type": ["string", "null"], "description": "Remote URL or origin name"},
                    "commit": {"type": ["string", "null"]},
                    "branch": {"type": ["string", "null"]},
                    "paths_root": {"type": ["string", "null"], "description": "Filesystem mount/volume path used by tools"},
                    "tags": {"type": ["array", "null"], "items": {"type": "string"}}
                }
            },
            "additional_props_policy": "allow",
            "prompt": {
                "system": "Validate and normalize a Git snapshot into strict JSON. Do not invent fields.",
                "strict_json": True
            },
            "identity": {"natural_key": ["repo", "commit"]},
            "examples": [{
                "repo": "https://git.example.com/legacy/cards.git",
                "commit": "8f2c1b...",
                "branch": "main",
                "paths_root": "/workspace"
            }],
            "diagram_recipes": [
                {
                    "id": "repo.mindmap",
                    "title": "Repo Snapshot Mindmap",
                    "view": "mindmap",
                    "language": "mermaid",
                    "description": "Quick overview of repo → branch/commit and tags.",
                    "template": """mindmap
  root(({{ data.repo }}))
    Branch: {{ data.branch }}
    Commit: {{ data.commit }}
    Paths Root: {{ data.paths_root }}
    Tags
      {% for t in (data.tags or []) %}{{ t }}
      {% endfor %}"""
                }
            ],
            "narratives_spec": DEFAULT_NARRATIVES_SPEC
        }]
    },
    {
        "_id": "cam.asset.source_index",
        "title": "Source Index",
        "category": "generic",
        "aliases": ["cam.asset.repo_index"],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [{
            "version": LATEST,
            "json_schema": {
                "type": "object",
                "additionalProperties": True,
                "required": ["root", "files"],
                "properties": {
                    "root": {"type": ["string", "null"]},
                    "files": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "object",
                            "additionalProperties": True,
                            "required": ["relpath"],
                            "properties": {
                                "relpath": {"type": ["string", "null"]},
                                "size_bytes": {"type": ["integer", "string", "null"]},
                                "sha256": {"type": ["string", "null"]},
                                "kind": {
                                    "type": ["string", "null"],
                                    "enum": ["cobol", "copybook", "jcl", "ddl", "bms", "other", None]
                                },
                                "language_hint": {"type": ["string", "null"]},
                                "encoding": {"type": ["string", "null"]},
                                "program_id_guess": {"type": ["string", "null"]}
                            }
                        }
                    }
                }
            },
            "additional_props_policy": "allow",
            "prompt": {
                "system": "Given a raw file walk, emit a strict typed inventory mapping each file to a kind used by downstream parsers. Do not include files outside the root.",
                "strict_json": True
            },
            "depends_on": {
                "hard": ["cam.asset.repo_snapshot"],
                "context_hint": "Use `paths_root` from the repo snapshot to anchor relpaths."
            },
            "identity": {"natural_key": ["root"]},
            "examples": [{
                "root": "/workspace",
                "files": [
                    {"relpath": "batch/POSTTRAN.cbl", "size_bytes": 12453, "sha256": "...", "kind": "cobol"},
                    {"relpath": "batch/POSTTRAN.jcl", "size_bytes": 213, "sha256": "...", "kind": "jcl"},
                    {"relpath": "copy/CUSTREC.cpy", "size_bytes": 982, "sha256": "...", "kind": "copybook"}
                ]
            }],
            "diagram_recipes": [
                {
                    "id": "source_index.treemap",
                    "title": "Source Index Treemap",
                    "view": "flowchart",
                    "language": "mermaid",
                    "description": "Kind-bucketed file overview.",
                    "prompt": {
                        "system": "Summarize the Source Index into a Mermaid flowchart grouping files by kind. Keep labels short; do not list more than 50 nodes.",
                        "strict_text": True
                    },
                    "renderer_hints": {"direction": "LR"}
                }
            ],
            "narratives_spec": DEFAULT_NARRATIVES_SPEC
        }]
    },
    {
        "_id": "cam.cobol.program",
        "title": "COBOL Program",
        "category": "cobol",
        "aliases": [],
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [{
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
                            "sha256": {"type": ["string", "null"]}
                        }
                    },
                    "divisions": {
                        "type": ["object", "null"],
                        "additionalProperties": True,
                        "properties": {
                            "identification": {"type": ["object", "null"], "additionalProperties": True},
                            "environment": {"type": ["object", "null"], "additionalProperties": True},
                            "data": {"type": ["object", "null"], "additionalProperties": True},
                            "procedure": {"type": ["object", "null"], "additionalProperties": True}
                        }
                    },
                    "paragraphs": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "object",
                            "additionalProperties": True,
                            "required": ["name"],
                            "properties": {
                                "name": {"type": ["string", "null"]},
                                "performs": {"type": ["array", "null"], "items": {"type": "string"}},
                                "calls": {
                                    "type": ["array", "null"],
                                    "items": {
                                        "type": "object",
                                        "additionalProperties": True,
                                        "properties": {
                                            "target": {"type": ["string", "null"], "description": "PROGRAM-ID if resolvable, else literal"},
                                            "dynamic": {"type": ["boolean", "string", "null"]}
                                        }
                                    }
                                },
                                "io_ops": {
                                    "type": ["array", "null"],
                                    "items": {
                                        "type": "object",
                                        "additionalProperties": True,
                                        "properties": {
                                            "op": {"type": ["string", "null"]},
                                            "dataset_ref": {"type": ["string", "null"]},
                                            "fields": {"type": ["array", "null"], "items": {"type": "string"}}
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "copybooks_used": {"type": ["array", "null"], "items": {"type": "string"}},
                    "notes": {"type": ["array", "null"], "items": {"type": "string"}}
                }
            },
            "additional_props_policy": "allow",
            "prompt": {
                "system": "Normalize ProLeap/cb2xml output into this canonical shape. Preserve names; do not invent CALL targets.",
                "strict_json": True
            },
            "depends_on": {
                "hard": ["cam.asset.source_index"],
                "soft": ["cam.cobol.copybook"],
                "context_hint": "Map `source.relpath` to a file in Source Index. Collect copybook names used."
            },
            "identity": {"natural_key": ["program_id"]},
            "examples": [{
                "program_id": "POSTTRAN",
                "source": {"relpath": "batch/POSTTRAN.cbl", "sha256": "..."},
                "divisions": {"identification": {}, "environment": {}, "data": {}, "procedure": {}},
                "paragraphs": [{"name": "MAIN", "performs": ["VALIDATE-INPUT"], "calls": [], "io_ops": []}]
            }],
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
classDef divisions fill:#eee,stroke:#999;"""
                },
                {
                    "id": "program.sequence",
                    "title": "Paragraph CALL / PERFORM Sequence",
                    "view": "sequence",
                    "language": "mermaid",
                    "description": "Dynamic interaction across paragraphs and called programs.",
                    "prompt": {
                        "system": "Given the canonical cam.cobol.program JSON, emit Mermaid sequence diagram instructions describing PERFORM and CALL interactions. Use paragraph names and PROGRAM-ID targets. Do not fabricate nodes.",
                        "strict_text": True
                    },
                    "renderer_hints": {"wrap": True}
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
  END([END])"""
                }
            ],
            "narratives_spec": DEFAULT_NARRATIVES_SPEC
        }]
    },
    {
        "_id": "cam.cobol.copybook",
        "title": "COBOL Copybook",
        "category": "cobol",
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [{
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
                            "sha256": {"type": ["string", "null"]}
                        }
                    },
                    "items": {
                        "type": ["array", "null"],
                        "items": { "$ref": "#/$defs/CopyItem" }
                    }
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
                            "occurs": {"type": ["integer", "string", "object", "null"]},
                            "children": {
                                "type": ["array", "null"],
                                "items": { "$ref": "#/$defs/CopyItem" }
                            }
                        }
                    }
                }
            },
            "additional_props_policy": "allow",
            "prompt": {
                "system": "Normalize copybook AST into a strict tree. Do not lose levels or PIC clauses.",
                "strict_json": True
            },
            "depends_on": {"hard": ["cam.asset.source_index"]},
            "identity": {"natural_key": ["name"]},
            "examples": [{
                "name": "CUSTREC",
                "source": {"relpath": "copy/CUSTREC.cpy", "sha256": "..."},
                "items": [{
                    "level": "01",
                    "name": "CUST-REC",
                    "picture": "",
                    "children": [
                        {"level": "05", "name": "CUST-ID", "picture": "X(10)"}
                    ]
                }]
            }],
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
  {% endfor %}"""
                }
            ],
            "narratives_spec": DEFAULT_NARRATIVES_SPEC
        }]
    },
    {
        "_id": "cam.jcl.job",
        "title": "JCL Job",
        "category": "cobol",
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [{
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
                        "properties": {"relpath": {"type": ["string", "null"]}, "sha256": {"type": ["string", "null"]}}
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
                                            "direction": {"type": ["string", "null"]}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "additional_props_policy": "allow",
            "prompt": {"system": "Parse JCL into an ordered list of steps with DD statements. Keep program names as written.", "strict_json": True},
            "depends_on": {"hard": ["cam.asset.source_index"]},
            "identity": {"natural_key": ["job_name"]},
            "examples": [{
                "job_name": "POSTTRAN",
                "source": {"relpath": "batch/POSTTRAN.jcl", "sha256": "..."},
                "steps": [{
                    "step_name": "STEP1", "seq": 1, "program": "POSTTRAN",
                    "dds": [
                        {"ddname": "INFILE", "dataset": "TRAN.IN", "direction": "IN"},
                        {"ddname": "OUTFILE", "dataset": "LEDGER.OUT", "direction": "OUT"}
                    ]
                }]
            }],
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
  END([END])"""
                }
            ],
            "narratives_spec": DEFAULT_NARRATIVES_SPEC
        }]
    },
    {
        "_id": "cam.jcl.step",
        "title": "JCL Step",
        "category": "cobol",
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [{
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
                                "direction": {"type": ["string", "null"]}
                            }
                        }
                    }
                }
            },
            "additional_props_policy": "allow",
            "prompt": {"system": "Emit one strict record per JCL step to simplify graph indexing.", "strict_json": True},
            "depends_on": {"hard": ["cam.jcl.job"]},
            "identity": {"natural_key": ["job_name", "step_name"]},
            "examples": [{
                "job_name": "POSTTRAN",
                "step_name": "STEP1",
                "seq": 1,
                "program": "POSTTRAN",
                "dds": [{"ddname": "INFILE", "dataset": "TRAN.IN", "direction": "IN"}]
            }],
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
  {% endfor %}"""
                }
            ],
            "narratives_spec": DEFAULT_NARRATIVES_SPEC
        }]
    },
    {
        "_id": "cam.cics.transaction",
        "title": "CICS Transaction Map",
        "category": "cobol",
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [{
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
                                "commarea": {"type": ["string", "null"]}
                            }
                        }
                    }
                }
            },
            "additional_props_policy": "allow",
            "prompt": {"system": "Normalize CICS catalogs into a simple transaction map.", "strict_json": True},
            "depends_on": {"soft": ["cam.asset.source_index"]},
            "identity": {"natural_key": ["region"]},
            "examples": [{
                "region": "CICSPROD",
                "transactions": [{"tranid": "PAY1", "program": "PAYMENT"}, {"tranid": "BAL1", "program": "BALENQ"}]
            }],
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
  end"""
                }
            ],
            "narratives_spec": DEFAULT_NARRATIVES_SPEC
        }]
    },
    {
        "_id": "cam.data.model",
        "title": "Data Model",
        "category": "data",
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [{
            "version": LATEST,
            "json_schema": {
                "type": "object",
                "additionalProperties": True,
                "required": [],
                "properties": {
                    "logical": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "object",
                            "additionalProperties": True,
                            "required": ["name"],
                            "properties": {
                                "name": {"type": ["string", "null"]},
                                "fields": {
                                    "type": ["array", "null"],
                                    "items": {
                                        "type": "object",
                                        "additionalProperties": True,
                                        "required": ["name"],
                                        "properties": {
                                            "name": {"type": ["string", "null"]},
                                            "type": {"type": ["string", "null"]},
                                            "source_refs": {"type": ["array", "null"], "items": {"type": "string"}}
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "physical": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "object",
                            "additionalProperties": True,
                            "required": ["name"],
                            "properties": {
                                "name": {"type": ["string", "null"]},
                                "type": {"type": ["string", "null"]},
                                "columns": {
                                    "type": ["array", "null"],
                                    "items": {
                                        "type": "object",
                                        "additionalProperties": True,
                                        "required": ["name"],
                                        "properties": {
                                            "name": {"type": ["string", "null"]},
                                            "pic_or_sqltype": {"type": ["string", "null"]}
                                        }
                                    }
                                },
                                "source_refs": {"type": ["array", "null"], "items": {"type": "string"}}
                            }
                        }
                    }
                }
            },
            "additional_props_policy": "allow",
            "prompt": {
                "system": "Map copybook fields and DB2/DDL into a normalized logical/physical model. Do not invent entities; aggregate identical record layouts.",
                "strict_json": True,
                "variants": [
                    {"name": "cobol-first", "when": {"stack": "cobol"}, "system": "Prefer copybooks as truth; fold DB2 later."}
                ]
            },
            "depends_on": {
                "hard": ["cam.cobol.copybook"],
                "soft": ["cam.jcl.job", "cam.jcl.step"],
                "context_hint": "Use copybook trees to propose logical entities; attach physical refs from JCL DD datasets or DB2 DDL if present."
            },
            "identity": {"natural_key": ["logical[*].name"]},
            "examples": [{
                "logical": [{"name": "Transaction", "fields": [{"name": "AMOUNT", "type": "NUMERIC(9,2)"}]}],
                "physical": [{
                    "name": "TRAN.IN", "type": "SEQ",
                    "columns": [{"name": "AMOUNT", "pic_or_sqltype": "S9(7)V99"}]
                }]
            }],
            "diagram_recipes": [
                {
                    "id": "data.er",
                    "title": "Logical ER Diagram",
                    "view": "er",
                    "language": "mermaid",
                    "description": "Render logical entities and fields as Mermaid ER.",
                    "template": """erDiagram
  {% for e in (data.logical or []) %}
  {{ e.name }} {
    {% for f in (e.fields or []) %}{{ (f.type or "TYPE") | replace(" ", "_") }} {{ f.name }}
    {% endfor %}
  }
  {% endfor %}"""
                }
            ],
            "narratives_spec": DEFAULT_NARRATIVES_SPEC
        }]
    },
    {
        "_id": "cam.data.dictionary",
        "title": "Domain Data Dictionary",
        "category": "domain",
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [{
            "version": LATEST,
            "json_schema": {
                "type": "object",
                "additionalProperties": True,
                "required": [],
                "properties": {
                    "terms": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "object",
                            "additionalProperties": True,
                            "required": ["term"],
                            "properties": {
                                "term": {"type": ["string", "null"]},
                                "definition": {"type": ["string", "null"]},
                                "aliases": {"type": ["array", "null"], "items": {"type": "string"}},
                                "source_refs": {"type": ["array", "null"], "items": {"type": "string"}}
                            }
                        }
                    }
                }
            },
            "additional_props_policy": "allow",
            "prompt": {
                "system": "Extract a business-friendly data dictionary from copybook/table names with concise definitions. No prose outside JSON.",
                "strict_json": True
            },
            "depends_on": {"hard": ["cam.cobol.copybook"], "soft": ["cam.data.model"]},
            "identity": {"natural_key": ["terms[*].term"]},
            "examples": [{
                "terms": [{"term": "Account Balance", "definition": "Current monetary balance on an account.", "aliases": ["BAL", "ACCT-BAL"]}]
            }],
            "diagram_recipes": [
                {
                    "id": "terms.mindmap",
                    "title": "Terms Mindmap",
                    "view": "mindmap",
                    "language": "mermaid",
                    "description": "Terms with aliases as child leaves.",
                    "template": """mindmap
  root((Data Dictionary))
  {% for t in (data.terms or []) %}
  {{ t.term }}
    {% for a in (t.aliases or []) %}{{ a }}
    {% endfor %}
  {% endfor %}"""
                }
            ],
            "narratives_spec": DEFAULT_NARRATIVES_SPEC
        }]
    },
    {
        "_id": "cam.data.lineage",
        "title": "Data Lineage",
        "category": "data",
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [{
            "version": LATEST,
            "json_schema": {
                "type": "object",
                "additionalProperties": True,
                "required": [],
                "properties": {
                    "edges": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "object",
                            "additionalProperties": True,
                            "required": ["from", "to"],
                            "properties": {
                                "from": {"type": ["string", "null"], "description": "qualified source e.g., PROGRAM.PARAGRAPH.FIELD or DATASET.FIELD"},
                                "to": {"type": ["string", "null"], "description": "qualified target"},
                                "op": {"type": ["string", "null"]},
                                "evidence": {"type": ["array", "null"], "items": {"type": "string"}}
                            }
                        }
                    }
                }
            },
            "additional_props_policy": "allow",
            "prompt": {"system": "Emit lineage edges only where there is evidence (IO ops, assignments). Be conservative.", "strict_json": True},
            "depends_on": {"hard": ["cam.cobol.program", "cam.jcl.step"], "soft": ["cam.data.model"]},
            "identity": {"natural_key": ["from", "to", "op"]},
            "examples": [{
                "edges": [
                    {"from": "TRAN.IN.AMOUNT", "to": "POSTTRAN.MAIN.AMOUNT", "op": "READ"},
                    {"from": "POSTTRAN.MAIN.BALANCE", "to": "LEDGER.OUT.BALANCE", "op": "WRITE"}
                ]
            }],
            "diagram_recipes": [
                {
                    "id": "lineage.graph",
                    "title": "Lineage Graph",
                    "view": "flowchart",
                    "language": "mermaid",
                    "description": "Show lineage edges as a directed graph.",
                    "prompt": {
                        "system": "Render lineage edges as a Mermaid flowchart LR. Use succinct node ids; collapse duplicate edges; annotate edges with op (READ/WRITE/TRANSFORM).",
                        "strict_text": True
                    },
                    "renderer_hints": {"direction": "LR"}
                }
            ],
            "narratives_spec": DEFAULT_NARRATIVES_SPEC
        }]
    },
    {
        "_id": "cam.asset.service_inventory",
        "title": "Service/Asset Inventory",
        "category": "generic",
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [{
            "version": LATEST,
            "json_schema": {
                "type": "object",
                "additionalProperties": True,
                "required": [],
                "properties": {
                    "programs": {"type": ["array", "null"], "items": {"type": "string"}},
                    "jobs": {"type": ["array", "null"], "items": {"type": "string"}},
                    "datasets": {"type": ["array", "null"], "items": {"type": "string"}},
                    "transactions": {"type": ["array", "null"], "items": {"type": "string"}}
                }
            },
            "additional_props_policy": "allow",
            "prompt": {"system": "Aggregate identifiers from upstream facts into a single inventory. Do not rename.", "strict_json": True},
            "depends_on": {"hard": ["cam.cobol.program", "cam.jcl.job"], "soft": ["cam.cics.transaction"]},
            "identity": {"natural_key": ["programs", "jobs", "datasets", "transactions"]},
            "examples": [{
                "programs": ["POSTTRAN"],
                "jobs": ["POSTTRAN"],
                "datasets": ["TRAN.IN", "LEDGER.OUT"],
                "transactions": []
            }],
            "diagram_recipes": [
                {
                    "id": "inventory.mindmap",
                    "title": "Service/Asset Inventory Mindmap",
                    "view": "mindmap",
                    "language": "mermaid",
                    "description": "Top-level inventory grouped by artifact class.",
                    "template": """mindmap
  root((Inventory))
    Programs
      {% for p in (data.programs or []) %}{{ p }}
      {% endfor %}
    Jobs
      {% for j in (data.jobs or []) %}{{ j }}
      {% endfor %}
    Datasets
      {% for d in (data.datasets or []) %}{{ d }}
      {% endfor %}
    Transactions
      {% for t in (data.transactions or []) %}{{ t }}
      {% endfor %}"""
                }
            ],
            "narratives_spec": DEFAULT_NARRATIVES_SPEC
        }]
    },
    {
        "_id": "cam.asset.dependency_inventory",
        "title": "Dependency Inventory",
        "category": "generic",
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [{
            "version": LATEST,
            "json_schema": {
                "type": "object",
                "additionalProperties": True,
                "required": [],
                "properties": {
                    "call_graph": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "object",
                            "additionalProperties": True,
                            "required": ["from", "to"],
                            "properties": {"from": {"type": ["string", "null"]}, "to": {"type": ["string", "null"]}, "dynamic": {"type": ["boolean", "string", "null"]}}
                        }
                    },
                    "job_flow": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "object",
                            "additionalProperties": True,
                            "required": ["job", "step"],
                            "properties": {
                                "job": {"type": ["string", "null"]},
                                "step": {"type": ["string", "null"]},
                                "seq": {"type": ["integer", "string", "null"]},
                                "program": {"type": ["string", "null"]}
                            }
                        }
                    },
                    "dataset_deps": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "object",
                            "additionalProperties": True,
                            "required": ["producer", "dataset", "consumer"],
                            "properties": {
                                "producer": {"type": ["string", "null"]},
                                "dataset": {"type": ["string", "null"]},
                                "consumer": {"type": ["string", "null"]}
                            }
                        }
                    }
                }
            },
            "additional_props_policy": "allow",
            "prompt": {"system": "Build deterministic edges from parsed facts. Do not infer missing endpoints.", "strict_json": True},
            "depends_on": {"hard": ["cam.cobol.program", "cam.jcl.step"]},
            "identity": {"natural_key": ["call_graph", "job_flow", "dataset_deps"]},
            "examples": [{
                "call_graph": [],
                "job_flow": [{"job": "POSTTRAN", "step": "STEP1", "seq": 1, "program": "POSTTRAN"}],
                "dataset_deps": [{"producer": "STEP1", "dataset": "LEDGER.OUT", "consumer": "DOWNSTREAM"}]
            }],
            "diagram_recipes": [
                {
                    "id": "deps.callgraph",
                    "title": "Program Call Graph",
                    "view": "flowchart",
                    "language": "mermaid",
                    "description": "Static call edges across programs.",
                    "prompt": {
                        "system": "Render call_graph as Mermaid graph LR with from --> to. Merge duplicates. Mark dynamic edges with dotted style.",
                        "strict_text": True
                    },
                    "renderer_hints": {"direction": "LR"}
                },
                {
                    "id": "deps.jobflow",
                    "title": "Job Flow",
                    "view": "flowchart",
                    "language": "mermaid",
                    "description": "Sequential flow of job steps.",
                    "template": """flowchart TD
  {% for e in (data.job_flow or [])|sort(attribute='seq') %}
  {{ e.step | replace("-", "_") }}([{{ e.job }}::{{ e.step }}\\n{{ e.program }}])
  {% endfor %}
  {% for e in (data.job_flow or [])|sort(attribute='seq') %}
    {% set next = loop.index0 + 1 %}
    {% if next < ((data.job_flow or [])|length) %}
  {{ data.job_flow[loop.index0].step | replace("-", "_") }} --> {{ data.job_flow[next].step | replace("-", "_") }}
    {% endif %}
  {% endfor %}"""
                },
                {
                    "id": "deps.dataset",
                    "title": "Dataset Producers/Consumers",
                    "view": "flowchart",
                    "language": "mermaid",
                    "description": "Edges from producers to consumers via dataset nodes.",
                    "template": """flowchart LR
  {% for d in (data.dataset_deps or []) %}
  {{ d.producer | replace("-", "_") }} --> {{ d.dataset | replace(".", "_") }}([{{ d.dataset }}]) --> {{ d.consumer | replace("-", "_") }}
  {% endfor %}"""
                }
            ],
            "narratives_spec": DEFAULT_NARRATIVES_SPEC
        }]
    },
    {
        "_id": "cam.workflow.process",
        "title": "Workflow Process",
        "category": "workflow",
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [{
            "version": LATEST,
            "json_schema": {
                "type": "object",
                "additionalProperties": True,
                "required": ["name", "type"],
                "properties": {
                    "name": {"type": ["string", "null"]},
                    "type": {"type": ["string", "null"]},
                    "lanes": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "object",
                            "additionalProperties": True,
                            "required": ["id"],
                            "properties": {"id": {"type": ["string", "null"]}, "label": {"type": ["string", "null"]}}
                        }
                    },
                    "nodes": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "object",
                            "additionalProperties": True,
                            "required": ["id"],
                            "properties": {
                                "id": {"type": ["string", "null"]},
                                "kind": {"type": ["string", "null"]},
                                "label": {"type": ["string", "null"]},
                                "lane": {"type": ["string", "null"]},
                                "refs": {"type": ["array", "null"], "items": {"type": "string"}}
                            }
                        }
                    },
                    "edges": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "object",
                            "additionalProperties": True,
                            "required": ["from", "to"],
                            "properties": {
                                "from": {"type": ["string", "null"]},
                                "to": {"type": ["string", "null"]},
                                "condition": {"type": ["string", "null"]}
                            }
                        }
                    }
                }
            },
            "additional_props_policy": "allow",
            "prompt": {
                "system": "Given inventories and dependency graphs, emit a minimal process graph. Prefer deterministic stitching for batch; use naming heuristics only for labels.",
                "strict_json": True,
                "variants": [
                    {"name": "entity-centric", "when": {"mode": "entity"}, "system": "Slice graphs around fields/entities in cam.data.model and produce a business-readable flow."}
                ]
            },
            "depends_on": {"hard": ["cam.asset.dependency_inventory"], "soft": ["cam.data.model", "cam.data.lineage"]},
            "identity": {"natural_key": ["name", "type"]},
            "examples": [{
                "name": "POSTTRAN Batch",
                "type": "batch",
                "lanes": [{"id": "job", "label": "JCL Job"}],
                "nodes": [
                    {"id": "n0", "kind": "start", "label": "Start"},
                    {"id": "n1", "kind": "task", "label": "POSTTRAN"},
                    {"id": "n2", "kind": "end", "label": "End"}
                ],
                "edges": [{"from": "n0", "to": "n1"}, {"from": "n1", "to": "n2"}]
            }],
            "diagram_recipes": [
                {
                    "id": "process.activity",
                    "title": "Process Activity Flow",
                    "view": "activity",
                    "language": "mermaid",
                    "description": "Flowchart rendering of nodes and edges; lane shown as subgraph if present.",
                    "template": """flowchart TD
  {% for l in (data.lanes or []) %}
  subgraph lane_{{ l.id }}[{{ l.label }}]
  end
  {% endfor %}
  {% for n in (data.nodes or []) %}
  {{ n.id }}([{{ n.label }}])
  {% endfor %}
  {% for e in (data.edges or []) %}
  {{ e.from }} -->{% if e.condition %}|{{ e.condition }}|{% endif %} {{ e.to }}
  {% endfor %}"""
                }
            ],
            "narratives_spec": DEFAULT_NARRATIVES_SPEC
        }]
    },
    {
        "_id": "cam.diagram.activity",
        "title": "Activity Diagram",
        "category": "diagram",
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [{
            "version": LATEST,
            "json_schema": {
                "type": "object",
                "additionalProperties": True,
                "required": ["source_process", "diagram"],
                "properties": {
                    "source_process": {"type": ["string", "null"]},
                    "diagram": {"type": ["object", "null"], "additionalProperties": True}
                }
            },
            "additional_props_policy": "allow",
            "prompt": {"system": "Render the referenced workflow process as an activity diagram JSON. Preserve node and edge ids.", "strict_json": True},
            "depends_on": {"hard": ["cam.workflow.process"]},
            "identity": {"natural_key": ["source_process"]},
            "adapters": [{"type": "dsl", "dsl": {"to_plantuml": "activity_dsl_to_puml"}}],
            "examples": [{"source_process": "POSTTRAN Batch", "diagram": {"nodes": [], "edges": []}}],
            "diagram_recipes": [
                {
                    "id": "diagram.activity.puml",
                    "title": "PlantUML Activity",
                    "view": "activity",
                    "language": "plantuml",
                    "description": "Render activity JSON via adapter to PlantUML instructions.",
                    "prompt": {
                        "system": "Convert the activity diagram JSON to PlantUML instructions. Keep ids stable; use partitions for lanes if present.",
                        "strict_text": True
                    }
                }
            ],
            "narratives_spec": DEFAULT_NARRATIVES_SPEC
        }]
    },
    {
        "_id": "cam.domain.dictionary",
        "title": "Domain Dictionary",
        "category": "domain",
        "status": "active",
        "latest_schema_version": LATEST,
        "schema_versions": [{
            "version": LATEST,
            "json_schema": {
                "type": "object",
                "additionalProperties": True,
                "required": [],
                "properties": {
                    "entries": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "object",
                            "additionalProperties": True,
                            "required": ["term"],
                            "properties": {
                                "term": {"type": ["string", "null"]},
                                "kind": {"type": ["string", "null"]},
                                "definition": {"type": ["string", "null"]},
                                "aliases": {"type": ["array", "null"], "items": {"type": "string"}},
                                "mappings": {"type": ["array", "null"], "items": {"type": "string"}}
                            }
                        }
                    }
                }
            },
            "additional_props_policy": "allow",
            "prompt": {"system": "Produce consistent, de-duplicated business terms grounded in upstream copybooks and data model. Keep definitions concise and non-ambiguous.", "strict_json": True},
            "depends_on": {"hard": ["cam.data.model", "cam.data.dictionary"]},
            "identity": {"natural_key": ["entries[*].term"]},
            "examples": [{
                "entries": [{
                    "term": "Transaction",
                    "kind": "entity",
                    "definition": "A financial posting.",
                    "aliases": ["TXN"],
                    "mappings": ["copybook:CUST-REC", "table:TRAN.IN"]
                }]
            }],
            "diagram_recipes": [
                {
                    "id": "domain.terms.map",
                    "title": "Domain Terms Map",
                    "view": "mindmap",
                    "language": "mermaid",
                    "description": "Domain terms grouped by kind with aliases.",
                    "template": """mindmap
  root((Domain Dictionary))
  {% set kinds = {"entity":[], "event":[], "metric":[], "policy":[], "other":[]} %}
  {% for e in (data.entries or []) %}{% do kinds[e.kind or "other"].append(e) %}{% endfor %}
  {% for k, arr in kinds.items() %}
  {{ k | capitalize }}
    {% for e in arr %}{{ e.term }}
      {% for a in (e.aliases or []) %}{{ a }}
      {% endfor %}
    {% endfor %}
  {% endfor %}"""
                }
            ],
            "narratives_spec": DEFAULT_NARRATIVES_SPEC
        }]
    },
]

# ─────────────────────────────────────────────────────────────
# Seeder
# ─────────────────────────────────────────────────────────────
def seed_registry() -> None:
    now = datetime.utcnow()
    for doc in KIND_DOCS:
        # Ensure common top-level fields exist
        doc.setdefault("aliases", [])
        doc.setdefault("policies", {})
        doc["created_at"] = doc.get("created_at", now)
        doc["updated_at"] = now
        upsert_kind(doc)

if __name__ == "__main__":
    seed_registry()
    print(f"Seeded {len(KIND_DOCS)} kinds into registry.")
# seeds/capabilities.py
from __future__ import annotations

import logging
import inspect

from app.models import (
    GlobalCapabilityCreate,
    McpExecution,
    LlmExecution,
    ToolCallSpec,
    StdioTransport,
    HTTPTransport,
    ExecutionInput,
    ExecutionIO,
    ExecutionOutputContract,  # uses artifact_type ("cam" | "freeform"), supports extra_schema
)
from app.services import CapabilityService

log = logging.getLogger("app.seeds.capabilities")


async def _try_wipe_all(svc: CapabilityService) -> bool:
    """
    Best-effort collection wipe without relying on list_all().
    Tries common method names; returns True if any succeeded.
    """
    candidates = [
        "delete_all", "purge_all", "purge", "truncate", "clear",
        "reset", "drop_all", "wipe_all"
    ]
    for name in candidates:
        method = getattr(svc, name, None)
        if callable(method):
            try:
                result = method()
                if inspect.isawaitable(result):
                    await result
                log.info("[capability.seeds] wiped existing via CapabilityService.%s()", name)
                return True
            except Exception as e:
                log.warning("[capability.seeds] %s() failed: %s", name, e)
    return False


async def seed_capabilities() -> None:
    """
    Seeds the capability set (mix of MCP over stdio and HTTP, plus LLM).
    """
    log.info("[capability.seeds] Begin")

    svc = CapabilityService()

    # 1) Try full wipe
    wiped = await _try_wipe_all(svc)
    if not wiped:
        log.info("[capability.seeds] No wipe method found; proceeding with replace-by-id")

    LONG_TIMEOUT = 3600  # seconds

    # ─────────────────────────────────────────────────────────────
    # Existing stdio MCP servers (leave only those actually used)
    # ─────────────────────────────────────────────────────────────
    source_indexer_stdio = StdioTransport(
        kind="stdio",
        command="source-indexer-mcp",
        args=["--stdio"],
        cwd="/opt/astra/tools/source-indexer",
        env={"LOG_LEVEL": "info"},
        env_aliases={},
        restart_on_exit=True,
        readiness_regex="server started",
        kill_timeout_sec=10,
    )

    # NOTE: jcl_parser_stdio removed; cap.jcl.parse now uses HTTP MCP.

    cics_catalog_stdio = StdioTransport(
        kind="stdio",
        command="cics-catalog-mcp",
        args=["--stdio"],
        cwd="/opt/astra/tools/cics-catalog",
        env={"LOG_LEVEL": "info"},
        env_aliases={"CICS_TOKEN": "alias.cics.token"},
        restart_on_exit=True,
        readiness_regex="server started",
        kill_timeout_sec=10,
    )

    db2_catalog_stdio = StdioTransport(
        kind="stdio",
        command="db2-catalog-mcp",
        args=["--stdio"],
        cwd="/opt/astra/tools/db2-catalog",
        env={"LOG_LEVEL": "info"},
        env_aliases={
            "DB2_CONN": "alias.db2.conn",
            "DB2_USERNAME": "alias.db2.user",
            "DB2_PASSWORD": "alias.db2.pass",
        },
        restart_on_exit=True,
        readiness_regex="server started",
        kill_timeout_sec=10,
    )

    graph_indexer_stdio = StdioTransport(
        kind="stdio",
        command="graph-indexer-mcp",
        args=["--stdio"],
        cwd="/opt/astra/tools/graph-indexer",
        env={"LOG_LEVEL": "info"},
        env_aliases={},
        restart_on_exit=True,
        readiness_regex="server started",
        kill_timeout_sec=10,
    )

    lineage_engine_stdio = StdioTransport(
        kind="stdio",
        command="lineage-engine-mcp",
        args=["--stdio"],
        cwd="/opt/astra/tools/lineage-engine",
        env={"LOG_LEVEL": "info"},
        env_aliases={},
        restart_on_exit=True,
        readiness_regex="server started",
        kill_timeout_sec=10,
    )

    workflow_miner_stdio = StdioTransport(
        kind="stdio",
        command="workflow-miner-mcp",
        args=["--stdio"],
        cwd="/opt/astra/tools/workflow-miner",
        env={"LOG_LEVEL": "info"},
        env_aliases={},
        restart_on_exit=True,
        readiness_regex="server started",
        kill_timeout_sec=10,
    )

    diagram_exporter_stdio = StdioTransport(
        kind="stdio",
        command="diagram-exporter-mcp",
        args=["--stdio"],
        cwd="/opt/astra/tools/diagram-exporter",
        env={"LOG_LEVEL": "info"},
        env_aliases={},
        restart_on_exit=True,
        readiness_regex="server started",
        kill_timeout_sec=10,
    )

    # ─────────────────────────────────────────────────────────────
    # Capability targets
    # ─────────────────────────────────────────────────────────────
    targets: list[GlobalCapabilityCreate] = [
        # ---------------------------------------------------------------------
        # UPDATED: cap.repo.clone (HTTP MCP, polling)
        # ---------------------------------------------------------------------
        GlobalCapabilityCreate(
            id="cap.repo.clone",
            name="Clone Source Repository",
            description="Starts a background Git clone/snapshot job and lets callers poll for completion.",
            tags=[],
            parameters_schema=None,
            produces_kinds=["cam.asset.repo_snapshot"],
            agent=None,
            execution=McpExecution(
                mode="mcp",
                transport=HTTPTransport(
                    kind="http",
                    base_url="http://host.docker.internal:8000",
                    headers={
                        "host": "localhost:8000"
                    },
                    auth={"method": "none"},
                    timeout_sec=30,
                    verify_tls=False,
                    retry={"max_attempts": 2, "backoff_ms": 250, "jitter_ms": 50},
                    health_path="/health",
                    protocol_path="/mcp",
                ),
                io=ExecutionIO(
                    input_contract=ExecutionInput(
                        json_schema={
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["repo_url", "volume_path"],
                            "properties": {
                                "repo_url": {
                                    "type": "string",
                                    "minLength": 1,
                                    "examples": ["https://github.com/skamble7/CardDemo_minimal"],
                                },
                                "volume_path": {
                                    "type": "string",
                                    "minLength": 1,
                                    "examples": ["/workspace"],
                                },
                                "branch": {"type": "string", "examples": ["master"]},
                                "depth": {"type": "integer", "minimum": 0, "examples": [1]},
                                "auth_mode": {
                                    "type": ["string", "null"],
                                    "enum": ["https", "ssh", None],
                                    "examples": [None],
                                },
                            },
                        },
                        schema_guide=(
                            "Provide details for a git snapshot job, ideally to fetch this from the pack_input \n"
                            "- **repo_url** (required): HTTPS or SSH URL to clone.\n"
                            "- **volume_path** (required): Absolute path where the repo should be materialized (e.g., `/workspace`).\n"
                            "- **branch** (optional): Branch name to checkout. Defaults to the default branch if omitted.\n"
                            "- **depth** (optional): Integer ≥ 0 for shallow clone. `0` or omitted means full history.\n"
                            "- **auth_mode** (optional): One of `https`, `ssh`, or `null` for unauthenticated public clones."
                        ),
                    ),
                    output_contract=ExecutionOutputContract(
                        artifact_type="cam",
                        kinds=["cam.asset.repo_snapshot"],
                        extra_schema={
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "job_id": {"type": "string"},
                                "status": {"type": "string", "enum": ["queued", "running", "done", "error"]},
                                "progress": {"type": "number", "minimum": 0, "maximum": 100},
                                "message": {"type": "string"},
                            },
                        },
                        schema_guide=(
                            "The response contains **artifacts** (an array of CAM objects under `artifacts`) and an envelope.\n"
                            "- When the job is still running, expect `{ job_id, status }` with **no artifacts**.\n"
                            "- When complete, expect `{ job_id, status: \"done\", artifacts: [cam.asset.repo_snapshot, ...] }`.\n"
                            "- `progress` (0–100) and `message` are optional hints during execution."
                        ),
                    ),
                ),
                tool_calls=[
                    ToolCallSpec(
                        tool="git.repo.snapshot.start",
                        args_schema={
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["repo_url", "volume_path"],
                            "properties": {
                                "repo_url": {"type": "string"},
                                "volume_path": {"type": "string"},
                                "branch": {"type": "string"},
                                "depth": {"type": "integer", "minimum": 0},
                                "auth_mode": {"type": ["string", "null"], "enum": ["https", "ssh", None]},
                            },
                        },
                        output_kinds=[],
                        result_schema={
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["job_id", "status"],
                            "properties": {
                                "job_id": {"type": "string"},
                                "status": {"type": "string", "enum": ["queued", "running"]},
                            },
                        },
                        timeout_sec=15,
                        retries=1,
                        expects_stream=False,
                        cancellable=True,
                    ),
                    ToolCallSpec(
                        tool="git.repo.snapshot.status",
                        args_schema={
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["job_id"],
                            "properties": {"job_id": {"type": "string"}},
                        },
                        output_kinds=["cam.asset.repo_snapshot"],
                        result_schema={
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["job_id", "status"],
                            "properties": {
                                "job_id": {"type": "string"},
                                "status": {"type": "string", "enum": ["queued", "running", "done", "error"]},
                            },
                        },
                        timeout_sec=15,  # per poll
                        retries=0,
                        expects_stream=False,
                        cancellable=True,
                    ),
                ],
                discovery={"validate_tools": True, "validate_resources": False, "validate_prompts": False, "fail_fast": True},
                connection={"singleton": True, "share_across_steps": True},
            ),
        ),

        # ---------------------------------------------------------------------
        # UNCHANGED: cap.source.index (stdio)
        # ---------------------------------------------------------------------
        GlobalCapabilityCreate(
            id="cap.source.index",
            name="Index Source Files",
            description="Indexes source files and detects type/kind (COBOL, JCL, copybook, etc.).",
            produces_kinds=["cam.asset.source_file"],
            execution=McpExecution(
                mode="mcp",
                transport=source_indexer_stdio,
                tool_calls=[
                    ToolCallSpec(
                        tool="index_sources",
                        output_kinds=["cam.asset.source_file"],
                        timeout_sec=LONG_TIMEOUT,
                        retries=1,
                    )
                ],
                discovery={"validate_tools": True, "fail_fast": True},
                connection={"singleton": True, "share_across_steps": True},
            ),
        ),

        # ---------------------------------------------------------------------
        # UPDATED: cap.cobol.parse (HTTP MCP, pagination)  ✅ REVISED
        # ---------------------------------------------------------------------
        GlobalCapabilityCreate(
            id="cap.cobol.parse",
            name="Parse COBOL Programs and Copybooks",
            description="Parses COBOL repos and emits source index, normalized programs, copybooks, and ProLeap-specific AST/ASG snapshots plus parse telemetry.",
            tags=[],
            parameters_schema=None,
            produces_kinds=[
                "cam.asset.source_index",
                "cam.cobol.copybook",
                "cam.cobol.program",
                "cam.cobol.ast_proleap",
                "cam.cobol.asg_proleap",
                "cam.cobol.parse_report",
            ],
            agent=None,
            execution=McpExecution(
                mode="mcp",
                transport=HTTPTransport(
                    kind="http",
                    base_url="http://host.docker.internal:8765",
                    headers={
                        "host": "localhost:8765"
                    },
                    auth={"method": "none"},
                    timeout_sec=90,
                    verify_tls=False,
                    retry={"max_attempts": 2, "backoff_ms": 250, "jitter_ms": 50},
                    health_path="/health",
                    protocol_path="/mcp",
                ),
                io=ExecutionIO(
                    input_contract=ExecutionInput(
                        json_schema={
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["paths_root"],
                            "properties": {
                                "paths_root": {
                                    "type": "string",
                                    "minLength": 1,
                                    "examples": ["/workspace"],
                                },
                                "page_size": {"type": "integer", "minimum": 1, "examples": [60]},
                                "cursor": {"type": ["string", "null"], "examples": ["<opaque-cursor>"]},
                                "kinds": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                        "enum": [
                                            "source_index",
                                            "copybook",
                                            "program",
                                            "ast_proleap",
                                            "asg_proleap",
                                            "parse_report",
                                        ],
                                    },
                                    "examples": [[
                                        "source_index",
                                        "copybook",
                                        "program",
                                        "ast_proleap",
                                        "asg_proleap",
                                        "parse_report",
                                    ]],
                                },
                                "force_reparse": {"type": "boolean"},
                                "run_id": {"type": "string"},
                            },
                        },
                        schema_guide=(
                            "Request a COBOL parse page:\n"
                            "- **paths_root** (required): Root directory containing the checked-out repo (e.g., `/workspace`).\n"
                            "- **page_size** (optional): Number of artifacts per page (integer ≥ 1). Defaults to 3.\n"
                            "- **cursor** (optional): Opaque pagination token from a prior response; use `null` for the first page.\n"
                            "- **kinds** (optional): subset of artifacts to emit this page; choose from "
                            "`source_index`, `copybook`, `program`, `ast_proleap`, `asg_proleap`, `parse_report`.\n"
                            "- **force_reparse** (optional): Boolean to force a clean reparse ignoring caches.\n"
                            "- **run_id** (optional): Correlation id to be echoed back in responses."
                        ),
                    ),
                    output_contract=ExecutionOutputContract(
                        artifact_type="cam",
                        kinds=[
                            "cam.asset.source_index",
                            "cam.cobol.copybook",
                            "cam.cobol.program",
                            "cam.cobol.ast_proleap",
                            "cam.cobol.asg_proleap",
                            "cam.cobol.parse_report",
                        ],
                        extra_schema={
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "run": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "run_id": {"type": "string"},
                                        "paths_root": {"type": "string"},
                                    },
                                },
                                "meta": {
                                    "type": "object",
                                    "additionalProperties": True,
                                    "properties": {
                                        "counts": {
                                            "type": "object",
                                            "additionalProperties": True,
                                            "properties": {
                                                "source_index": {"type": "integer"},
                                                "copybook": {"type": "integer"},
                                                "program": {"type": "integer"},
                                                "ast_proleap": {"type": "integer"},
                                                "asg_proleap": {"type": "integer"},
                                                "parse_report": {"type": "integer"},
                                            },
                                        },
                                        "page_size": {"type": "integer", "minimum": 1},
                                    },
                                },
                                "next_cursor": {"type": ["string", "null"]},
                            },
                        },
                        schema_guide=(
                            "Each page responds with an envelope and (optionally) **artifacts**:\n"
                            "- `run`: echoes identifiers like `run_id` and `paths_root`.\n"
                            "- `meta.counts`: per-kind artifact counts for the selected kinds; `meta.page_size` is the requested size.\n"
                            "- `next_cursor`: supply this on the next call to continue paging; `null` means last page.\n"
                            "- `artifacts`: array of CAM objects "
                            "(`cam.asset.source_index`, `cam.cobol.copybook`, `cam.cobol.program`, "
                            "`cam.cobol.ast_proleap`, `cam.cobol.asg_proleap`, `cam.cobol.parse_report`). "
                            "The artifacts.data property contains the actual data as per the json_schema property of an artifact kind."
                        ),
                    ),
                ),
                tool_calls=[
                    ToolCallSpec(
                        tool="cobol.parse_repo",
                        args_schema={
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["paths_root"],
                            "properties": {
                                "paths_root": {"type": "string", "minLength": 1},
                                "page_size": {"type": "integer", "minimum": 1},
                                "cursor": {"type": ["string", "null"]},
                                "kinds": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                        "enum": [
                                            "source_index",
                                            "copybook",
                                            "program",
                                            "ast_proleap",
                                            "asg_proleap",
                                            "parse_report",
                                        ],
                                    },
                                },
                                "force_reparse": {"type": "boolean"},
                                "run_id": {"type": "string"},
                            },
                        },
                        output_kinds=[
                            "cam.asset.source_index",
                            "cam.cobol.copybook",
                            "cam.cobol.program",
                            "cam.cobol.ast_proleap",
                            "cam.cobol.asg_proleap",
                            "cam.cobol.parse_report",
                        ],
                        timeout_sec=LONG_TIMEOUT,
                        retries=1,
                        expects_stream=False,
                        cancellable=True,
                    )
                ],
                discovery={"validate_tools": True, "validate_resources": False, "validate_prompts": False, "fail_fast": True},
                connection={"singleton": True, "share_across_steps": True},
            ),
        ),

        # ---------------------------------------------------------------------
        # NEW: cap.cobol.workspace_doc (HTTP MCP, blocking tool)
        # ---------------------------------------------------------------------
        GlobalCapabilityCreate(
            id="cap.cobol.workspace_doc",
            name="Generate COBOL Workspace Document",
            description="Generates a Markdown document summarizing COBOL artifacts in a workspace and emits cam.asset.cobol_artifacts_summary with storage and (optionally pre-signed) download info.",
            tags=["cobol", "docs", "summary", "mcp"],
            parameters_schema=None,
            produces_kinds=["cam.asset.cobol_artifacts_summary"],
            agent=None,
            execution=McpExecution(
                mode="mcp",
                transport=HTTPTransport(
                    kind="http",
                    base_url="http://host.docker.internal:8002",
                    headers={},
                    auth={"method": "none"},
                    timeout_sec=180,
                    verify_tls=False,
                    retry={"max_attempts": 2, "backoff_ms": 250, "jitter_ms": 50},
                    health_path="/health",
                    protocol_path="/mcp",
                ),
                tool_calls=[
                    ToolCallSpec(
                        tool="generate.workspace.document",
                        args_schema={
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["workspace_id"],
                            "properties": {
                                "workspace_id": {
                                    "type": "string",
                                    "minLength": 1,
                                    "description": "Workspace identifier whose artifacts should be summarized.",
                                },
                                "kind_id": {
                                    "type": "string",
                                    "const": "cam.asset.cobol_artifacts_summary",
                                    "description": "Driver kind for the document generation.",
                                },
                            },
                        },
                        output_kinds=["cam.asset.cobol_artifacts_summary"],
                        result_schema=None,
                        timeout_sec=LONG_TIMEOUT,
                        retries=1,
                        expects_stream=False,
                        cancellable=True,
                    )
                ],
                discovery={"validate_tools": True, "validate_resources": False, "validate_prompts": False, "fail_fast": True},
                connection={"singleton": True, "share_across_steps": True},
                io=ExecutionIO(
                    input_contract=ExecutionInput(
                        json_schema={
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["workspace_id"],
                            "properties": {
                                "workspace_id": {
                                    "type": "string",
                                    "minLength": 1,
                                    "description": "Workspace identifier to summarize.",
                                    "examples": ["0084b4c5-b11b-44d3-8ec3-d616dfa3e873"],
                                },
                                "kind_id": {
                                    "type": "string",
                                    "const": "cam.asset.cobol_artifacts_summary",
                                    "description": "Fixed to the COBOL workspace document kind.",
                                },
                            },
                        },
                        schema_guide=(
                            "Call the MCP server to generate a single Markdown document summarizing COBOL artifacts for the given workspace.\n"
                            "- **workspace_id** (required): The workspace whose artifacts will be summarized.\n"
                            "- **kind_id** (fixed): `cam.asset.cobol_artifacts_summary`."
                        ),
                    ),
                    output_contract=ExecutionOutputContract(
                        artifact_type="cam",
                        kinds=["cam.asset.cobol_artifacts_summary"],
                        result_schema=None,
                        extra_schema={
                            "type": "object",
                            "additionalProperties": True,
                            "properties": {
                                "name": {"type": ["string", "null"]},
                                "description": {"type": ["string", "null"]},
                                "filename": {"type": ["string", "null"]},
                                "path": {"type": ["string", "null"]},
                                "storage_uri": {"type": ["string", "null"]},
                                "download_url": {"type": ["string", "null"], "format": "uri"},
                                "download_expires_at": {"type": ["string", "null"], "format": "date-time"},
                                "size_bytes": {"type": ["integer", "string", "null"]},
                                "mime_type": {"type": ["string", "null"]},
                                "encoding": {"type": ["string", "null"]},
                                "checksum": {
                                    "type": ["object", "null"],
                                    "additionalProperties": True,
                                    "properties": {
                                        "md5": {"type": ["string", "null"]},
                                        "sha1": {"type": ["string", "null"]},
                                        "sha256": {"type": ["string", "null"]},
                                    },
                                },
                                "source_system": {"type": ["string", "null"]},
                                "tags": {"type": ["array", "null"], "items": {"type": "string"}},
                                "created_at": {"type": ["string", "null"], "format": "date-time"},
                                "updated_at": {"type": ["string", "null"], "format": "date-time"},
                                "preview": {
                                    "type": ["object", "null"],
                                    "additionalProperties": True,
                                    "properties": {
                                        "thumbnail_url": {"type": ["string", "null"], "format": "uri"},
                                        "text_excerpt": {"type": ["string", "null"]},
                                        "page_count": {"type": ["integer", "string", "null"]},
                                    },
                                },
                                "metadata": {"type": ["object", "null"], "additionalProperties": True},
                            },
                        },
                        schema_guide=(
                            "The MCP server returns one artifact of kind `cam.asset.cobol_artifacts_summary` with file metadata and links:\n"
                            "- `storage_uri` (e.g., `s3://astra-docs/<key>`) and `download_url` (may be pre-signed).\n"
                            "- If pre-signed, `download_expires_at` may be present; consumers should respect it.\n"
                            "- Other fields include `filename`, `path`, `size_bytes`, `mime_type`, `encoding`, and checksums."
                        ),
                    ),
                ),
            ),
        ),

        # ---------------------------------------------------------------------
        # NEW: cap.data-eng.generate-arch-diagram (HTTP MCP, blocking tool)
        # ---------------------------------------------------------------------
        GlobalCapabilityCreate(
            id="cap.data-eng.generate-arch-diagram",
            name="Generate Data Pipeline Architecture Guidance Document",
            description="Calls the MCP server to produce a Markdown architecture guidance document grounded on discovered data-engineering artifacts and RUN INPUTS; emits cam.documents.data-pipeline-arch-guidance with standard file metadata (and optional pre-signed download info).",
            tags=["data-eng", "docs", "guidance", "mcp"],
            parameters_schema=None,
            produces_kinds=["cam.documents.data-pipeline-arch-guidance"],
            agent=None,
            execution=McpExecution(
                mode="mcp",
                transport=HTTPTransport(
                    kind="http",
                    base_url="http://host.docker.internal:8002",
                    headers={},
                    auth={"method": "none"},
                    timeout_sec=180,
                    verify_tls=False,
                    retry={"max_attempts": 2, "backoff_ms": 250, "jitter_ms": 50},
                    health_path="/health",
                    protocol_path="/mcp",
                ),
                tool_calls=[
                    ToolCallSpec(
                        tool="generate.workspace.document",
                        args_schema={
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["workspace_id"],
                            "properties": {
                                "workspace_id": {
                                    "type": "string",
                                    "minLength": 1,
                                    "description": "Workspace identifier whose discovered artifacts ground the guidance document.",
                                },
                                "kind_id": {
                                    "type": "string",
                                    "const": "cam.documents.data-pipeline-arch-guidance",
                                    "description": "Driver kind for the document generation.",
                                },
                            },
                        },
                        output_kinds=["cam.documents.data-pipeline-arch-guidance"],
                        result_schema=None,
                        timeout_sec=LONG_TIMEOUT,
                        retries=1,
                        expects_stream=False,
                        cancellable=True,
                    )
                ],
                discovery={"validate_tools": True, "validate_resources": False, "validate_prompts": False, "fail_fast": True},
                connection={"singleton": True, "share_across_steps": True},
                io=ExecutionIO(
                    input_contract=ExecutionInput(
                        json_schema={
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["workspace_id"],
                            "properties": {
                                "workspace_id": {
                                    "type": "string",
                                    "minLength": 1,
                                    "description": "Workspace identifier whose artifacts will be used to ground the architecture guidance document.",
                                    "examples": ["0084b4c5-b11b-44d3-8ec3-d616dfa3e873"],
                                },
                                "kind_id": {
                                    "type": "string",
                                    "const": "cam.documents.data-pipeline-arch-guidance",
                                    "description": "Fixed to the architecture guidance document kind.",
                                },
                            },
                        },
                        schema_guide=(
                            "Call the MCP server to generate a single Markdown architecture guidance document grounded on the workspace's discovered artifacts and RUN INPUTS.\n"
                            "- **workspace_id** (required): The workspace to analyze.\n"
                            "- **kind_id** (fixed): `cam.documents.data-pipeline-arch-guidance`."
                        ),
                    ),
                    output_contract=ExecutionOutputContract(
                        artifact_type="cam",
                        kinds=["cam.documents.data-pipeline-arch-guidance"],
                        result_schema=None,
                        extra_schema={
                            "type": "object",
                            "additionalProperties": True,
                            "properties": {
                                "name": {"type": ["string", "null"]},
                                "description": {"type": ["string", "null"]},
                                "filename": {"type": ["string", "null"]},
                                "path": {"type": ["string", "null"]},
                                "storage_uri": {"type": ["string", "null"]},
                                "download_url": {"type": ["string", "null"], "format": "uri"},
                                "download_expires_at": {"type": ["string", "null"], "format": "date-time"},
                                "size_bytes": {"type": ["integer", "string", "null"]},
                                "mime_type": {"type": ["string", "null"]},
                                "encoding": {"type": ["string", "null"]},
                                "checksum": {
                                    "type": ["object", "null"],
                                    "additionalProperties": True,
                                    "properties": {
                                        "md5": {"type": ["string", "null"]},
                                        "sha1": {"type": ["string", "null"]},
                                        "sha256": {"type": ["string", "null"]},
                                    },
                                },
                                "source_system": {"type": ["string", "null"]},
                                "tags": {"type": ["array", "null"], "items": {"type": "string"}},
                                "created_at": {"type": ["string", "null"], "format": "date-time"},
                                "updated_at": {"type": ["string", "null"], "format": "date-time"},
                                "preview": {
                                    "type": ["object", "null"],
                                    "additionalProperties": True,
                                    "properties": {
                                        "thumbnail_url": {"type": ["string", "null"], "format": "uri"},
                                        "text_excerpt": {"type": ["string", "null"]},
                                        "page_count": {"type": ["integer", "string", "null"]},
                                    },
                                },
                                "metadata": {"type": ["object", "null"], "additionalProperties": True},
                            },
                        },
                        schema_guide=(
                            "The MCP server returns one artifact of kind `cam.documents.data-pipeline-arch-guidance` with file metadata and links:\n"
                            "- `storage_uri` (e.g., `s3://astra-docs/<key>`) and `download_url` (may be pre-signed).\n"
                            "- If pre-signed, `download_expires_at` may be present; consumers should respect it.\n"
                            "- Other fields include `filename`, `path`, `size_bytes`, `mime_type`, `encoding`, and checksums."
                        ),
                    ),
                ),
            ),
        ),

        # ---------------------------------------------------------------------
        # NEW: cap.mermaid.generate (HTTP MCP, freeform output contract)
        # ---------------------------------------------------------------------
        GlobalCapabilityCreate(
            id="cap.diagram.mermaid",
            name="Generate Mermaid Diagrams from Artifact JSON",
            description="Given an artifact JSON payload and requested diagram views, returns validated Mermaid instructions (LLM-only).",
            tags=[],
            parameters_schema=None,
            produces_kinds=[],
            agent=None,
            execution=McpExecution(
                mode="mcp",
                transport=HTTPTransport(
                    kind="http",
                    base_url="http://host.docker.internal:8001",
                    headers={
                        "host": "localhost:8001"
                    },
                    auth={"method": "none"},
                    timeout_sec=120,
                    verify_tls=False,
                    retry={"max_attempts": 2, "backoff_ms": 250, "jitter_ms": 50},
                    # health_path kept default ("/health")
                    protocol_path="/mcp",
                ),
                tool_calls=[
                    ToolCallSpec(
                        tool="diagram.mermaid.generate",
                        args_schema={
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["artifact"],
                            "properties": {
                                "artifact": {
                                    "type": "object",
                                    "description": "The JSON payload to visualize (any shape).",
                                },
                                "views": {
                                    "type": "array",
                                    "description": 'Diagram views to generate (defaults to ["flowchart"]).',
                                    "items": {
                                        "type": "string",
                                        "enum": [
                                            "sequence",
                                            "flowchart",
                                            "class",
                                            "component",
                                            "deployment",
                                            "state",
                                            "activity",
                                            "mindmap",
                                            "er",
                                            "gantt",
                                            "timeline",
                                            "journey",
                                        ],
                                    },
                                },
                                "prompt": {
                                    "type": "string",
                                    "description": "Optional extra guidance for the LLM (appended to the first user prompt).",
                                },
                            },
                        },
                        output_kinds=[],
                        result_schema=None,
                        timeout_sec=600,
                        retries=1,
                        expects_stream=False,
                        cancellable=True,
                    )
                ],
                discovery={
                    "validate_tools": True,
                    "validate_resources": False,
                    "validate_prompts": False,
                    "fail_fast": True,
                },
                connection={"singleton": True, "share_across_steps": True},
                io=ExecutionIO(
                    input_contract=ExecutionInput(
                        json_schema={
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["artifact"],
                            "properties": {
                                "artifact": {
                                    "type": "object",
                                    "description": "The JSON payload to visualize (e.g., a parsed program structure).",
                                    "examples": [
                                        {
                                            "program_id": "USRLST01",
                                            "paragraphs": [
                                                {
                                                    "name": "MAIN-PARA",
                                                    "performs": [
                                                        "SEND-USRLST-SCREEN",
                                                        "PROCESS-ENTER-KEY",
                                                    ],
                                                }
                                            ],
                                        }
                                    ],
                                },
                                "views": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                        "enum": [
                                            "sequence",
                                            "flowchart",
                                            "class",
                                            "component",
                                            "deployment",
                                            "state",
                                            "activity",
                                            "mindmap",
                                            "er",
                                            "gantt",
                                            "timeline",
                                            "journey",
                                        ],
                                    },
                                    "description": "Which diagrams to produce.",
                                    "examples": [["flowchart", "sequence", "mindmap"]],
                                },
                                "prompt": {
                                    "type": "string",
                                    "description": "Optional extra guidance for the LLM.",
                                    "examples": ["Use concise node labels and avoid empty nodes."],
                                },
                            },
                        },
                        schema_guide=(
                            'Request Mermaid diagrams from an artifact JSON.\n'
                            '- **artifact** (required): Your JSON payload to visualize (any shape).\n'
                            '- **views** (optional): List of diagram views to generate. Defaults to ["flowchart"]. '
                            "Allowed: sequence, flowchart, class, component, deployment, state, activity, mindmap, er, gantt, timeline, journey.\n"
                            "- **prompt** (optional): Extra guidance appended to the first LLM user prompt."
                        ),
                    ),
                    output_contract=ExecutionOutputContract(
                        artifact_type="freeform",
                        kinds=[],  # must be empty for freeform
                        result_schema={
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["diagrams"],
                            "properties": {
                                "diagrams": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "required": ["view", "language", "instructions"],
                                        "properties": {
                                            "view": {
                                                "type": "string",
                                                "enum": [
                                                    "sequence",
                                                    "flowchart",
                                                    "class",
                                                    "component",
                                                    "deployment",
                                                    "state",
                                                    "activity",
                                                    "mindmap",
                                                    "er",
                                                    "gantt",
                                                    "timeline",
                                                    "journey",
                                                ],
                                            },
                                            "language": {"type": "string", "const": "mermaid"},
                                            "instructions": {"type": "string", "minLength": 1},
                                            "renderer_hints": {
                                                "type": "object",
                                                "description": 'Optional rendering hints (e.g., {"wrap": true}).',
                                                "additionalProperties": True,
                                            },
                                        },
                                    },
                                },
                                "error": {
                                    "type": ["string", "null"],
                                    "description": "Present when the server could not generate diagrams.",
                                },
                            },
                        },
                        schema_guide=(
                            'Response contains an array of diagrams. Each diagram includes:\n'
                            '- **view**: One of the requested views.\n'
                            '- **language**: Always "mermaid".\n'
                            '- **instructions**: The Mermaid source starting with the correct directive '
                            '(e.g., `flowchart TD`, `sequenceDiagram`, `mindmap`). The server normalizes and validates output '
                            "before returning.\nIf generation fails, **error** is populated and **diagrams** may be empty."
                        ),
                    ),
                ),
            ),
        ),

        # ---------------------------------------------------------------------
        # UPDATED (DETERMINISTIC MCP over HTTP): cap.jcl.parse
        # ---------------------------------------------------------------------
        GlobalCapabilityCreate(
            id="cap.jcl.parse",
            name="Parse JCL Jobs and Steps",
            description="Parses JCL repositories and emits normalized job and step artifacts with DD datasets and derived directions.",
            produces_kinds=["cam.jcl.job", "cam.jcl.step"],
            execution=McpExecution(
                mode="mcp",
                transport=HTTPTransport(
                    kind="http",
                    base_url="http://host.docker.internal:8876",
                    headers={},
                    auth={"method": "none"},
                    timeout_sec=90,
                    verify_tls=False,
                    retry={"max_attempts": 2, "backoff_ms": 250, "jitter_ms": 50},
                    health_path="/health",
                    protocol_path="/mcp",
                ),
                tool_calls=[
                    ToolCallSpec(
                        tool="parse_jcl",
                        args_schema={
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["paths_root"],
                            "properties": {
                                "paths_root": {"type": "string", "minLength": 1},
                                "page_size": {"type": "integer", "minimum": 1},
                                "cursor": {"type": ["string", "null"]},
                                "kinds": {
                                    "type": "array",
                                    "items": {"type": "string", "enum": ["job", "step"]},
                                },
                                "force_reparse": {"type": "boolean"},
                                "run_id": {"type": "string"},
                            },
                        },
                        output_kinds=["cam.jcl.job", "cam.jcl.step"],
                        result_schema=None,
                        timeout_sec=LONG_TIMEOUT,
                        retries=1,
                        expects_stream=False,
                        cancellable=True,
                    )
                ],
                discovery={"validate_tools": True, "validate_resources": False, "validate_prompts": False, "fail_fast": True},
                connection={"singleton": True, "share_across_steps": True},
                io=ExecutionIO(
                    input_contract=ExecutionInput(
                        json_schema={
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["paths_root"],
                            "properties": {
                                "paths_root": {
                                    "type": "string",
                                    "minLength": 1,
                                    "examples": ["/workspace"],
                                },
                                "page_size": {"type": "integer", "minimum": 1, "examples": [60]},
                                "cursor": {"type": ["string", "null"], "examples": ["<opaque-cursor>"]},
                                "kinds": {
                                    "type": "array",
                                    "items": {"type": "string", "enum": ["job", "step"]},
                                    "examples": [["job", "step"]],
                                },
                                "force_reparse": {"type": "boolean"},
                                "run_id": {"type": "string"},
                            },
                        },
                        schema_guide=(
                            "Request a JCL parse page:\n"
                            "- **paths_root** (required): Root directory containing the checked-out repo (e.g., `/workspace`).\n"
                            "- **page_size** (optional): Artifacts per page (integer ≥ 1). Defaults to server setting.\n"
                            "- **cursor** (optional): Opaque pagination token from a prior response; use `null` for the first page.\n"
                            "- **kinds** (optional): Which artifact types to emit this page: `job`, `step`.\n"
                            "- **force_reparse** (optional): Force a clean parse ignoring caches.\n"
                            "- **run_id** (optional): Correlation id to be echoed back in responses."
                        ),
                    ),
                    output_contract=ExecutionOutputContract(
                        artifact_type="cam",
                        kinds=["cam.jcl.job", "cam.jcl.step"],
                        result_schema=None,
                        extra_schema={
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "run": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "run_id": {"type": "string"},
                                        "paths_root": {"type": "string"},
                                    },
                                },
                                "meta": {
                                    "type": "object",
                                    "additionalProperties": True,
                                    "properties": {
                                        "counts": {
                                            "type": "object",
                                            "additionalProperties": True,
                                            "properties": {
                                                "job": {"type": "integer"},
                                                "step": {"type": "integer"},
                                            },
                                        },
                                        "page_size": {"type": "integer", "minimum": 1},
                                    },
                                },
                                "next_cursor": {"type": ["string", "null"]},
                            },
                        },
                        schema_guide=(
                            "Each page responds with an envelope and (optionally) **artifacts**:\n"
                            "- `run`: echoes identifiers like `run_id` and `paths_root`.\n"
                            "- `meta.counts`: per-kind artifact counts for this page; `meta.page_size` is the requested size.\n"
                            "- `next_cursor`: supply this on the next call to continue paging; `null` means last page.\n"
                            "- `artifacts`: array of CAM objects (`cam.jcl.job` or `cam.jcl.step`). Each artifact's `data` "
                            "conforms to its artifact kind's `json_schema`."
                        ),
                    ),
                ),
            ),
        ),

        # ---------------------------------------------------------------------
        # UNCHANGED deterministic MCP + LLM capabilities
        # ---------------------------------------------------------------------
        GlobalCapabilityCreate(
            id="cap.cics.catalog",
            name="Discover CICS Transactions",
            description="Discovers CICS transactions and maps them to COBOL programs.",
            produces_kinds=["cam.cics.transaction"],
            execution=McpExecution(
                mode="mcp",
                transport=cics_catalog_stdio,
                tool_calls=[
                    ToolCallSpec(
                        tool="list_transactions",
                        output_kinds=["cam.cics.transaction"],
                        timeout_sec=LONG_TIMEOUT,
                        retries=1,
                    )
                ],
                discovery={"validate_tools": True, "fail_fast": True},
                connection={"singleton": True, "share_across_steps": True},
            ),
        ),
        GlobalCapabilityCreate(
            id="cap.db2.catalog",
            name="Export DB2 Catalog",
            description="Exports DB2 schemas and tables either via connection or DDL scan.",
            produces_kinds=["cam.data.model"],
            execution=McpExecution(
                mode="mcp",
                transport=db2_catalog_stdio,
                tool_calls=[
                    ToolCallSpec(
                        tool="export_schema",
                        output_kinds=["cam.data.model"],
                        timeout_sec=LONG_TIMEOUT,
                        retries=1,
                    )
                ],
                discovery={"validate_tools": True, "fail_fast": True},
                connection={"singleton": True, "share_across_steps": True},
            ),
        ),
        GlobalCapabilityCreate(
            id="cap.graph.index",
            name="Index Enterprise Graph",
            description="Builds inventories and dependency graphs from parsed COBOL, JCL, and DB2 facts.",
            produces_kinds=["cam.asset.service_inventory", "cam.asset.dependency_inventory"],
            execution=McpExecution(
                mode="mcp",
                transport=graph_indexer_stdio,
                tool_calls=[
                    ToolCallSpec(
                        tool="index",
                        output_kinds=["cam.asset.service_inventory", "cam.asset.dependency_inventory"],
                        timeout_sec=LONG_TIMEOUT,
                        retries=1,
                    )
                ],
                discovery={"validate_tools": True, "fail_fast": True},
                connection={"singleton": True, "share_across_steps": True},
            ),
        ),

        # ---------------------------------------------------------------------
        # UPDATED (LLM): cap.entity.detect — OpenAI with api_key auth alias
        # ---------------------------------------------------------------------
        GlobalCapabilityCreate(
            id="cap.entity.detect",
            name="Detect Entities and Business Terms",
            description="Lifts copybooks and DB2 schemas into logical entities and extracts a domain dictionary.",
            produces_kinds=["cam.data.model", "cam.domain.dictionary"],
            execution=LlmExecution(
                mode="llm",
                llm_config={
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "parameters": {"temperature": 0, "max_tokens": 2000},
                    # IMPORTANT: Using api_key (not bearer) per instruction.
                    "auth": {"method": "api_key", "alias_key": "OPENAI_API_KEY"},
                },
                # (Optional) If you later want strict I/O, add io=ExecutionIO(...).
            ),
        ),

        GlobalCapabilityCreate(
            id="cap.lineage.derive",
            name="Derive Data Lineage",
            description="Derives data lineage across programs, jobs, and entities.",
            produces_kinds=["cam.data.lineage"],
            execution=McpExecution(
                mode="mcp",
                transport=lineage_engine_stdio,
                tool_calls=[
                    ToolCallSpec(
                        tool="derive_lineage",
                        output_kinds=["cam.data.lineage"],
                        timeout_sec=LONG_TIMEOUT,
                        retries=1,
                    )
                ],
                discovery={"validate_tools": True, "fail_fast": True},
                connection={"singleton": True, "share_across_steps": True},
            ),
        ),

        # ---------------------------------------------------------------------
        # UPDATED (LLM): cap.workflow.mine_entity — OpenAI with api_key auth alias
        # ---------------------------------------------------------------------
        GlobalCapabilityCreate(
            id="cap.workflow.mine_entity",
            name="Mine Entity Workflows",
            description="Discovers entity-centric workflows such as Account or Customer lifecycle.",
            produces_kinds=["cam.workflow.process"],
            execution=LlmExecution(
                mode="llm",
                llm_config={
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "parameters": {"temperature": 0, "max_tokens": 2000},
                    # IMPORTANT: Using api_key (not bearer) per instruction.
                    "auth": {"method": "api_key", "alias_key": "OPENAI_API_KEY"},
                },
            ),
        ),

        GlobalCapabilityCreate(
            id="cap.diagram.render",
            name="Render Diagrams",
            description="Renders activity, sequence, component, deployment, and state diagrams from workflow and inventories.",
            produces_kinds=[
                "cam.diagram.activity",
                "cam.diagram.sequence",
                "cam.diagram.component",
                "cam.diagram.deployment",
                "cam.diagram.state",
            ],
            execution=McpExecution(
                mode="mcp",
                transport=diagram_exporter_stdio,
                tool_calls=[
                    ToolCallSpec(
                        tool="render_diagrams",
                        output_kinds=[
                            "cam.diagram.activity",
                            "cam.diagram.sequence",
                            "cam.diagram.component",
                            "cam.diagram.deployment",
                            "cam.diagram.state",
                        ],
                        timeout_sec=LONG_TIMEOUT,
                        retries=1,
                    )
                ],
                discovery={"validate_tools": True, "fail_fast": True},
                connection={"singleton": True, "share_across_steps": True},
            ),
        ),
    ]

    # 2) Replace-by-id creation
    created = 0
    for cap in targets:
        try:
            existing = await svc.get(cap.id)
            if existing:
                try:
                    await svc.delete(cap.id, actor="seed")
                    log.info("[capability.seeds] replaced: %s (deleted old)", cap.id)
                except AttributeError:
                    log.warning("[capability.seeds] delete() not available; attempting create() which may fail on unique ID")
        except Exception:
            # get() not found -> OK
            pass

        await svc.create(cap, actor="seed")
        log.info("[capability.seeds] created: %s", cap.id)
        created += 1

    log.info("[capability.seeds] Done (created=%d)", created)
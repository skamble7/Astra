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
    ExecutionInput,          # ← added
    ExecutionIO,
    ExecutionOutputContract,
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
    # Existing stdio MCP servers
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

    jcl_parser_stdio = StdioTransport(
        kind="stdio",
        command="jcl-parser-mcp",
        args=["--stdio"],
        cwd="/opt/astra/tools/jcl-parser",
        env={"LOG_LEVEL": "info"},
        env_aliases={},
        restart_on_exit=True,
        readiness_regex="server started",
        kill_timeout_sec=10,
    )

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
        #   Start tool -> returns { job_id, status }
        #   Status tool -> returns { job_id, status, artifacts: [cam.asset.repo_snapshot] }
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
                    headers={},
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
                            "- **depth** (optional): Integer >= 0 for shallow clone. `0` or omitted means full history.\n"
                            "- **auth_mode** (optional): One of `https`, `ssh`, or `null` for unauthenticated public clones."
                        ),
                    ),
                    output_contract=ExecutionOutputContract(
                        artifacts_property="artifacts",
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
                        allow_extra_output_fields=False,
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
        # UPDATED: cap.cobol.parse (HTTP MCP, pagination)
        # ---------------------------------------------------------------------
        GlobalCapabilityCreate(
            id="cap.cobol.parse",
            name="Parse COBOL Programs and Copybooks",
            description="Parses COBOL repos and emits source index, normalized programs, and copybooks.",
            tags=[],
            parameters_schema=None,
            produces_kinds=[
                "cam.asset.source_index",
                "cam.cobol.copybook",
                "cam.cobol.program",
            ],
            agent=None,
            execution=McpExecution(
                mode="mcp",
                transport=HTTPTransport(
                    kind="http",
                    base_url="http://host.docker.internal:8765",
                    headers={},
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
                                        "enum": ["source_index", "copybook", "program"],
                                    },
                                    "examples": [["source_index", "copybook", "program"]],
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
                            "- **kinds** (optional): list of artifact kinds that the mcp server needs to produce. Should be taken from the capability's produces_kinds.\n"
                            "- **force_reparse** (optional): Boolean to force a clean reparse ignoring caches.\n"
                            "- **run_id** (optional): Correlation id to be echoed back in responses."
                        ),
                    ),
                    output_contract=ExecutionOutputContract(
                        artifacts_property="artifacts",
                        kinds=[
                            "cam.asset.source_index",
                            "cam.cobol.copybook",
                            "cam.cobol.program",
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
                                            },
                                        },
                                        "page_size": {"type": "integer", "minimum": 1},
                                    },
                                },
                                "next_cursor": {"type": ["string", "null"]},
                            },
                        },
                        allow_extra_output_fields=False,
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
                                    "items": {"type": "string", "enum": ["source_index", "copybook", "program"]},
                                },
                                "force_reparse": {"type": "boolean"},
                                "run_id": {"type": "string"},
                            },
                        },
                        output_kinds=[
                            "cam.asset.source_index",
                            "cam.cobol.copybook",
                            "cam.cobol.program",
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
        # UNCHANGED: remaining deterministic MCP + LLM capabilities
        # ---------------------------------------------------------------------
        GlobalCapabilityCreate(
            id="cap.jcl.parse",
            name="Parse JCL Jobs and Steps",
            description="Parses JCL jobs and steps including datasets and program calls.",
            produces_kinds=["cam.jcl.job", "cam.jcl.step"],
            execution=McpExecution(
                mode="mcp",
                transport=jcl_parser_stdio,
                tool_calls=[
                    ToolCallSpec(
                        tool="parse_jcl",
                        output_kinds=["cam.jcl.job", "cam.jcl.step"],
                        timeout_sec=LONG_TIMEOUT,
                        retries=1,
                    )
                ],
                discovery={"validate_tools": True, "fail_fast": True},
                connection={"singleton": True, "share_across_steps": True},
            ),
        ),
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
        GlobalCapabilityCreate(
            id="cap.entity.detect",
            name="Detect Entities and Business Terms",
            description="Lifts copybooks and DB2 schemas into logical entities and extracts a domain dictionary.",
            produces_kinds=["cam.data.model", "cam.domain.dictionary"],
            execution=LlmExecution(
                mode="llm",
                llm_config={
                    "provider": "openai",
                    "model": "gpt-4.1",
                    "parameters": {"temperature": 0, "max_tokens": 2000},
                    "output_contracts": ["cam.data.model", "cam.domain.dictionary"],
                },
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
        GlobalCapabilityCreate(
            id="cap.workflow.mine_batch",
            name="Mine Batch Workflows",
            description="Mines batch workflows from JCL job flows and COBOL call graphs.",
            produces_kinds=["cam.workflow.process"],
            execution=McpExecution(
                mode="mcp",
                transport=workflow_miner_stdio,
                tool_calls=[
                    ToolCallSpec(
                        tool="mine_batch",
                        output_kinds=["cam.workflow.process"],
                        timeout_sec=LONG_TIMEOUT,
                        retries=1,
                    )
                ],
                discovery={"validate_tools": True, "fail_fast": True},
                connection={"singleton": True, "share_across_steps": True},
            ),
        ),
        GlobalCapabilityCreate(
            id="cap.workflow.mine_entity",
            name="Mine Entity Workflows",
            description="Discovers entity-centric workflows such as Account or Customer lifecycle.",
            produces_kinds=["cam.workflow.process"],
            execution=LlmExecution(
                mode="llm",
                llm_config={
                    "provider": "openai",
                    "model": "gpt-4.1",
                    "parameters": {"temperature": 0, "max_tokens": 2000},
                    "output_contracts": ["cam.workflow.process"],
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
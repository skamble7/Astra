# seeds/capabilities.py
from __future__ import annotations

import logging
import inspect

from app.models import (
    GlobalCapabilityCreate,
    McpExecution,
    LlmExecution,
    StdioTransport,
    HTTPTransport,
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
    # Stdio transports
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
        # cap.repo.clone — async polling; status tool discovered via tools/list
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
                    headers={"host": "localhost:8000"},
                    timeout_sec=30,
                    verify_tls=False,
                    protocol_path="/mcp",
                ),
                tool_name="git.repo.snapshot.start",
            ),
        ),

        # cap.source.index — stdio
        GlobalCapabilityCreate(
            id="cap.source.index",
            name="Index Source Files",
            description="Indexes source files and detects type/kind (COBOL, JCL, copybook, etc.).",
            produces_kinds=["cam.asset.source_file"],
            execution=McpExecution(
                mode="mcp",
                transport=source_indexer_stdio,
                tool_name="index_sources",
            ),
        ),

        # cap.cobol.parse — HTTP MCP, pagination
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
                    headers={"host": "localhost:8765"},
                    timeout_sec=90,
                    verify_tls=False,
                    protocol_path="/mcp",
                ),
                tool_name="cobol.parse_repo",
            ),
        ),

        # cap.cobol.workspace_doc — HTTP MCP, blocking
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
                    timeout_sec=LONG_TIMEOUT,
                    verify_tls=False,
                    protocol_path="/mcp",
                ),
                tool_name="generate.workspace.document",
            ),
        ),

        # cap.diagram.generate_arch — HTTP MCP, blocking
        GlobalCapabilityCreate(
            id="cap.diagram.generate_arch",
            name="Generate Data Pipeline Architecture Guidance Document",
            description="Calls the MCP server to produce a Markdown architecture guidance document grounded on discovered data-engineering artifacts and RUN INPUTS; emits cam.governance.data_pipeline_arch_guidance with standard file metadata (and optional pre-signed download info).",
            tags=["data", "diagram", "docs", "guidance", "mcp"],
            parameters_schema=None,
            produces_kinds=["cam.governance.data_pipeline_arch_guidance"],
            agent=None,
            execution=McpExecution(
                mode="mcp",
                transport=HTTPTransport(
                    kind="http",
                    base_url="http://host.docker.internal:8004",
                    timeout_sec=LONG_TIMEOUT,
                    verify_tls=False,
                    protocol_path="/mcp",
                ),
                tool_name="generate_data_pipeline_arch_guidance",
            ),
        ),

        # cap.diagram.mermaid — HTTP MCP, freeform output
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
                    headers={"host": "localhost:8001"},
                    timeout_sec=120,
                    verify_tls=False,
                    protocol_path="/mcp",
                ),
                tool_name="diagram.mermaid.generate",
            ),
        ),

        # cap.jcl.parse — HTTP MCP, pagination
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
                    timeout_sec=90,
                    verify_tls=False,
                    protocol_path="/mcp",
                ),
                tool_name="parse_jcl",
            ),
        ),

        # cap.cics.catalog — stdio
        GlobalCapabilityCreate(
            id="cap.cics.catalog",
            name="Discover CICS Transactions",
            description="Discovers CICS transactions and maps them to COBOL programs.",
            produces_kinds=["cam.cics.transaction"],
            execution=McpExecution(
                mode="mcp",
                transport=cics_catalog_stdio,
                tool_name="list_transactions",
            ),
        ),

        # cap.db2.catalog — stdio
        GlobalCapabilityCreate(
            id="cap.db2.catalog",
            name="Export DB2 Catalog",
            description="Exports DB2 schemas and tables either via connection or DDL scan.",
            produces_kinds=["cam.data.model"],
            execution=McpExecution(
                mode="mcp",
                transport=db2_catalog_stdio,
                tool_name="export_schema",
            ),
        ),

        # cap.graph.index — stdio
        GlobalCapabilityCreate(
            id="cap.graph.index",
            name="Index Enterprise Graph",
            description="Builds inventories and dependency graphs from parsed COBOL, JCL, and DB2 facts.",
            produces_kinds=["cam.asset.service_inventory", "cam.asset.dependency_inventory"],
            execution=McpExecution(
                mode="mcp",
                transport=graph_indexer_stdio,
                tool_name="index",
            ),
        ),

        # cap.entity.detect — LLM
        GlobalCapabilityCreate(
            id="cap.entity.detect",
            name="Detect Entities and Business Terms",
            description="Lifts copybooks and DB2 schemas into logical entities and extracts a domain dictionary.",
            produces_kinds=["cam.data.model", "cam.domain.dictionary"],
            execution=LlmExecution(
                mode="llm",
                llm_config_ref="dev.llm.openai.fast",
            ),
        ),

        # cap.lineage.derive — stdio
        GlobalCapabilityCreate(
            id="cap.lineage.derive",
            name="Derive Data Lineage",
            description="Derives data lineage across programs, jobs, and entities.",
            produces_kinds=["cam.data.lineage"],
            execution=McpExecution(
                mode="mcp",
                transport=lineage_engine_stdio,
                tool_name="derive_lineage",
            ),
        ),

        # cap.workflow.mine_entity — LLM
        GlobalCapabilityCreate(
            id="cap.workflow.mine_entity",
            name="Mine Entity Workflows",
            description="Discovers entity-centric workflows such as Account or Customer lifecycle.",
            produces_kinds=["cam.workflow.process"],
            execution=LlmExecution(
                mode="llm",
                llm_config_ref="dev.llm.openai.fast",
            ),
        ),

        # cap.diagram.render — stdio
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
                tool_name="render_diagrams",
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

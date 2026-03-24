# Slim MCP Capability Declaration Refactor

## Goal

Strip the capability declaration down to the minimum that ASTRA controls. Previously, MCP capabilities duplicated the tool's input/output schema inline in the database document. Since the MCP server already exposes its schema live via `tools/list`, the stored copy was always at risk of drifting. This refactor makes the conductor and planner discover the schema live at runtime and removes the stored copy entirely.

---

## New `McpExecution` Shape

```python
class McpExecution(BaseModel):
    mode: Literal["mcp"]
    transport: HTTPTransport | StdioTransport
    tool_name: str                  # single MCP tool this capability maps to

class HTTPTransport(BaseModel):
    kind: Literal["http"]
    base_url: str
    headers: Dict[str, str] = {}
    protocol_path: str = "/mcp"
    auth: Optional[AuthAlias] = None
    verify_tls: bool = True
    timeout_sec: int = 60
```

**Removed from `McpExecution`:** `tool_calls`, `io`, `discovery`, `connection`
**Removed from `HTTPTransport`:** `retry` (RetryPolicy), `health_path`
**Removed models:** `ToolCallSpec`, `DiscoveryPolicy`, `ExecutionInput`, `ExecutionOutputContract`, `RetryPolicy`

---

## Files Changed

### `services/capability-service/app/models/capability_models.py`
- Replaced `tool_calls: List[ToolCallSpec]` with `tool_name: str` on `McpExecution`
- Removed `io`, `discovery`, `connection` fields from `McpExecution`
- Slimmed `HTTPTransport`: dropped `retry` and `health_path`
- Added `@model_validator(mode='before')` on `McpExecution` for backward compatibility:
  - If old doc has `tool_calls` but no `tool_name` → sets `tool_name = tool_calls[0]["tool"]`
  - Silently ignores `io`, `discovery`, `connection` (Pydantic extra-ignore)
- Removed unused models: `ToolCallSpec`, `DiscoveryPolicy`, `ExecutionInput`, `ExecutionOutputContract`, `RetryPolicy`

### `services/capability-service/app/migrations/migrate_mcp_slim.py` *(new)*
- One-shot async migration script
- Fetches all capability documents where `execution.mode == "mcp"`
- Deserializes using the updated model (backward-compat validator fires)
- Upserts back with the new slim shape (removes old fields from MongoDB)

### `services/capability-service/app/seeds/seed_data_pipeline_capabilities.py`
- `cap.asset.fetch_raina_input` updated to slim format:
  ```python
  McpExecution(
      mode="mcp",
      transport=HTTPTransport(base_url="http://host.docker.internal:8003", ...),
      tool_name="raina.input.fetch",
  )
  ```

### `services/capability-service/app/seeds/seed_microservices_capabilities.py`
- `cap.microservices.generate_guidance_document` updated to slim format with `tool_name="generate.workspace.document"`

### `services/conductor-service/app/agent/graph.py`
- Added `discovered_tools` field to `GraphState`:
  ```python
  discovered_tools: Annotated[
      Dict[str, Dict[str, Any]],
      lambda left, right: {**left, **right}   # merge reducer
  ]
  ```

### `services/planner-service/app/agent/execution_graph.py`
- Added `discovered_tools` field to `ExecutionState` (same shape and merge reducer)
- Added `tool_name: "diagram.mermaid.generate"` to the inline `mermaid_cap` capability dict used by `plan_init`

### `libs/conductor-core/conductor_core/nodes/mcp_input_resolver.py`
- **Complete rewrite** of tool name and schema resolution:
  - Tool name: read from `capability["execution"]["tool_name"]` via `_get_tool_name()`
  - Schema discovery: `_discover_and_cache()` calls `MCPConnection.connect()` → `conn.list_tools()` on the capability's transport, caches result in `state["discovered_tools"][cap_id]`
  - Tool description embedded into schema dict as `_tool_description` key, stripped before passing to JSON schema validator
  - Passes `exec_input_json_schema` directly to `llm.acomplete_json(schema=...)` — no wrapper object
  - Caches discovered tools in `Command` update so `mcp_execution` can reuse without a second `tools/list` call
- Removed helpers: `_cap_io_input_contract()`, `_cap_io_input_json_schema()`, `_cap_io_input_schema_guide()`, `_tool_calls()`

### `libs/conductor-core/conductor_core/nodes/mcp_execution.py`
- Rewrote `_find_status_tool()` to search `discovered_tools[cap_id]` (from state) instead of `execution.tool_calls[]`
- Removed `_tool_calls()` helper
- `_transport_from_capability()` now reads from slim `execution.transport` (no `retry`/`health_path` access)

### `libs/conductor-core/conductor_core/mcp/mcp_client.py`
- Fixed `list_tools()` schema extraction bug:
  - `langchain-mcp-adapters 0.2+` stores `tool.inputSchema` (a plain `dict`) as `t.args_schema`
  - Old code called `.schema()` / `.model_json_schema()` on the dict → both fail with `AttributeError` → exception caught → `schema = {}` silently
  - **Fix:** check `isinstance(raw, dict)` first and use directly; fall back to Pydantic model methods for older adapters
- Changed tool schema preview log from `DEBUG` to `INFO`

### `services/planner-service/app/agent/planner_tools.py`
- `get_capability_details()`: removed "Required inputs" section (was derived from `io.input_contract.json_schema`, no longer present)
- Now shows "MCP tool" section reading `exec_cfg["tool_name"]` and `transport["base_url"]`

### `services/planner-service/app/agent/nodes/plan_input_resolver.py`
- Removed broken imports (`_choose_tool_name`, `_cap_io_input_json_schema`, `_cap_io_input_schema_guide`)
- Replaced `_choose_tool_name` with `_get_tool_name` (reads `execution.tool_name`)
- Uses open schema `{"type": "object", "additionalProperties": True}` for steps 1+ (schema discovered live in conductor, not needed at planning time)
- Fixed `acomplete_json` calls to pass schema dict directly (not wrapped)

### `services/planner-service/app/api/routers/session_routes.py`
- `approve_plan` endpoint: replaced dead `execution.io.input_contract` read with live `tools/list` call
- Calls `MCPConnection.connect(transport_cfg)` → `conn.list_tools()` → picks the target tool by name
- Wraps result as `{"json_schema": raw_schema, "schema_guide": description}` matching the `ApproveResult` frontend type
- Fallback: if MCP call fails, derives a minimal schema from `prefilled_inputs` (for resilience)
- Added `from conductor_core.mcp.mcp_client import MCPConnection, MCPTransportConfig`

### `astra-mcp/.../raina-input-fetcher/src/mcp_raina_input_fetcher/server.py`
- Renamed function parameter `url: str` → `stories_url: str`
- FastMCP derives `tools/list` schema from the Python function signature, so the exposed field name changed from `url` to `stories_url`, matching the pack input key used by the planner

### `astra-VSCodeEx/.../InputFormModal.tsx`
- Updated stale label text from "validated against execution.io.input_contract" to "schema discovered live from MCP server" / "Schema from MCP tools/list"

---

## Bug Fixes

| Bug | Root Cause | Fix |
|-----|-----------|-----|
| LLM returned `{"name": "mcp_tool_args", "schema": {...}}` instead of tool args | `acomplete_json` was passed a wrapper object `{"name": ..., "schema": ...}` instead of the raw JSON schema; LLM echoed the wrapper back | Pass `exec_input_json_schema` directly to `acomplete_json(schema=...)` |
| MCP server rejected args with `url Field required` | MCP server exposed `url` in `tools/list` but pack input / LLM used `stories_url` | Renamed server function parameter to `stories_url` |
| Planner input form always empty | `list_tools()` always returned `{}` schemas — `args_schema` is a plain dict in langchain-mcp-adapters 0.2+, but code tried `.model_json_schema()` on it → `AttributeError` → silently caught | Added `isinstance(raw, dict)` check in `mcp_client.py` |
| `approve_plan` reading removed field | `execution.io.input_contract` removed from slim model but still accessed | Replaced with live `tools/list` call |

---

## Architecture After Refactor

```
Planner "Approve & Run" click
  → POST /sessions/{id}/plan/approve
  → approve_plan reads capability.execution.transport + tool_name
  → MCPConnection.connect() → list_tools()   ← live schema from MCP server
  → returns { input_form_type: "structured", input_contract: { json_schema, schema_guide } }
  → Frontend InputFormModal renders schema-driven form

User submits form
  → POST /sessions/{id}/run
  → run_execution_plan (planner) → conductor /runs
  → mcp_input_resolver: MCPConnection → list_tools() → cached in discovered_tools state
  → LLM resolves tool args using live schema
  → mcp_execution invokes tool with resolved args
```

---

## Running the Migration

After deploying the updated capability-service:

```bash
docker exec astra-capability-service python -m app.migrations.migrate_mcp_slim
```

This rewrites all existing MCP capability documents in MongoDB to the slim format. Safe to re-run — it is idempotent.

---

## Rebuild Required

Both services install `conductor-core` which contains the MCP client and node fixes:

```bash
docker compose -f deploy/docker-compose.yml build astra-planner-service astra-conductor-service
docker compose -f deploy/docker-compose.yml up -d astra-planner-service astra-conductor-service
```

# ASTRA Intent Feature — Implementation Tasks

> Ordered implementation backlog for Claude Code.
> Work top to bottom. Each task is atomic and independently testable.
> Reference `ASTRA_INTENT_FEATURE.md` for design detail and `DECISIONS.md` for rationale.

---

## Phase 1 — Backend foundations

### TASK-001 — Extract `conductor-core` shared library

**What:** Refactor the existing conductor service to extract reusable execution nodes into `libs/conductor-core/`.

**Nodes to extract:**
- `mcp_input_resolver`
- `mcp_execution`
- `llm_execution`
- `diagram_enrichment`
- `narrative_enrichment`
- `persist_run`

**Steps:**
1. Create `libs/conductor-core/` Python package with `pyproject.toml`
2. Move each node function/class into the package, preserving all existing logic exactly
3. Update `conductor-service` to import nodes from `conductor-core` instead of local modules
4. Run existing conductor tests — all must pass unchanged
5. Add `conductor-core` as a dependency in `conductor-service/pyproject.toml`

**Done when:** Conductor service passes all existing tests. No behaviour change. `conductor-core` is importable as a standalone package.

---

### TASK-002 — Planner Service scaffold

**What:** Create the `planner-service` FastAPI application skeleton.

**Steps:**
1. Create `services/planner-service/` with standard project structure:
   - `pyproject.toml` (deps: fastapi, uvicorn, motor, redis, pika, langgraph, conductor-core)
   - `app/main.py` — FastAPI app, lifespan, router registration
   - `app/config.py` — env vars: `PLANNER_LLM_CONFIG_REF`, `MONGODB_URL`, `REDIS_URL`, `RABBITMQ_URL`
   - `app/db.py` — Motor async MongoDB client
   - `app/cache.py` — Redis client (async)
   - `app/events.py` — RabbitMQ publisher + consumer setup
2. Register empty routers for `/planner/sessions` and `/planner/ws`
3. Add health check endpoint `GET /health`
4. Add to docker-compose (or equivalent) alongside existing services

**Done when:** Service starts, `/health` returns 200, connects to MongoDB/Redis/RabbitMQ on startup.

---

### TASK-003 — `PlannerSession` data model and repository

**What:** Define the MongoDB document model and data access layer for planning sessions.

**Models to implement** (see `ASTRA_INTENT_FEATURE.md` Section 3.2 for full schema):
- `PlannerSession`
- `Plan`
- `PlanStep` (with `execution_mode`, `input_contract`, `run_inputs`, `status`, `phase`)
- `SessionMessage`

**Repository methods:**
- `create_session(workspace_id) → PlannerSession`
- `get_session(session_id) → PlannerSession`
- `append_message(session_id, message) → None`
- `update_plan(session_id, plan) → None`
- `update_step_status(session_id, step_order, status, phase, artifacts, timing_ms) → None`
- `set_run_id(session_id, run_id) → None`
- `set_status(session_id, status) → None`

**Done when:** Unit tests for all repository methods pass against a test MongoDB instance.

---

### TASK-004 — Capability manifest cache

**What:** Implement the Redis-backed capability manifest cache in the Planner Service.

**Steps:**
1. `app/manifest_cache.py`:
   - `refresh_manifest()` — fetch all capabilities from capability service HTTP API, store as JSON in Redis key `astra:capability_manifest` with 1hr TTL
   - `get_manifest() → list[CapabilityManifestEntry]` — read from Redis; if miss, call `refresh_manifest()`
   - `CapabilityManifestEntry`: `{ id, name, description, tags, produces_kinds, execution_mode }`
2. Call `refresh_manifest()` in service lifespan startup
3. RabbitMQ consumer: listen on `capability.created` and `capability.updated` → call `refresh_manifest()`

**Done when:** Cache populates on startup. A test that publishes a `capability.updated` event verifies the cache refreshes.

---

### TASK-005 — Planner Agent — LangGraph graph

**What:** Implement the LangGraph planner agent with all nodes and MongoDB checkpointer.

**Nodes to implement** (see `ASTRA_INTENT_FEATURE.md` Section 3.3):
- `session_init`
- `intent_resolver`
- `capability_selector`
- `plan_builder` (includes `input_prefill` logic for MCP first step)
- `clarification`
- `plan_approved`

**Key implementation notes:**
- Use LangGraph `MongoDBSaver` as checkpointer; thread_id = session_id
- `capability_selector` receives the manifest from Redis cache as a structured context block
- `plan_builder` respects `depends_on` from artifact kind definitions when ordering steps
- `plan_builder` sets `execution_mode` on each `PlanStep` from the resolved capability definition
- `plan_builder` marks first step `input_contract` from `capability.execution.io.input_contract` when mode is `mcp`
- `clarification` node pauses graph execution (LangGraph interrupt) and awaits next message
- All LLM calls use polyllm with `PLANNER_LLM_CONFIG_REF`

**Done when:** Integration test — send three messages to a test session, verify plan is assembled with correct steps, modes, and input_contract populated for an MCP-mode first step.

---

### TASK-006 — Planner Service HTTP API

**What:** Implement all REST endpoints for the planner service.

**Endpoints** (see `ASTRA_INTENT_FEATURE.md` Section 3.2):
- `POST /planner/sessions` — create session, return session_id
- `POST /planner/sessions/{id}/message` — append user message, resume planner agent async, return 202
- `GET /planner/sessions/{id}` — return full session document
- `GET /planner/sessions/{id}/plan` — return current Plan
- `POST /planner/sessions/{id}/plan/steps` — add/remove/reorder steps
- `POST /planner/sessions/{id}/approve` — lock plan; return `{ run_id, input_form_type, input_contract?, prefilled_inputs? }`
- `POST /planner/sessions/{id}/run` — accept user inputs; validate; trigger execution agent

**`/run` payload validation:**
- `input_form_type: "structured"` → validate `run_inputs` dict against `input_contract` JSON Schema; return 422 with field-level errors on failure
- `input_form_type: "freetext"` → validate `run_text` is non-empty string; `attachments` list is optional

**Done when:** All endpoints return correct responses in integration tests. `/approve` correctly branches on step 1 execution mode.

---

### TASK-007 — WebSocket streaming endpoint

**What:** Implement `WS /planner/sessions/{id}/stream`.

**Message types to emit:**
```
{ "type": "agent_token", "content": "..." }           # streamed planner LLM tokens
{ "type": "plan_updated", "plan": { ... } }            # whenever plan changes
{ "type": "step_status", "step_order": 1, "status": "running", "phase": "discover", ... }
{ "type": "run_summary", "summary": { ... } }
{ "type": "error", "message": "..." }
```

**Steps:**
1. WebSocket handler authenticates and subscribes to session-scoped event channel
2. Planner agent emits tokens via async generator → handler forwards as `agent_token` messages
3. RabbitMQ consumer for `step.*` and `run.*` events → forwards as `step_status` / `run_summary`
4. Handle reconnection gracefully — client re-connects and receives current session state

**Done when:** E2E test connects WebSocket, sends a message, receives streamed agent tokens and a `plan_updated` message.

---

### TASK-008 — Execution Agent

**What:** Implement the new LangGraph execution agent.

**Nodes:**
- `plan_input_resolver` — dual path for LLM vs MCP first step (see `ASTRA_INTENT_FEATURE.md` Section 3.4)
- `step_executor` — router; publishes RabbitMQ step events
- `mcp_execution`, `llm_execution`, `diagram_enrichment`, `narrative_enrichment`, `persist_run` — **import from conductor-core**

**Trigger:** Consumes `plan.approved` RabbitMQ event OR called directly from `/run` endpoint.

**RabbitMQ events to publish** (see `ASTRA_INTENT_FEATURE.md` Section 3.4 for full list):
- `step.started`, `step.discovery_completed`, `step.enrichment_started`, `step.enrichment_completed`, `step.completed`, `step.failed`, `run.completed`, `run.failed`

**Key implementation notes:**
- `plan_input_resolver` for LLM path: receive `run_text` + `attachments` from `/run` payload; build LLM prompt from text + decoded file content; pass to `llm_execution`
- `plan_input_resolver` for MCP path: receive `run_inputs` dict from `/run` payload; pass to `mcp_input_resolver` from conductor-core; validated against `input_contract` before this point
- On discovery failure: publish `step.failed` + `run.failed`, call `persist_run` with failed status
- Enrichment failures are non-fatal (same as existing conductor) — log, continue

**Done when:** Integration test — run an execution agent with a 2-step test plan (one MCP step, one LLM step). Verify both steps complete, artifacts are persisted, and all expected RabbitMQ events are emitted.

---

## Phase 2 — Frontend implementation

### TASK-009 — Planner tab scaffold + WebSocket connection

**What:** Add the Planner tab to the workspace detail screen and establish the WebSocket connection.

**Steps:**
1. Add "Planner" to the tab list in the workspace detail component
2. Create `PlannerTab` component with split-pane layout (left chat / right canvas)
3. Implement `usePlannerSession` hook:
   - `POST /planner/sessions` on tab open (if no existing session for workspace)
   - WebSocket connect to `/planner/sessions/{id}/stream`
   - Handle reconnection with exponential backoff
   - Dispatch incoming messages to correct state slices
4. Persist session_id in VS Code extension state (keyed by workspace_id) so re-opening tab reconnects

**Done when:** Tab renders, WebSocket connects, console shows incoming messages.

---

### TASK-010 — Chat pane

**What:** Implement the left pane chat thread and input.

**Components:**
- `ChatThread` — renders message list; user messages right-aligned (blue tint), planner messages left-aligned (gray)
- `ChatMessage` — renders bubble; for planner messages renders `ClarificationChips` if present
- `ClarificationChips` — quick-select pill buttons; on click sends message via `POST /message`
- `AttachmentChip` — shows uploaded file name + type icon below user message
- `ThinkingIndicator` — animated dots while agent is responding
- `ChatInput` — textarea + upload button + send button; Enter sends, Shift+Enter newlines
- File upload: attach to message payload as base64; show attached file chip before sending

**Transitions:**
- During execution: input area is hidden; pane shows run log entries instead
- Run log entries styled differently from chat bubbles (monospace, muted, left-aligned with log-ts prefix)

**Done when:** Full conversation flow works — type intent, receive streamed response, click clarification chip, see plan appear on right.

---

### TASK-011 — Plan canvas (planning state)

**What:** Implement the right pane plan canvas for the planning state.

**Components:**
- `PlanCanvas` — renders intent summary pill + step list + add step row + reasoning details
- `PlanStepCard` — shows step number, human-readable name, capability ID (monospace), description, badge (included/optional), toggle switch
- Toggle switch: calls `POST /plan/steps` to update step status (included ↔ skipped)
- `PlannerReasoning` — collapsible `<details>` showing planner reasoning text
- `AddStepRow` — "+" link that calls `sendPrompt` to open capability browser (Phase 2 — no-op in iteration 1)
- Bottom bar: Revise button (clears plan, re-activates chat input) / Approve & run button / Save as pack button (no-op)

**State management:**
- Plan updates arrive via `plan_updated` WebSocket messages → replace local plan state
- Step toggles are optimistic — update local state immediately, rollback on API error

**Done when:** Plan renders correctly from WebSocket data. Step toggles work. Approve button calls `/approve`.

---

### TASK-012 — Input form modal (both modes)

**What:** Implement the input form modal shown after "Approve & run" for both MCP and LLM first-step modes.

**Trigger:** Always shown after `/approve` response is received. Form type determined by `input_form_type` in response.

**Component: `InputFormModal`** — modal overlaying the blurred plan canvas; shared shell for both variants

**Variant A — Structured form (`input_form_type: "structured"`, MCP mode):**
- Header: "Step 1 requires inputs" / capability_id / "mode: mcp"
- `SchemaFormField` renders correct widget per JSON Schema field type:
  - `string` → `<input type="text">`
  - `string` + `format: uri` → `<input type="url">`
  - `enum` → `EnumPillGroup` (pill radio buttons)
  - `boolean` → toggle switch
  - `file` / `file[]` → drop zone + attached file chips
- Pre-filled values from `prefilled_inputs` shown with "✦ Pre-filled from your conversation" notice
- Client-side validation against `input_contract` JSON Schema (use `ajv`) before submit
- Inline field-level error messages on validation failure
- Footer: "Validated against execution.io.input_contract" / Back / Start run →
- Submit: `POST /run` with `{ run_inputs: { ...fieldValues } }`

**Variant B — Freetext form (`input_form_type: "freetext"`, LLM mode):**
- Header: "Step 1 requires inputs" / capability_id / "mode: llm"
- Large textarea: placeholder "Describe what you want this step to process…" (required)
- File upload drop zone: "Attach documents, diagrams, or source files" (optional, multiple)
- Attached file chips with remove button
- No pre-fill — form opens empty
- Validation: textarea must be non-empty before submit enabled
- Footer: "Your text and files will be passed directly to the AI capability" / Back / Start run →
- Submit: `POST /run` with `{ run_text: "...", attachments: [{ filename, content_base64, mime_type }] }`

**On submit (both variants):** transitions to execution view on 200 response; shows field errors on 422.

**Done when:** Both form variants render correctly. Structured form validates and rejects on missing required fields. Freetext form disables submit when textarea empty. Both submit payloads trigger execution state transition on success.

---

### TASK-013 — Execution view (running + completed + failed states)

**What:** Implement the right pane execution view and all terminal states.

**Components:**
- `ExecutionView` — renders progress bar + step list
- `ExecutionStepCard` — variants for: done (green left border + ✓), running (blue border + spin icon + phase badge), enrich (purple border + ◈ icon), pending (dimmed), failed (red border + ✗), skipped (very dimmed)
- Phase badge: `discover` (blue), `enrich · diagram` (purple), `narrative_enrich` (amber)
- `RunSummaryCard` — shown at top of completed execution; shows New/Updated/Unchanged counts + total duration + "View all artifacts in Artifacts tab →" link
- Progress bar: width = (completed_steps / total_steps) * 100%; green when completed, red when failed

**Step events from WebSocket:**
- `step_status` with `status: running` + `phase: discover` → update card to running state
- `step_status` with `status: done` → update card to done state, show artifact chips
- `run_summary` → show summary card, set all pending steps to skipped if failed

**Bottom bar transitions:**
- Executing: artifact count + Pause button
- Completed: "View artifacts →" (navigates to Artifacts tab) + Re-run button
- Failed: "View partial artifacts" + "Replan →" (resets to planning state with context)

**Done when:** All five step states render correctly. Progress bar animates. Summary card shows correct counts.

---

### TASK-014 — Artifact popover

**What:** Implement the artifact chip popover with three representation tabs.

**Components:**
- `ArtifactChip` — clickable chip on completed step card; colored dot (amber=narrative, purple=diagram, blue=data); active state on open
- `ArtifactPopover` — slide-in panel from right edge of right pane (not a full modal — preserves plan context)
  - Header: kind ID (monospace) + artifact title + close button
  - Rep switcher: Narrative / Diagram / Data tabs with colored dots
  - Body: representation content (see below)
  - Footer: `auto:overview · audience: developer` label + "Open in Artifacts →" link

**Representation content:**
- `Narrative` (default): fetch `GET /artifact/{ws_id}/{id}/narrative?id=auto:overview` → render Markdown
- `Diagram`: fetch `GET /artifact/{ws_id}/{id}/diagram` → render Mermaid via `mermaid.js`
- `Data`: fetch `GET /artifact/{ws_id}/{id}` → render JSON with syntax highlighting

**Dismissal:** click backdrop, click ✕, or press Escape

**"Open in Artifacts →":** switches workspace detail tab to Artifacts, passes artifact ID as filter param

**Done when:** Clicking a chip opens popover. All three tabs fetch and render correct content. Navigation to Artifacts tab works.

---

## Phase 3 — Integration and polish

### TASK-015 — E2E integration test

**What:** Full flow test from intent input to artifact popover.

**Test scenario:**
1. Create workspace
2. Open Planner tab → session created, WebSocket connected
3. Type intent message → planner responds with plan
4. Click clarification chip → plan updates
5. Click Approve & run → (if MCP first step) fill and submit form
6. Watch execution steps complete via WebSocket
7. Click artifact chip → popover opens with narrative

**Done when:** Test passes against local environment with all services running.

---

### TASK-016 — Error handling and edge cases

**What:** Implement graceful handling of all failure scenarios.

**Scenarios:**
- WebSocket disconnect mid-execution → reconnect + replay current session state
- Execution step failure → show failed state, enable Replan flow
- Planner LLM timeout → show error message in chat, allow retry
- `input_contract` validation failure on submit → show inline field errors
- Capability service unavailable on manifest refresh → serve stale cache + log warning
- Session not found (stale session_id) → create new session, inform user

**Done when:** Each scenario tested manually or via integration test. No unhandled exceptions surface to the user.

---

### TASK-017 — Docker Compose and deployment config

**What:** Add `planner-service` and (if separate) `execution-agent` to deployment configuration.

**Steps:**
1. Add `planner-service` to `docker-compose.yml` with correct env vars and dependencies
2. Add `PLANNER_LLM_CONFIG_REF` to ConfigForge / `.env.example`
3. Ensure `conductor-core` is built as a local package dependency available to both `conductor-service` and `planner-service`
4. Update README with new service description and startup instructions

**Done when:** `docker-compose up` starts all services including planner-service. Health checks pass.

---

## Quick reference — implementation order

```
TASK-001  Extract conductor-core          ← start here; zero risk
TASK-002  Planner service scaffold
TASK-003  Session data model
TASK-004  Manifest cache
TASK-005  Planner agent (LangGraph)       ← most complex backend task
TASK-006  HTTP API
TASK-007  WebSocket endpoint
TASK-008  Execution agent                 ← most complex; uses conductor-core
TASK-009  Frontend: tab + WebSocket
TASK-010  Frontend: chat pane
TASK-011  Frontend: plan canvas
TASK-012  Frontend: MCP input form
TASK-013  Frontend: execution view
TASK-014  Frontend: artifact popover
TASK-015  E2E test
TASK-016  Error handling
TASK-017  Deployment config
```

# Planner Service — Implementation Reference

## Overview

The **planner-service** is ASTRA's intent-driven planning and execution layer. It translates a user's natural-language intent into an ordered capability plan, presents that plan for user review, and then executes it against the registered capability registry using the same LangGraph execution infrastructure shared with the conductor-service.

It runs at port **9025** and is the backend for the Planner tab in the ASTRA VSCode extension.

---

## Responsibilities

| Responsibility | Mechanism |
|---|---|
| Understand user intent from free-form chat | Planner Agent (LangGraph) |
| Select matching capabilities from the registry | Capability manifest cache + LLM |
| Build an ordered execution plan with prefilled inputs | Plan builder node |
| Present and allow editing of the plan | REST API (`/plan`, `PATCH /plan`) |
| Lock the plan and return input form metadata | `POST /plan/approve` (ADR-006) |
| Accept confirmed user inputs and start execution | `POST /run` (ADR-006) |
| Execute the plan using conductor-core nodes | Execution Agent (LangGraph) |
| Stream events in real time to the frontend | Per-session WebSocket + RabbitMQ |

---

## Session Lifecycle

Every user interaction is scoped to a **PlannerSession** stored in MongoDB. A session holds the full chat history, the current plan, and state machine status.

```
planning
  ↓ (LLM needs clarification)
awaiting_clarification
  ↓ (user replies)
planning
  ↓ (plan ready)
awaiting_inputs       ← optional intermediate state
  ↓
ready_to_execute      ← set by POST /plan/approve
  ↓
executing             ← set by POST /run
  ↓
completed | failed
```

`SessionStatus` values:

| Status | Meaning |
|---|---|
| `planning` | Agent is building or refining the plan |
| `awaiting_clarification` | Agent asked a clarifying question |
| `awaiting_inputs` | Plan ready; waiting for user to provide inputs |
| `ready_to_execute` | Plan approved; waiting for `/run` call |
| `executing` | Execution graph running |
| `completed` | Run finished successfully |
| `failed` | Run ended with error |

---

## Data Models

### PlannerSession

```
session_id    string        MongoDB _id (also used as playbook_id during execution)
org_id        string
workspace_id  string
status        SessionStatus
messages      ChatMessage[]
plan          PlanStep[]
intent        dict          Last extracted intent from LLM
active_run_id string        run_id of the most recent PlaybookRun
```

### PlanStep

```
step_id        string   Auto-generated (step-{hex8})
capability_id  string   e.g. "cap.cobol.copybook.parse"
title          string
description    string
enabled        bool     User can toggle steps off
inputs         dict     General config — empty at plan time
run_inputs     dict     ADR-009: LLM-prefilled MCP form values shown to user for review
order          int
```

`inputs` and `run_inputs` are intentionally separate. `inputs` is reserved for general step configuration while `run_inputs` holds the values that map to the first-step MCP capability's `input_contract` form — they are populated by the LLM during planning and presented to the user for review/correction before execution starts.

### RunRequest

The body of `POST /{session_id}/run`:

```
strategy     string          "baseline" | "delta"  (default: "baseline")
workspace_id string          optional override
run_inputs   dict            MCP structured form values confirmed by user
run_text     string          Freetext for LLM-mode first steps
attachments  list[dict]      File uploads for LLM-mode capabilities
```

---

## HTTP API

All session routes are under `/sessions`.

| Method | Path | Description |
|---|---|---|
| `POST` | `/sessions` | Create a new session; optional `initial_message` starts planning immediately |
| `GET` | `/sessions/{id}` | Fetch full session state |
| `POST` | `/sessions/{id}/messages` | Send a user message; kicks off planner agent in background |
| `GET` | `/sessions/{id}/plan` | Get the current plan steps |
| `PATCH` | `/sessions/{id}/plan` | Update plan steps (user edits) |
| `POST` | `/sessions/{id}/plan/approve` | Lock plan; return input form metadata (ADR-006) |
| `POST` | `/sessions/{id}/run` | Submit confirmed inputs; start execution (ADR-006) |
| `GET` | `/sessions/{id}/runs/{run_id}` | Get run status |

### Two-Step Execute Flow (ADR-006)

The approve → run separation ensures the user sees and confirms the input form before execution starts.

**Step 1 — `POST /plan/approve`**

- Sets session status to `ready_to_execute`
- Looks up the first enabled step's capability from the manifest cache
- Determines `input_form_type`:
  - `"structured"` — if `execution.mode == "mcp"` (renders a JSON Schema form)
  - `"freetext"` — if `execution.mode == "llm"` (renders a free-text textarea)
- Reads `prefilled_inputs` from `first_step.run_inputs` (LLM-generated guesses)
- Returns:
  ```json
  {
    "session_id": "...",
    "status": "ready_to_execute",
    "input_form_type": "structured | freetext",
    "prefilled_inputs": { ... },
    "input_contract": { ... }
  }
  ```

**Step 2 — `POST /run`**

- Guards: session must be in `ready_to_execute`
- Sets status to `executing`
- Publishes `execution.started` WebSocket event
- Schedules `_run_execution_bg` as FastAPI background task
- Returns immediately: `{ "session_id": "...", "status": "executing" }`

---

## WebSocket API

Endpoint: `GET /ws/sessions/{session_id}`

The planner-service maintains a per-session **in-memory event stream** (`SessionStream`). Events are appended with a sequential `idx` allowing clients to resume from a cursor after reconnect.

### Protocol

```
Client → Server: { "type": "resume", "cursor": N }   (optional, within first 2 s)
Server → Client: { "idx": N, "type": "...", ... }     (events)
Client → Server: { "type": "ping" }
Server → Client: { "type": "pong" }
Server → Client: { "type": "keepalive" }              (every 30 s if idle)
```

### Events delivered on this channel

| Event type | Trigger |
|---|---|
| `planner.response` | Planner agent completes a planning turn |
| `planner.error` | Planner agent failed |
| `plan.updated` | User edited plan steps via `PATCH /plan` |
| `plan.approved` | `POST /plan/approve` completed |
| `execution.started` | `POST /run` accepted |
| `execution.run_created` | `plan_init_node` created the PlaybookRun |
| `execution.completed` | Run finished successfully |
| `execution.failed` | Run ended with error |

**Note:** Execution step-level events (`step.started`, `step.completed`, etc.) travel via RabbitMQ → notification-service → notification WebSocket, not this channel. See [Event Channels](#event-channels).

---

## Planner Agent Graph

Invoked for every user message turn. Built fresh per invocation using `StateGraph` from LangGraph. No persistent checkpointer — state is carried in the `PlannerState` dict.

### Graph

```
session_init → intent_resolver → capability_selector → plan_builder
                                                              ↓
                                               (confidence < 0.65?)
                                              yes ↓           no ↓
                                         clarification    plan_approved
                                               ↓               ↓
                                              END             END
```

### PlannerState fields

| Field | Type | Description |
|---|---|---|
| `session_id` | str | |
| `org_id` / `workspace_id` | str | |
| `messages` | list | Full chat history from MongoDB |
| `current_message` | str | Latest user message |
| `intent` | dict | Extracted intent (`intent_type`, `description`, `entities`, `constraints`, `confidence`) |
| `candidate_capabilities` | list | Full capability objects selected by LLM |
| `draft_plan` | list | Assembled plan steps with prefilled `run_inputs` |
| `confidence_score` | float | Plan assembly confidence from LLM (0–1) |
| `needs_clarification` | bool | Routes to `clarification` node if True |
| `clarification_question` | str | Question sent to user |
| `response_message` | str | Narrative message returned to frontend |
| `status` | str | `"planning"` | `"clarification"` | `"failed"` |

### Nodes

#### `session_init`

Loads `PlannerSession` from MongoDB, populates `messages`, `org_id`, `workspace_id` into state. Short-circuits with `error` if session not found.

#### `intent_resolver`

Calls the agent LLM to extract structured intent from the user message and recent chat history (last 6 messages). Returns a JSON object with `intent_type`, `description`, `entities`, `constraints`, and `confidence`. Falls back gracefully on parse failure.

Intent types: `analyze`, `generate`, `document`, `review`, `refactor`, `test`, `other`

#### `capability_selector`

Fetches all capabilities from the manifest cache, summarises them into a compact list (id, title, description, produces_kinds, mode), and asks the LLM to select and rank the capabilities that best match the intent. Returns:
- Full resolved capability objects ordered by `order`
- `needs_clarification` flag if the LLM could not confidently match

#### `plan_builder`

Takes selected capabilities and the conversation context. Calls the LLM to build an ordered plan with prefilled input values. Key behaviours:
- If first capability is `mcp` mode and has an `input_contract`, an explicit ADR-009 instruction is appended to the prompt to extract values from the conversation
- LLM-generated prefills go into `run_inputs`; `inputs` stays empty
- If `confidence < 0.65`, routes to `clarification`

#### `clarification`

Saves the clarification question to the session's `response_message` and appends it as an assistant chat message to MongoDB.

#### `plan_approved`

Saves the assembled `draft_plan` to the `PlannerSession.plan` field in MongoDB and sets a success response message.

---

## Execution Agent Graph

Converts an approved `PlannerSession` plan into the conductor-core execution format and runs it. Reuses conductor-core's shared execution nodes — the same nodes used by the conductor-service.

### Graph

```
plan_init → capability_executor ←──────────────────────────────────┐
                 ↓ (mcp)                  ↑ (loop back)            │
          mcp_input_resolver              │                         │
          (plan_input_resolver)           │                         │
                 ↓                        │                         │
          mcp_execution ──────────────────┘                         │
                                                                    │
          capability_executor ──→ llm_execution ────────────────────┘
                 ↓ (after discover)
          diagram_enrichment ────→ capability_executor
                 ↓ (after enrich)
          narrative_enrichment ──→ capability_executor
                 ↓ (all steps done)
          persist_run → END
```

### ExecutionState

The state dict inherits the full conductor-core `GraphState` shape, extended with planner-specific fields:

| Field | Description |
|---|---|
| `session_id` | Source PlannerSession |
| `run_inputs` | User-confirmed inputs from `/run` body |
| `request` | Pack run request: `{ playbook_id, inputs: run_inputs, strategy, workspace_id }` |
| `run` | Serialised `PlaybookRun` document |
| `pack` | `{ capabilities: [...], playbooks: [{ id, steps }] }` |
| `artifact_kinds` | Map of `kind_id → kind spec` pre-fetched from artifact-service |
| `agent_capabilities_map` | Map of `cap_id → capability` for platform enrichment tools |
| `step_idx` | Current step index |
| `current_step_id` | Step ID being processed |
| `phase` | `"discover"` \| `"enrich"` \| `"narrative_enrich"` |
| `staged_artifacts` | Artifacts produced so far (accumulates across steps) |
| `dispatch` | Current step + capability + resolved args for executor nodes |

### `plan_init` Node

Planner-service–specific node. Runs first and sets up the full execution state:

1. Loads the `PlannerSession` from MongoDB
2. Resolves full capability objects from the manifest cache for each enabled step
3. Builds a `pack` dict in conductor-core format: `{ capabilities, playbooks }`
4. Constructs the diagram MCP capability from settings (config-driven, not registry-dependent — see [Platform Enrichment](#platform-enrichment))
5. Pre-fetches artifact kind specs concurrently from artifact-service for all `produces_kinds` across all capabilities
6. Determines run strategy (baseline or delta) from the frontend-supplied value
7. Creates a `PlaybookRun` document in MongoDB and sets it as the session's `active_run_id`
8. Publishes `execution.run_created` WebSocket event
9. Returns the full initial state dict

### Subsequent Execution Nodes

After `plan_init`, all nodes are imported directly from `conductor_core`:

| Node | Source | Description |
|---|---|---|
| `capability_executor` | `conductor_core.nodes.capability_executor` | Central router: phase transitions, step dispatch, terminal conditions, event publishing |
| `mcp_input_resolver` (as `mcp_input_resolver`) | `app.agent.nodes.plan_input_resolver` | Planner-specific: step 0 uses `request["inputs"]` (user-confirmed); steps 1+ use LLM + artifact context |
| `mcp_execution` | `conductor_core.nodes.mcp_execution` | Executes MCP tools via HTTP transport |
| `llm_execution` | `conductor_core.nodes.llm_execution` | Executes LLM capabilities using kind schemas |
| `diagram_enrichment` | `conductor_core.nodes.diagram_enrichment` | Generates Mermaid diagrams via the diagram MCP server |
| `narrative_enrichment` | `conductor_core.nodes.narrative_enrichment` | Generates Markdown narratives via the agent LLM |
| `persist_run` | `conductor_core.nodes.persist_run` | Normalises and persists artifacts to artifact-service |

### Plan Input Resolver (Planner-specific)

The planner-service uses `plan_input_resolver_node` (not the standard `mcp_input_resolver_node` from conductor-core) to handle the two-step ADR-006 flow:

- **Step 0:** User-confirmed inputs from `state["request"]["inputs"]` (populated from `RunRequest.run_inputs`) are used directly. No LLM call.
- **Steps 1+:** Mirrors conductor-core's `mcp_input_resolver` — uses LLM + staged artifact context + the capability's `input_contract` to synthesise arguments. Validates against JSON Schema with one repair attempt.

---

## Run Strategies

Inherited directly from conductor-core. The frontend supplies the strategy in the `RunRequest` body.

| Strategy | Behaviour |
|---|---|
| `baseline` | `persist_run_node` calls `artifact-service /artifact/{workspace_id}/upsert-batch` — artifacts are promoted to the workspace baseline |
| `delta` | Artifacts are stored in `PlaybookRun.run_artifacts` within the `pack_runs` collection only; not promoted |

---

## Platform Enrichment — Diagram MCP Server

The diagram MCP server (`cap.diagram.mermaid`) generates Mermaid diagrams from artifact JSON. It is a **platform-level service** — not registered in the capability registry — so it is always available regardless of what capabilities are installed.

Configuration is driven by environment variables:

| Env var | Default | Description |
|---|---|---|
| `DIAGRAM_MCP_BASE_URL` | `http://host.docker.internal:8001` | Base URL of the diagram MCP server |
| `DIAGRAM_MCP_PATH` | `/mcp` | MCP protocol path |
| `DIAGRAM_MCP_TIMEOUT_SEC` | `120` | Per-call timeout |

`plan_init_node` builds the `mermaid_cap` dict directly from `settings` and injects it into `agent_capabilities_map`. The `diagram_enrichment_node` (from conductor-core) looks up `agent_capabilities_map["cap.diagram.mermaid"]` to get its transport config — if present, it proceeds; if absent, it skips enrichment gracefully.

---

## Capability Manifest Cache

The manifest cache provides capability objects to both the planner graph (for LLM selection) and the execution graph (for step resolution).

### Cache Strategy

1. **In-memory** (`_memory_cache` dict) — fastest; populated at startup and on RabbitMQ events
2. **Redis** (`astra:planner:cap:{id}` keys, TTL = `MANIFEST_CACHE_TTL_SECONDS`) — survives process restarts
3. **Direct capability-service call** — fallback if both caches miss

### Startup Warm-up

On startup (`main.py` lifespan), `cache.refresh()` fetches all capabilities from capability-service and populates both in-memory and Redis caches.

### Event-Driven Refresh

A RabbitMQ consumer (`capability_consumer`) listens on `planner.capability.v1` for `capability.updated` and `capability.created` events and calls `cache.refresh_one(cap_id)` to keep individual entries current.

---

## Event Channels

Two separate channels carry different classes of events.

### Channel 1 — Planner Direct WebSocket

`ws://localhost:9025/ws/sessions/{session_id}`

- Session-scoped, private to the session owner
- Backed by `SessionStream` (in-memory, per-process)
- Supports replay from cursor (useful on reconnect)
- Carries: planner chat events, plan updates, high-level execution lifecycle

Events published via `publish_to_session()`:

| Event | Source |
|---|---|
| `planner.response` | `_run_planner_bg` after LLM planning |
| `planner.error` | `_run_planner_bg` on failure |
| `plan.updated` | `PATCH /plan` |
| `plan.approved` | `POST /plan/approve` |
| `execution.started` | `POST /run` |
| `execution.run_created` | `plan_init_node` |
| `execution.completed` | `_run_execution_bg` on success |
| `execution.failed` | `_run_execution_bg` on error |

### Channel 2 — RabbitMQ → Notification Service

Events published to RabbitMQ via `bus.publish()` with routing key `astra.planner.<event>.v1`:

| Event | Source |
|---|---|
| `execution.completed` | `_run_execution_bg` on success |
| `execution.failed` | `_run_execution_bg` on error |
| Step events (`step.started`, `step.completed`, etc.) | `capability_executor_node` via `EventPublisher` |

The notification-service binds `*.planner.*.v1` and `*.planner.*.*.v1` and broadcasts these to all connected WebSocket clients on the workspace.

**Important:** `planner.response` and `planner.error` are **not** published to RabbitMQ. They are session-private chat messages. Publishing them to the broker would cause duplicate delivery to the same frontend client (which subscribes to both channels).

---

## Startup Sequence

Controlled by the FastAPI lifespan context manager in `main.py`:

1. Configure structured logging
2. Connect to RabbitMQ (publisher connection)
3. Ensure MongoDB indexes
4. Warm-up capability manifest cache (non-fatal on failure)
5. Start capability consumer background task (keeps cache in sync)
6. Yield (serve requests)
7. On shutdown: stop consumer → close RabbitMQ → close MongoDB

---

## Configuration

All settings are in `app/config.py` and read from environment variables (`.env.example` for local dev):

| Variable | Default | Description |
|---|---|---|
| `MONGO_URI` | — | MongoDB connection string |
| `MONGO_DB` | `astra_planner` | Database name |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis for manifest cache |
| `RABBITMQ_URI` | — | RabbitMQ AMQP URI |
| `RABBITMQ_EXCHANGE` | `raina.events` | Exchange name |
| `EVENTS_ORG` | `astra` | Org prefix for routing keys |
| `CAPABILITY_SVC_BASE_URL` | `http://astra-capability-service:9021` | Capability service |
| `ARTIFACT_SVC_BASE_URL` | `http://astra-artifact-service:9020` | Artifact service |
| `PLANNER_LLM_CONFIG_REF` | — | ConfigForge ref for planner + narrative LLM |
| `CONFIG_FORGE_URL` | — | ConfigForge service URL |
| `DIAGRAM_MCP_BASE_URL` | `http://host.docker.internal:8001` | Diagram MCP server |
| `DIAGRAM_MCP_PATH` | `/mcp` | Diagram MCP protocol path |
| `DIAGRAM_MCP_TIMEOUT_SEC` | `120` | Diagram MCP timeout |
| `MANIFEST_CACHE_TTL_SECONDS` | `300` | Redis TTL for cached capabilities |
| `CONSUMER_QUEUE_CAPABILITY` | `planner.capability.v1` | RabbitMQ queue for capability events |
| `LOG_LEVEL` | `INFO` | Log level |

---

## Service Dependencies

| Service | Purpose | Protocol |
|---|---|---|
| capability-service (9021) | Fetch capability manifests | HTTP |
| artifact-service (9020) | Fetch kind specs; persist artifacts | HTTP |
| MongoDB | Session, plan, run storage | Motor async |
| Redis | Manifest cache | redis.asyncio |
| RabbitMQ | Event publishing + capability event consumption | AMQP (aio-pika) |
| ConfigForge (8040) | Resolve LLM configurations by ref | HTTP |
| Diagram MCP server (8001) | Generate Mermaid diagrams from artifact JSON | HTTP / MCP |

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| Two-step `/approve` + `/run` (ADR-006) | Separates plan locking from execution; allows frontend to show input form and collect user-confirmed values before any execution begins |
| `run_inputs` separate from `inputs` on `PlanStep` (ADR-009) | `inputs` is general step config; `run_inputs` holds LLM-prefilled MCP form values shown to user. Keeps concerns distinct |
| Planner session = playbook at execution time | `session_id` is reused as both `pack_id` and `playbook_id`. No separate pack registration needed for intent-driven runs |
| Diagram MCP from settings, not registry | The diagram enrichment service must always be available regardless of what capabilities are installed. Config-driven injection avoids a registry dependency |
| `plan_input_resolver` instead of `mcp_input_resolver` | Step 0 must use user-confirmed inputs from `/run`, not LLM inference. Custom node handles both cases cleanly |
| Planner WS carries only session-private events | Prevents RabbitMQ-path duplication. Step events that need workspace broadcast go via RabbitMQ → notification-service only |

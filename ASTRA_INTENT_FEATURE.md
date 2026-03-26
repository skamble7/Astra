# ASTRA Intent-Driven Execution — Feature Design Document

> **Purpose:** Ground truth for implementing the intent-driven planner feature in ASTRA.
> Read this file at the start of every Claude Code session working on this feature.
> Cross-reference with `DECISIONS.md` for rationale and `TASKS.md` for implementation order.

---

## 1. Feature Overview

ASTRA currently executes capability packs — pre-authored, fixed recipes that define what capabilities run, in what order, with what inputs. This feature adds a new **intent-driven mode** where:

1. A user expresses what they want in natural language (and optionally uploads documents/diagrams)
2. A **Planner Agent** understands the intent and assembles a capability plan dynamically
3. The plan is presented to the user as an ordered, editable todo list for approval
4. An **Execution Agent** executes the approved plan and streams progress back
5. Produced artifacts surface inline with narrative/diagram/data representations

This runs inside a **workspace** and is exposed as a new **"Planner" tab** in the VS Code extension frontend.

---

## 2. Existing Backend (do not modify these services)

### 2.1 Services

| Service | Responsibility | Key APIs |
|---|---|---|
| **Artifact Service** | Stores/versions all artifacts, owns kind registry | `POST /artifact/{ws_id}`, `GET /artifact/{ws_id}`, `GET /kinds/{id}` |
| **Capability Service** | Manages capabilities, packs, pack inputs | `GET /capability`, `GET /capability/{id}`, `GET /capability/packs/{id}/resolve` |
| **Conductor Service** | Pack-driven run execution (LangGraph) | `POST /runs/start` (requires `pack_id` + `playbook_id`) |

### 2.2 Conductor LangGraph nodes (existing — to be extracted into `conductor-core`)

```
input_resolver → capability_executor (router) → mcp_input_resolver
                                               → mcp_execution
                                               → llm_execution
                                               → diagram_enrichment
                                               → narrative_enrichment
                                               → persist_run
```

Three phases per step: `discover → enrich → narrative_enrich`

### 2.3 Key existing patterns to reuse

- **polyllm** — unified LLM abstraction layer; use for all LLM calls
- **ConfigForge** — external LLM config store; reference via canonical string e.g. `"dev.llm.openai.fast"`
- **RabbitMQ events** — all services publish events on state changes; consumers subscribe
- **MongoDB** — primary store for all services
- **ETags** — optimistic concurrency on artifact updates

### 2.4 Capability modes (critical for input handling)

Every capability declares `execution.mode` as either `"mcp"` or `"llm"`:

- **`llm` mode** — takes natural language as input. No declared input contract. The user provides free-text intent and/or file uploads via a text/upload form before execution starts. The execution agent builds the LLM prompt from this input.
- **`mcp` mode** — declares `execution.io.input_contract` (JSON Schema). The user provides structured inputs via a schema-driven form before execution starts. The MCP tool is called with the exact validated arguments from this form.

**Critical rule:** Both modes require the user to explicitly supply input via a form before execution begins. The form type differs — structured fields for MCP, free-text + file upload for LLM — but the input gate always exists. Execution never starts automatically from conversation context alone.

This distinction drives the input form type shown after plan approval, specifically for the **first step** of a plan. Steps 2–N always consume upstream artifacts via `depends_on` and never require user input.

---

## 3. New Backend Components

### 3.1 `conductor-core` — shared library

**What it is:** A Python package extracted from the existing conductor service containing the execution nodes that are reusable across both the existing conductor and the new execution agent.

**Nodes to extract:**
- `mcp_input_resolver`
- `mcp_execution`
- `llm_execution`
- `diagram_enrichment`
- `narrative_enrichment`
- `persist_run`

**What stays in the conductor service (not extracted):**
- `input_resolver` (pack-specific)
- `capability_executor` (pack-specific router)

**Package location:** `libs/conductor-core/` in the monorepo

---

### 3.2 Planner Service — new FastAPI service

**Responsibility:** Manages planning sessions. Hosts the Planner Agent. Serves the WebSocket stream to the frontend.

#### API surface

```
POST   /planner/sessions                        Create new session
POST   /planner/sessions/{id}/message           Send user message → triggers planner agent
GET    /planner/sessions/{id}                   Get session state
GET    /planner/sessions/{id}/plan              Get current assembled plan
POST   /planner/sessions/{id}/plan/steps        Add/remove/reorder steps (power user edits)
POST   /planner/sessions/{id}/approve           Lock plan; returns requires_inputs + input_contract
POST   /planner/sessions/{id}/run               Submit run_inputs (MCP first step only); starts execution
WS     /planner/sessions/{id}/stream            Stream: agent tokens, plan mutations, execution events
```

#### `/approve` response schema

```json
{
  "run_id": "string",
  "input_form_type": "structured | freetext",
  "input_contract": { /* JSON Schema — present only when input_form_type = structured (mcp mode) */ },
  "prefilled_inputs": { /* planner's best-effort pre-fill — present only when input_form_type = structured */ }
}
```

**`/approve` always requires a subsequent `/run` call — execution never starts automatically.**

- `input_form_type: "structured"` (step 1 is `mcp` mode) → frontend shows schema-driven form derived from `input_contract`; user fills structured fields; submits via `POST /run` with `{ run_inputs: dict }`
- `input_form_type: "freetext"` (step 1 is `llm` mode) → frontend shows free-text area + file upload zone; user types natural language and/or attaches files; submits via `POST /run` with `{ run_text: str, attachments: [] }`

The `/run` endpoint validates the payload against mode-appropriate rules and triggers the execution agent.

#### MongoDB collections

```
planner_sessions:
  _id, session_id, workspace_id
  status: active | approved | executing | completed | failed
  messages: [{ role: user|planner, content, timestamp, attachments?: [] }]
  plan: Plan | null
  run_id: str | null
  created_at, updated_at

Plan:
  steps: [PlanStep]
  intent_summary: str
  reasoning: str

PlanStep:
  order: int
  capability_id: str          # e.g. cap.arch.domain.model.generate
  capability_name: str
  description: str            # plain English — what this step does
  execution_mode: mcp | llm
  produces_kinds: [str]
  input_contract: dict | null # JSON Schema; present when execution_mode = mcp AND step is first
  run_inputs: dict | null     # populated from structured form submit (mcp mode first step)
  run_text: str | null        # populated from freetext form submit (llm mode first step)
  attachments: list | null    # populated from file uploads (llm mode first step)
  status: included | optional | skipped | running | done | failed
  phase: discover | enrich | narrative_enrich | null
  artifacts_produced: [str]
  timing_ms: int | null
```

#### Capability manifest cache (Redis)

- On service startup: fetch all capabilities from capability service, store flattened manifest in Redis
  - Per entry: `{ id, name, description, tags, produces_kinds, execution.mode }`
- Invalidation: consume `capability.created` and `capability.updated` RabbitMQ events
- Planner LLM receives this manifest as structured context when selecting capabilities

---

### 3.3 Planner Agent — LangGraph graph (runs inside Planner Service)

**Persistence:** Stateful across turns using LangGraph MongoDB checkpointer (session_id = thread_id)

#### Nodes

| Node | Responsibility |
|---|---|
| `session_init` | Load capability manifest from Redis; initialise graph state with workspace context and uploaded docs |
| `intent_resolver` | Call planner LLM with message + history + file content → produces structured intent: goal, domain signals, constraints, ambiguities |
| `capability_selector` | LLM reasons over capability manifest to select and rank relevant capabilities |
| `plan_builder` | Assemble selected capabilities into ordered Plan; respect `depends_on` for sequencing; mark steps included/optional; run `input_prefill` heuristic for MCP first step |
| `clarification` | If ambiguities detected: generate clarification questions as quick-select chips; pause graph and await next user message |
| `plan_approved` | Terminal node; emit `plan.approved` RabbitMQ event; trigger execution agent |

#### LLM configuration

- Env var: `PLANNER_LLM_CONFIG_REF` (e.g. `"dev.llm.openai.fast"`)
- Resolved via polyllm + ConfigForge (same pattern as conductor's `CONDUCTOR_LLM_CONFIG_REF`)

#### `input_prefill` heuristic (inside `plan_builder`)

When step 1 is `mcp` mode only:
- Call planner LLM with `input_contract` JSON Schema + full conversation history
- Ask it to produce best-effort `run_inputs` JSON matching schema fields to mentioned values
- Store as `PlanStep.run_inputs`; frontend shows these as pre-filled form values

When step 1 is `llm` mode: no pre-fill is attempted. The freetext form opens empty; the user types their input fresh. (Conversation context is available as reference in the left pane but is not auto-copied into the form.)

---

### 3.4 Execution Agent — new LangGraph graph

**Deployment:** Separate process (can be co-located in Planner Service initially, split later)
**Trigger:** Consumes `plan.approved` RabbitMQ events OR direct call from `/run` endpoint

#### Nodes

| Node | Responsibility |
|---|---|
| `plan_input_resolver` | Replaces conductor's `input_resolver`. Takes approved `Plan` directly (no pack_id needed). Resolves full capability definitions. Handles both input paths (see below). |
| `step_executor` | Router equivalent to conductor's `capability_executor`. Maintains step index and phase. Publishes step events to RabbitMQ (consumed by WebSocket → frontend). |
| `mcp_execution` | **From conductor-core** |
| `llm_execution` | **From conductor-core** |
| `diagram_enrichment` | **From conductor-core** |
| `narrative_enrichment` | **From conductor-core** |
| `persist_run` | **From conductor-core** |

#### `plan_input_resolver` dual path

```
if step_1.execution_mode == "llm":
    → receive run_text (str) + attachments (file list) from /run payload
    → build LLM prompt from run_text + decoded attachment content
    → pass as natural language context to llm_execution

if step_1.execution_mode == "mcp":
    → receive run_inputs dict (validated against input_contract) from /run payload
    → pass as structured args to mcp_input_resolver (from conductor-core)
```

In both cases inputs arrive from the `/run` endpoint — never inferred automatically from conversation history. Steps 2–N always use upstream artifacts via `depends_on`, same as the existing conductor.

#### RabbitMQ events published

```
step.started         { run_id, step_order, capability_id }
step.discovery_completed  { run_id, step_order, artifacts_staged }
step.enrichment_started   { run_id, step_order, phase }
step.enrichment_completed { run_id, step_order }
step.completed       { run_id, step_order, artifacts_produced, timing_ms }
step.failed          { run_id, step_order, error }
run.completed        { run_id, summary: { new, updated, unchanged, total_ms } }
run.failed           { run_id, failed_step, error }
```

These are consumed by the Planner Service WebSocket handler and pushed to the frontend.

---

## 4. Frontend — Planner Tab

**Tech stack:** React + shadcn + Tailwind CSS (VS Code extension, existing stack)
**Location:** New tab in workspace detail screen alongside Overview, Artifacts, Conversations, Runs, Timeline

### 4.1 Layout

Split-pane inside the Planner tab:
- **Left pane:** Chat thread (planning conversation) → transitions to run log during execution
- **Right pane:** Plan canvas (planning) → execution view (after approval) with Planning/Execution toggle

### 4.2 Screen states

| State | Left pane | Right pane | Bottom bar |
|---|---|---|---|
| `planning` | Chat thread, active input | Plan canvas with step cards + toggles | Revise / Approve & run / Save as pack |
| `awaiting_inputs · structured` | Chat thread (read-only) | Plan canvas (read-only) | — (MCP structured form modal is open) |
| `awaiting_inputs · freetext` | Chat thread (read-only) | Plan canvas (read-only) | — (LLM freetext + upload form modal is open) |
| `executing · discover` | Run log (live) | Execution steps with phase badges | Artifact count / Pause |
| `executing · enrich` | Run log (live) | Steps; running step shows purple enrich badge | Artifact count / Pause |
| `completed` | Run log + planner closing message | Run summary card + all steps done + artifact chips | View artifacts / Re-run |
| `failed` | Run log + planner recovery message | Steps with failed/skipped states | View partial artifacts / Replan |

### 4.3 Input form modal (shown after Approve & run — always)

The input form modal is always shown after the user clicks "Approve & run". The form type depends on the first step's `execution_mode`. Both forms open as a modal overlaying the (blurred) plan canvas.

#### Structured form (MCP mode — `input_form_type: "structured"`)

- Title: "Step 1 requires inputs"
- Sub: capability_id + "mode: mcp"
- Fields: schema-driven from `input_contract` JSON Schema
  - `string` → text input
  - `string · format: uri` → url input
  - `enum` → pill-style radio group
  - `boolean` → toggle switch
  - `file` / `file[]` → drop zone with attached file list
- Pre-filled values shown from `prefilled_inputs` with "✦ Pre-filled from your conversation" notice
- Validation: client-side against JSON Schema before submit; field-level inline errors
- Footer: "Validated against execution.io.input_contract" / Back / Start run →
- Submit: `POST /run` with `{ run_inputs: { ...fieldValues } }`

#### Freetext form (LLM mode — `input_form_type: "freetext"`)

- Title: "Step 1 requires inputs"
- Sub: capability_id + "mode: llm"
- Body:
  - Large textarea: "Describe what you want this step to process…" (required)
  - File upload drop zone: "Attach documents, diagrams, or source files" (optional, multiple)
  - Attached file chips with remove button
- No pre-fill (freetext form opens empty)
- Validation: textarea must not be empty before submit
- Footer: "Your text and files will be passed directly to the AI capability" / Back / Start run →
- Submit: `POST /run` with `{ run_text: "...", attachments: [{ filename, content_base64, mime_type }] }`

### 4.4 Artifact popover

Triggered by clicking an artifact chip on a completed step card.

- Three representation tabs: **Narrative** (amber dot) / **Diagram** (purple dot) / **Data** (blue dot)
- Default tab: Narrative
- Narrative content: `auto:overview` narrative from artifact envelope, audience: developer
- Diagram: Mermaid render (fetch from artifact service)
- Data: syntax-highlighted JSON from artifact data field
- Footer: "Open in Artifacts →" navigates to Artifacts tab filtered to this artifact

### 4.5 WebSocket message types (frontend consumes)

```
{ type: "agent_token", content: str }           # stream planner response
{ type: "plan_updated", plan: Plan }             # full plan replacement
{ type: "step_status", step_order, status, phase, artifacts_produced, timing_ms }
{ type: "run_summary", summary }
{ type: "error", message }
```

---

## 5. Key Design Decisions

See `DECISIONS.md` for full rationale. Summary:

1. **New Planner Service** — not bolted onto capability or conductor service
2. **New Execution Agent** — separate from existing conductor; both share `conductor-core`
3. **Existing conductor untouched** — continues to serve all pack-driven runs
4. **LangGraph MongoDB checkpointer** — planner agent is stateful across turns (session_id = thread_id)
5. **Redis manifest cache** — capability manifest cached; invalidated on capability events
6. **Input form always shown after approval** — MCP first step shows structured schema-driven form; LLM first step shows freetext + file upload form; execution never starts without explicit user input regardless of mode
7. **`input_prefill` heuristic** — planner LLM pre-fills form fields from conversation context
8. **Single WebSocket per session** — drives both chat stream and execution progress
9. **`Save as pack`** — approved plans can be persisted to capability service as new packs (Phase 2)

---

## 6. Out of Scope (this iteration)

- Chat session persistence across browser sessions (stateless per tab open for now)
- Save as pack implementation (UI button present but no-op in iteration 1)
- Sequence diagram optional step execution
- Multi-workspace plan templates
- Plan versioning / diff between plan runs

# ASTRA Intent Feature — Architecture Decision Log

> Decisions made during design. Reference this before making implementation choices
> that touch architecture, service boundaries, or data models.

---

## ADR-001 — New Planner Service, not extension of existing services

**Decision:** Create a standalone `planner-service` FastAPI application.

**Alternatives considered:**
- Extend capability service with planning endpoints
- Extend conductor service with a planning mode

**Rationale:**
- The planner has a fundamentally different lifecycle to capabilities or runs — it is conversational and stateful across multiple HTTP requests
- Keeping it separate means the existing conductor and capability service remain unchanged and stable
- The planner service owns its own MongoDB collection (`planner_sessions`) with no coupling to existing schemas
- Independent scaling — planning is LLM-heavy and latency-sensitive in a different way to execution

---

## ADR-002 — New Execution Agent, separate from existing conductor

**Decision:** Create a new execution agent (LangGraph graph) rather than modifying the existing conductor.

**Alternatives considered:**
- Extend conductor's `input_resolver` to accept a raw plan instead of a pack_id
- Register transient packs in the capability service to satisfy the conductor's contract

**Rationale:**
- The conductor's `input_resolver` is tightly coupled to pack resolution — adding a second code path would create a complex branching node that's hard to test
- Registering transient packs pollutes the pack registry and creates cleanup/lifecycle problems
- The new execution agent's `plan_input_resolver` is a clean, purpose-built replacement for the intent-driven path
- Both agents share `conductor-core` so execution logic is not duplicated

---

## ADR-003 — Extract `conductor-core` shared library

**Decision:** Extract the reusable execution nodes from the conductor into a `libs/conductor-core` Python package.

**Nodes to extract:** `mcp_input_resolver`, `mcp_execution`, `llm_execution`, `diagram_enrichment`, `narrative_enrichment`, `persist_run`

**Nodes that stay in conductor:** `input_resolver`, `capability_executor`

**Rationale:**
- Without extraction, execution logic would be duplicated between the conductor and the new execution agent
- Any bug fix or improvement to MCP execution, diagram enrichment, or narrative generation benefits both paths automatically
- The extracted nodes have no dependency on pack concepts — they operate on capabilities and artifacts only

**Implementation note:** This is the first task to complete. It is purely structural — no behaviour change. The existing conductor imports from `conductor-core` after extraction and behaves identically.

---

## ADR-004 — LangGraph MongoDB checkpointer for Planner Agent state

**Decision:** Use LangGraph's built-in checkpointer pattern with MongoDB as the backend. `session_id` is the LangGraph thread_id.

**Rationale:**
- The planner conversation is multi-turn — the graph must pause after generating a response and resume when the next user message arrives
- In-memory state would be lost on service restart or pod re-scheduling
- MongoDB is already the primary store; no new infrastructure
- LangGraph's checkpointer is the standard pattern for human-in-the-loop graphs

---

## ADR-005 — Redis capability manifest cache

**Decision:** Cache a flattened capability manifest (id, name, description, tags, produces_kinds, execution.mode) in Redis. Invalidate on `capability.created` / `capability.updated` RabbitMQ events.

**Rationale:**
- The planner LLM needs the full capability catalog as context on every planning request
- Fetching from MongoDB on every request adds latency and load to the capability service
- The capability registry changes infrequently — cache hit rate will be very high
- The flattened manifest is small (typically 5–20KB) and fits comfortably in LLM context windows

**Cache key:** `astra:capability_manifest`
**TTL:** 1 hour (as a safety net; primary invalidation is event-driven)

---

## ADR-006 — Only step 1 has an input_contract form

**Decision:** The MCP input form modal is only shown for the first step of a plan.

**Rationale:**
- The first step is the data ingestion step — it brings external context into the workspace
- Steps 2–N always consume upstream artifacts via `depends_on` — their inputs are resolved automatically by `mcp_input_resolver` from the artifact store, exactly as in the existing conductor
- Showing forms mid-execution for later steps would break the fire-and-forget execution UX and is not needed given the `depends_on` resolution pattern

---

## ADR-007 — Single WebSocket per session drives both chat and execution

**Decision:** One WebSocket connection (`/planner/sessions/{id}/stream`) delivers all real-time updates: planner agent tokens, plan mutations, and execution step events.

**Rationale:**
- Simpler frontend connection management — one reconnect strategy, one auth token
- Execution events flow through the Planner Service (which subscribes to RabbitMQ step events from the execution agent) — the frontend does not need a separate connection to the execution agent
- Message type field (`type: "agent_token" | "plan_updated" | "step_status" | "run_summary"`) allows the frontend to route updates to the correct pane

---

## ADR-008 — Existing conductor is not modified

**Decision:** The existing conductor service continues to operate exactly as before, serving all pack-driven runs for RAINA, Neozeta, and SABA.

**Rationale:**
- Zero regression risk to production pack-driven workflows
- After `conductor-core` extraction, the conductor simply imports from the shared library — its external API and behaviour are unchanged
- New intent-driven runs go through the new execution agent only

---

## ADR-009 — `input_prefill` heuristic for MCP form pre-population

**Decision:** After assembling the plan, if step 1 is MCP mode, the planner LLM makes a best-effort attempt to pre-fill `run_inputs` from the conversation history.

**Rationale:**
- Users often state relevant details (repo URLs, branch names, file paths) in their natural language intent
- Re-entering this information in a form is friction — pre-filling reduces it
- The pre-fill is advisory (shown with a notice); the user reviews and corrects before submitting
- If the LLM produces a wrong pre-fill, it is immediately visible and correctable in the form

**Implementation note:** This runs as part of `plan_builder` node, not as a separate LLM call — it is appended to the `plan_builder` prompt when the first step is MCP mode.

---

## ADR-010 — polyllm + ConfigForge for all LLM calls in new services

**Decision:** All LLM calls in the Planner Service and Execution Agent use polyllm with ConfigForge references, consistent with the existing conductor.

**New env vars:**
- `PLANNER_LLM_CONFIG_REF` — used by planner agent nodes (intent_resolver, capability_selector, plan_builder, clarification)

**Supported providers (via polyllm):** `openai`, `google_genai`, `bedrock`, `google_vertexai`

**Rationale:** Consistency with existing pattern. Provider details and API keys never appear in code or capability definitions.

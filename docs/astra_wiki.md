# ASTRA Framework Overview

## Introduction

**ASTRA** (Agentic System for traceable reasoning and artifacts.) is a composable framework for structured intelligence—where artifact kinds, capabilities and capability packs come together to define, extend, and orchestrate what artifacts a platform can produce. It enables systems like Raina and Zeta to dynamically evolve by simply adding new artifact kinds, capabilities and capability packs, which are then executed and harmonized by the runtime to generate consistent, traceable, and domain-specific outcomes.

## Core constituents of the framework

### Artifact-Kind — Definition

An artifact-kind is a first-class declarative template in ASTRA that defines what type of knowledge a platform can produce. It acts as the canonical contract describing the shape, semantics, and representations of an artifact—whether it comes from legacy analysis, architecture discovery, agile authoring, data engineering, or any other domain.

#### Different ASTRA-powered platforms produce different families of artifacts:

- **Neozeta** → learning artifacts (application workflows, business entities, data dictionary)

- **RAINA** → architectural artifacts (service boundaries, domain models, APIs)

- **SABA** → agile artifacts (epics, features, user stories, tasks)

Across all platforms, the unit of output—the artifact—is governed by artifact-kinds.

#### What an artifact-kind is

An artifact-kind is a declaration that tells ASTRA:

*“Here is the artifact this platform should be able to produce, what it must look like, how it should be visualized, how AI or tools should generate it, and what it logically depends on.”*

| Property | Purpose | Why it matters |
|---|---|---|
| **`_id`** | Globally unique identifier (`cam.<category>.<kind>`). | Anchors every instance of the artifact to a canonical meaning and allows tools across services to talk about the same concept consistently.Follows a heirarchical naming convention described above|
| **`title`**, **`category`**, **`aliases`**, **`status`** | Human‑friendly metadata and lifecycle state (active/deprecated/experimental). | Improves discoverability and UX; status guides producers and consumers on whether the kind should be used. |
| **`schema_versions.json_schema`** | Represents the shape of the artifact. Defines the exact structure and required fields of the artifact. Enables strict validation, diffing, merging, and deterministic generation. | Enforces structure, enables reproducible generation, supports schema evolution and interop with external formats|
| **`schema_versions.prompt`** | Canonical prompt contract *for agents that generate this kind*. | **repeatability.** The same inputs yield stable artifacts; audits can reconstruct how an artifact was generated. |
| **`schema_versions.depends_on`** | Declares upstream kinds needed to generate this kind. | Enables graph‑based orchestration and incremental recomputation. |
| **`schema_versions.diagram_recipes`** | An optional collection of embedded diagram definitions associated with the artifact. Each entry represents one visual interpretation of the artifact (e.g., flowchart, sequence diagram, mindmap, ER diagram). | Diagrams provide human-friendly visualization of structured artifacts, but remain traceable, versioned, and auditable in the same way as textual data. They bridge the gap 		between machine-validated structure and human comprehension, while preserving lineage and reproducibility. |
| **`schema_versions.narratives_spec`** | An optional collection of embedded human-readable narratives associated with the artifact. Each entry provides a textual explanation of the artifact’s meaning, usage, and context, derived from the structured data. | Narratives provide deeper, human-readable explanations of structured artifacts, tailored to different audiences, and serve as a complement to diagrams and raw JSON. They 		improve comprehension, traceability, and communication across teams. |

#### Why artifact-kinds matter

Artifact-kinds are the foundation of ASTRA’s extensibility:

- They let platforms add brand-new types of outputs without changing any platform code.

- They provide a machine-readable, versioned catalog of all knowledge the platform can generate.

- They allow the AI Agents to orchestrate generation deterministically using dependency ordering.

- They enforce consistency across JSON, diagrams, narratives, and downstream generators.

- They ensure artifacts are traceable, versioned, diffable, and governable across runs.

In short:

***To introduce a new type of output in any ASTRA-powered platform, you simply declare a new artifact-kind—no UI changes, no backend changes, no workflow changes. ASTRA takes care of the rest.***

#### Naming Convention

Artifact-kinds follow a simple, hierarchical naming pattern:

##### cam.<category>.<name>

Where:

**cam** → Canonical Artifact Model. The name always begins with cam, which designates it as an artifact-kind

**category** → The middle segment represents the domain, technology, or functional group the artifact-kind belongs to.This is almost always a noun, such as agile, architecture, data, workflow

**name** → specific artifact type (e.g., user_story, service_contract, entity, workflow)

### Capabilities — Definition

A **Capability** is a declarative, globally addressable unit of execution that defines what it produces, what inputs it accepts, and how it must be executed. Each capability is a self-contained contract describing its execution mode (MCP or LLM), transport details, authentication, validation rules, and output artifact kinds.

Crucially, a capability is the core mechanism through which new features and behaviors can be added to any ASTRA-powered platform without modifying the platform itself. By simply registering a new capability, a platform instantly becomes capable of orchestrating new workflows, integrating new tools, and producing new artifact kinds. **Capability**enables the AI agents to deterministically interpret and execute the capability’s declaration. Capabilities therefore transform platforms from hard-coded systems into extensible, capability-driven systems.

| Property | Description | Why it matters |
|---|---|---|
| **`id`** | Stable identifier such as `cap.cobol.copybook.parse`. | Used by playbooks to reference the capability and by the conductor to dispatch the correct execution|
| **`name`** | Human‑readable name. | Improves UX in UIs and logs and helps non‑experts understand what the capability does|
| **`description`** | Optional summary of the capability. | Documents the purpose of the capability and appears in search results. |
| **`tags`** | List of strings. | Used for grouping and searching capabilities (e.g., by language, domain or category). |
| **`parameters_schema`** | JSON Schema describing top‑level parameters distinct from execution input. | Enables validation and UI scaffolding for dynamic parameters provided by the user. |
| **`produces_kinds`** | Array of artifact kind ids that may be produced. | Guides the agent on what to expect and informs downstream consumers about resulting artifacts|
| **`agent`** | Optional agent identifier. | Associates the capability with a specific model or agent for LLM execution. |
| **`execution`** | Either an `McpExecution` or `LlmExecution` structure. | Declares the mode (`mcp` or `llm`) and contains transport configuration, the tool name, and (for LLM mode) the LLM config reference.|

Important sub‑models used within `execution` include:

- **Execution modes:**
  - `McpExecution` declares the transport (HTTP/STDIO) and a single `tool_name` string identifying the MCP tool to invoke. Input schema is **not** stored in the capability — it is discovered live at runtime by calling `tools/list` on the MCP server. This keeps the capability declaration minimal and always in sync with the actual server.
  - `LlmExecution` references an LLM configuration via a `llm_config_ref` — a ConfigForge canonical reference string (e.g., `"dev.llm.openai.fast"`) — and optionally declares structured I/O. The conductor resolves this reference at runtime to obtain the appropriate LLM client, enabling per-capability LLM configuration without embedding provider details or secrets in the capability definition.

#### Naming Convention

Capabilities in ASTRA follow a three-part hierarchical naming convention:

"cap.<group>.<action>"

##### cap — The namespace prefix
The name always begins with cap, which designates it as a Capability—a declarative, executable unit in the ASTRA ecosystem.


##### <group> — Domain or functional grouping (a noun)

The middle segment represents the domain, technology, or functional group the capability belongs to. This is almost always a noun, such as cobol, jcl, java, agile, data etc.

##### <action> — The operation performed (a verb)

The final segment is the actual capability, describing what it does—typically an action or verb, such as parse, generate, extract, validate, discover etc.

This makes capability names self-describing and semantically meaningful.

### Capability Pack — Definition

A Capability Pack is a versioned, goal-oriented bundle of capabilities that organizes and orchestrates ASTRA’s capabilities to solve a specific problem or intention—such as learning from a legacy application (Neozeta), discovering an application’s architecture (RAINA), or authoring agile outputs (SABA).

Where individual capabilities are atomic units of execution, a capability pack is the composed solution—a declarative specification of:

- What capabilities should run
- In what order
- Using what inputs
- To achieve what deterministic outcome

***It transforms the raw “capability library” of ASTRA into a purpose-driven workflow.***

#### Why Capability Packs Matter?

A capability pack provides:

1. A deterministic intention / goal
    The pack is the declaration of purpose:

    ***“Run these capabilities in this defined way to achieve this specific outcome.”***

    This is what powers platforms such as:

    **Neozeta** → goal: understand a legacy application

    **RAINA** → goal: discover architecture

    **SABA** → goal: author agile artifacts

    Without packs, a platform would need hard-coded workflows.
    With packs, the platform becomes dynamic, declarative, and extensible.

2. A composition layer over capabilities
    Capabilities define what can be done. Packs define how they come together.

    A pack selects a subset of the capabilities registry:
     - ***“These are the capabilities required for this type of solution.”***
  
    This allows ASTRA to offer plug-and-play modularity:
     - Add a new capability → include it in a pack → platform instantly gains new functionality
     - Introduce a new playbook version → platform now has a new workflow variant
     - Change execution order → change the system’s behavior without touching application code
  
3. A stable execution contract
    Each pack references a PackInput—a reusable JSON Schema that defines:
     - what data the user must supply
     - how UIs should render the input form
     - what validation constraints apply

    This decouples data collection from workflow logic, keeping the platform stable even as packs evolve.

#### What a Capability Pack Declares

A capability pack contains:

| Property | Description |
|---|---|
| `key` / `version` | Identifies the pack and its semantic version. |
| `title`, `description` | Human‑readable metadata. |
| `pack_input_id` | Optional reference to a PackInput that defines required inputs. |
| `capability_ids` | List of capabilities used in the pack. |
| `agent_capability_ids` | Extra capabilities available to the conductor for post-processing enrichment (e.g., diagram generation via `cap.diagram.mermaid`). These are not part of any playbook step but are invoked automatically after each discovery phase. |
| `playbooks` | One or more playbooks, each containing ordered **steps**. Each step references a capability id and provides parameters. |
| `status` | `draft`, `published` or `archived`.  Publishing locks the pack and makes it available to runs|
    
#### Playbooks: The Execution Blueprint

Inside a pack, playbooks describe how capabilities run:
 - Each playbook contains ordered steps
 - Each step references a capability
 - Each step may include parameters, hints, or conditional logic

The AI Agent interprets this blueprint, carrying out:
 - capability execution
 - dependency resolution
 - enrichment steps
 - artifact persistence
 - event publishing

This ensures reproducible, deterministic runs across environments and platforms.

### Putting It All Together

In ASTRA’s architecture:

- Artifact-kinds define what can be produced
- Capabilities define how to produce them
- Capability Packs define why and when to produce them

A capability pack is therefore the strategic layer on top of ASTRA’s primitives:

 ***"It transforms a library of discrete capabilities into an intentional, orchestrated, end-to-end solution—without changing the platform’s code."***

## Advantages and Usefulness of ASTRA

ASTRA provides a declarative, extensible, and deterministic foundation for platforms that generate structured knowledge—unlocking several major benefits:

1. Declarative extensibility (no platform changes required)
   ASTRA allows platforms to grow simply by declaring new artifact-kinds or capabilities, without modifying backend logic, UIs, or pipeline code.

   - Add a new artifact-kind → the platform can now produce a new type of output

   - Add a new capability → new tool/LLM functionality instantly becomes available

   - Add/update a capability pack → platform gains new workflows or intentions

   This creates plug-and-play evolution across all ASTRA-powered systems like Neozeta, RAINA, and SABA.

2. Goal-driven orchestration through capability packs
   
   ASTRA converts a large capability library into intention-based solutions:

    - “Learn a legacy system” (Neozeta)

    - “Discover architecture” (RAINA)

    - “Author agile artifacts” (SABA)

   Capability packs provide deterministic, purpose-driven workflows built from smaller capability units. This turns ASTRA into a problem-solving engine, not just a tool host.

3. Normalization and structured knowledge representation

   ASTRA enforces strong structure using artifact-kinds:

   - canonical IDs

   - strict JSON Schemas

   - versioned definitions

   - natural identity keys

   - diagram + narrative specifications

   This guarantees predictability, prevents schema drift, and enables stable downstream consumers (search, diff, diagrams, codegen).

4. Traceable, auditable, reproducible execution

   Every artifact produced by ASTRA has full provenance:

   - which capability ran

   - with which inputs

   - using which tool configuration

   - via which playbook step

   - at what time

   Runs are reproducible and debuggable, enabling deterministic reasoning and meeting enterprise audit requirements.

5. Composable, dependency-aware pipelines

   Through:

   - depends_on relationships in artifact-kinds

   - ordered playbooks in capability packs

   - LangGraph-based orchestration in the conductor-service

   ASTRA supports graph-based incremental execution.
   Only steps affected by input changes are recomputed, enabling efficient, intelligent recomposition of outputs.

6. Governance, compliance, and versioning

   ASTRA embeds governance naturally:

   - retention policies

   - masking & visibility rules

   - promotion gates

   - full version history of artifacts

   - optimistic concurrency (ETags)

   - lifecycle states for capabilities, packs, and kinds

   This makes it suitable for regulated, enterprise-grade environments.

7. Rich, multi-modal knowledge output

   Artifacts can include:

   - diagrams (Mermaid, PlantUML, etc.)

   - narratives (developer view, architect view, business view)

   - structured JSON

   - cross-linked dependencies

   Enrichment capabilities allow ASTRA to transform structured data into human-friendly representations automatically.

8. Multi-modal execution (MCP + LLM)

   Capabilities support:

   - Machine-Callable Tools (MCP) for precise, deterministic outputs

   - LLM execution for intelligent inference, summarization, or discovery

   - hybrid workflows that combine the strengths of both

   This makes ASTRA equally comfortable with hard-coded tools, AI reasoning, or both in combination.

9. Platform-neutral foundation

   ASTRA is not tied to a domain.

   It can power:

   - legacy modernization

   - architecture design

   - agile authoring

   - data engineering

   - security modeling

   - workflow discovery

   - API analysis

   - and many other problem spaces

   Any new domain becomes first-class simply by declaring new artifact-kinds, capabilities, and packs.

10. Future-proof evolution of knowledge systems

    Because ASTRA is fully declarative:

    - Platforms evolve without rewrites

    - Knowledge models evolve without migrations

    - Execution logic evolves without orchestration changes

    This positions ASTRA as a long-lived foundation for building intelligent, adaptive platforms.

## Services

ASTRA is composed of micro‑services that communicate over HTTP and RabbitMQ.  Each service has a well‑defined responsibility and can scale independently.

### Artifact Service

The artifact service is a pure **kind-registry and schema service** (port **9020**). It exposes a REST API with the following features:

- **Kind registry:** List, retrieve, adapt and validate artifact kinds, fetch prompt contracts, and perform admin operations such as upsert/patch/delete of kinds. A category API allows creating, updating and deleting high‑level categories (domain, data, code, etc.).

- **Build envelope** (`POST /registry/build-envelope`): Validates an incoming artifact payload, runs schema migration and adaptation, and returns a fully computed envelope with `natural_key`, `fingerprint`, `schema_version`, and `category`. Called by the workspace-manager-service before persisting any artifact.

- **Seeded at startup** with built-in kind definitions for all registered domains.

- **No RabbitMQ dependency** — the artifact service no longer consumes workspace lifecycle events. All messaging and runtime artifact storage concerns live in the workspace-manager-service.

### Workspace Manager Service

The workspace-manager-service (port **9027**) owns all runtime workspace artifact storage and workspace lifecycle management.  It exposes a REST API with the following features:

- **Create/upsert artifacts:** The `/artifact/{workspace_id}` endpoint delegates envelope computation (natural key, fingerprint, schema validation) to the artifact-service via `POST /registry/build-envelope`, then calls the data access layer to insert or update the artifact. When a new artifact is inserted or updated, the service publishes corresponding events for downstream consumers.

- **Batch upsert:** Clients can upsert multiple artifacts in one request; the service returns a summary of inserts, updates and no‑ops along with per‑item results.

- **List and retrieve:** The service lists artifacts with optional filters (kind, name prefix, deletion flag) and pagination. A workspace’s parent document (containing all artifacts) can be fetched, and deltas between runs (added, changed, unchanged artifacts) can be computed.

- **Replace and patch:** A PUT request can replace the data/diagrams/narratives of a specific artifact, guarded by an ETag to ensure optimistic concurrency. PATCH requests use JSON Patch to partially update the `data` field; the service records patch history and emits events.

- **History and deletion:** Endpoints exist to retrieve the version history of an artifact and to soft‑delete it (marking `deleted_at`). Deleted artifacts are excluded from normal listings unless explicitly requested.

- **Workspace lifecycle:** Consumes `platform.workspace.created`, `platform.workspace.updated`, and `platform.workspace.deleted` events from RabbitMQ to maintain the workspace parent document in MongoDB.

### Capability Service

The capability service manages capabilities, pack inputs and packs.  Key responsibilities include:

- **Capability CRUD and search:** Clients can create a `GlobalCapability`, retrieve by id, update, delete or search by tag, produced kind or execution mode.  Batch fetching of capabilities by id is supported.

- **Pack management:** The `/capability/packs` endpoint allows creating, listing, retrieving, updating and deleting capability packs.  Packs can be published, which marks them immutable and ready for execution.

- **Pack inputs:** `/capability/pack‑inputs` provides CRUD operations for PackInput documents.  A special endpoint resolves the effective input contract for a playbook using the rules described earlier.

- **Resolved pack view:** Clients can fetch a resolved view of a pack where capability ids are resolved to full capability documents, agent capabilities are included, and playbook steps are annotated with the mode and produced kinds.  This view is used by the conductor to orchestrate runs.

Internally, the capability service uses a data access layer to store documents in MongoDB and publishes events on creation or update.  The `CapabilityService`, `PackService` and `PackInputService` implement business logic, such as validating semver versions and ensuring referenced capabilities exist in a pack.  Packs can include **agent capabilities** (e.g., diagram generators) that are not part of any playbook step but are available to the conductor for enrichment.

### conductor-core (Shared Execution Library)

`libs/conductor-core` is a shared Python library that contains all of the core execution logic used by both the conductor-service and the planner-service.  Extracting this logic into a library ensures that the two services stay in lockstep on execution behaviour without duplicating code.

The library is structured into four top-level packages:

- **`conductor_core.models`** — shared Pydantic models: `PlaybookRun`, `StepState`, `RunStrategy`, `RunStatus`, `StepStatus`, `StepAudit`, `ToolCallAudit`, `ArtifactEnvelope`, `ArtifactProvenance`, `StartRunRequest`, `LLMConfig` and supporting types.

- **`conductor_core.nodes`** — the six reusable LangGraph execution nodes (see below).  Each node is a factory function that closes over its dependencies (repository, LLM, artifact client) and returns an async callable.

- **`conductor_core.llm`** — LLM abstraction layer: `AgentLLM` protocol, `ExecLLM` protocol, polyllm-backed implementations (`PolyllmAgentLLM`, `PolyllmExecLLM`), and factory functions `get_agent_llm()` and `build_exec_llm()` that resolve a ConfigForge ref to an LLM client.

- **`conductor_core.mcp`** — MCP transport client (`MCPConnection`, `MCPTransportConfig`) and JSON utilities.

- **`conductor_core.protocols`** — structural `Protocol` definitions for `RunRepositoryProtocol`, `ArtifactServiceClientProtocol` (registry reads: `get_kind`, `get_kind_schema`), `WorkspaceManagerClientProtocol` (artifact writes: `upsert_batch`), and `EventPublisherProtocol`.  Any object whose async methods structurally match these protocols can be injected into a node factory — this is what allows both conductor-service and planner-service to supply their own implementations without inheriting from a base class.

- **`conductor_core.artifacts`** — `ArtifactAdapter` utilities for normalising staged artifacts into `ArtifactEnvelope` instances before persistence.

#### Shared Execution Nodes

All six nodes follow the same pattern: a factory function accepts dependencies (typed via `Protocol`) and returns an async LangGraph node.  Each node returns a `Command(goto=..., update={...})` that drives the graph to the next node.

| Node | Description |
|---|---|
| `capability_executor_node` | Central routing coordinator.  Manages step index, three-phase transitions (`discover → enrich → narrative_enrich`), publishes step lifecycle events via `EventPublisher`, and drives the graph to `persist_run` on completion or error. |
| `mcp_input_resolver_node` | Builds MCP tool arguments. Reads `tool_name` from `capability.execution.tool_name`, then calls `tools/list` on the MCP server to discover the live input JSON schema (cached in `state["discovered_tools"]` for the duration of the run). Step 0 maps pack inputs to tool args; steps 1+ use LLM + upstream artifact context. Validates against the discovered schema with one LLM repair attempt. |
| `mcp_execution_node` | Connects to an MCP server (HTTP or STDIO transport), invokes the tool identified by `tool_name`, handles retries, polling, and pagination. Uses `discovered_tools` from state to detect async status tools without a second `tools/list` call. Stages produced artifacts with provenance metadata. |
| `llm_execution_node` | Executes LLM-based capabilities.  Resolves `llm_config_ref` from ConfigForge per capability, builds a prompt from the kind schema + prompt contract + upstream artifacts, calls the LLM, validates JSON output against the artifact kind schema, stages the result. |
| `diagram_enrichment_node` | Post-processing: connects to the diagram MCP server, calls `diagram.mermaid.generate` for each artifact produced in the current step, attaches the resulting Mermaid diagrams.  Reads transport config from `agent_capabilities_map["cap.diagram.mermaid"]`.  Failures are non-fatal. |
| `narrative_enrichment_node` | Post-processing: for each artifact produced in the current step, reads the kind’s `narratives_spec` and calls the agent LLM to generate a Markdown narrative (`id: "auto:overview"`, `audience: "developer"`).  Failures are non-fatal. |
| `persist_run_node` | Finalises the run.  Normalises `staged_artifacts` into `ArtifactEnvelope`s, calls `workspace-manager-service /artifact/{workspace_id}/upsert-batch` (baseline strategy) or stores in `run_artifacts` (delta strategy), records run summary and final status. |

#### Three-Phase Step Execution

Each playbook step is executed across three phases, all coordinated by `capability_executor_node`:

```
discover  →  enrich (diagram)  →  narrative_enrich  →  (advance to next step)
```

- **discover:** MCP or LLM execution.  Produces and stages raw artifacts.
- **enrich:** `diagram_enrichment_node` attaches diagrams to each artifact produced in this step.
- **narrative_enrich:** `narrative_enrichment_node` attaches human-readable narratives.

Enrichment failures in either phase are non-fatal — the run continues.  A discovery failure terminates the run immediately and routes to `persist_run`.

#### Protocol-Based Dependency Injection

Nodes depend on `RunRepositoryProtocol`, `ArtifactServiceClientProtocol`, `WorkspaceManagerClientProtocol`, and `EventPublisherProtocol` rather than concrete classes.  The conductor-service and planner-service each supply their own implementations.  `persist_run_node` requires both `art_client` (registry reads) and `workspace_client` (artifact writes) as separate required parameters — there is no fallback.  This means conductor-core has no import-time dependency on either service’s codebase.

---

### Conductor Service (Agent Runtime)

The conductor service orchestrates **runs** of a capability pack’s playbook.  It exposes an API to start a run and reports progress via events.  Its execution nodes are all provided by `libs/conductor-core`.

- **Run API:** The `/runs/start` endpoint accepts a `StartRunRequest` containing the workspace id, pack id, playbook id, inputs and optional title/description.  It immediately records a `PlaybookRun` with status `created` and schedules the run as a background task.  The response includes the run id and current status.

- **Run repository:** Abstracts database operations for runs and step states.  It updates step statuses (pending, running, completed, failed) and persists audits, logs and summaries.  Implements `RunRepositoryProtocol` so it can be injected directly into conductor-core nodes.

- **Clients:** The conductor maintains three service clients: `CapabilityServiceClient` (fetches resolved packs and capabilities), `ArtifactServiceClient` (kind registry reads — implements `ArtifactServiceClientProtocol`), and `WorkspaceManagerClient` (artifact storage writes — implements `WorkspaceManagerClientProtocol`). The split ensures registry queries go to artifact-service (port 9020) and artifact persistence goes to workspace-manager-service (port 9027).

- **LLM Architecture:** The conductor uses **polyllm** — a unified LLM abstraction layer from `conductor_core.llm` — to decouple the runtime from any specific LLM provider. All LLM configuration is stored externally in **ConfigForge** and referenced by a canonical string (e.g., `"dev.llm.bedrock.explicit-creds"`). The conductor maintains two distinct LLM roles:

  - **Agent LLM** (`CONDUCTOR_LLM_CONFIG_REF`) — used by `mcp_input_resolver` (to semantically map inputs to MCP tool arguments) and `narrative_enrichment` (to generate artifact narratives). Configured via the `CONDUCTOR_LLM_CONFIG_REF` environment variable.

  - **Execution LLM** — used by `llm_execution` when a capability declares `execution.mode = "llm"`. Each such capability specifies its own `llm_config_ref`; the conductor fetches the corresponding LLM client from ConfigForge at execution time. If the `OVERRIDE_CAPABILITY_LLM=1` flag is set, all capabilities fall back to the conductor’s own agent LLM regardless of their declared `llm_config_ref`.

  polyllm supports `openai`, `google_genai`, `bedrock`, and `google_vertexai` as providers. Provider selection, API keys, and sampling parameters are all stored in ConfigForge profiles — never hardcoded in capability definitions or service configuration.

- **LangGraph‑based agent:** The conductor builds a `StateGraph` using LangGraph and populates it with nodes from `conductor_core.nodes`.  The graph starts at `input_resolver` (conductor-service–specific) and then delegates to the shared nodes.  Each node returns a `Command` indicating the next node and a state update.  The graph state includes a `discovered_tools` map (`cap_id → {tool_name: schema}`) that is populated by `mcp_input_resolver` on first use and reused by `mcp_execution` for the same capability within the same run, avoiding redundant `tools/list` calls.  For the full description of each execution node, see the **conductor-core** section above.

The conductor advances through three phases for each step: `discover` (MCP or LLM execution gathers raw artifacts), `enrich` (diagram_enrichment generates Mermaid diagrams), and `narrative_enrich` (narrative_enrichment generates Markdown explanations via the agent LLM).  Errors in either enrichment phase are non‑fatal and the run continues; errors during discovery immediately trigger `persist_run` with a failed status.  When all steps complete or inputs are invalid, the conductor calls `persist_run` and publishes final events.

---

### Planner Service (Intent-Driven Planning and Execution)

The planner-service is the entry point for intent-driven capability runs.  Unlike the conductor-service — which requires a pre-configured capability pack and explicit inputs — the planner-service accepts a natural-language user intent, autonomously selects the right capabilities, assembles an ordered plan, presents it for user review, and then executes it using the same `conductor_core` execution nodes.

For a detailed implementation reference, see [docs/planner_service.md](planner_service.md).

#### Two Agents, One Service

The planner-service runs two distinct LangGraph agents:

1. **Planner Agent** (`planner_graph.py`) — a conversational, multi-turn graph that processes each user message.  It extracts intent, selects capabilities from the registry, and builds a plan with LLM-prefilled inputs.  Runs on demand for each user message; not checkpointed.

2. **Execution Agent** (`execution_graph.py`) — a single-pass execution graph triggered by `POST /run`.  It converts the approved session plan into a conductor-core–compatible pack/playbook structure and runs it through the shared execution nodes (`capability_executor`, `mcp_execution`, `llm_execution`, `diagram_enrichment`, `narrative_enrichment`, `persist_run`).

#### Intent-to-Plan Flow

```
User message
    ↓ session_init (load session + history)
    ↓ intent_resolver (LLM: extract structured intent)
    ↓ capability_selector (LLM: match capabilities from registry)
    ↓ plan_builder (LLM: build ordered steps + prefill run_inputs)
    ↓
  confidence ≥ 0.65?
    yes → plan_approved (save plan to MongoDB) → return plan to user
    no  → clarification (ask user a question) → wait for next message
```

#### Plan-Approve-Run Flow (ADR-006)

ASTRA uses a deliberate two-step flow to ensure users review and confirm inputs before execution begins:

1. **`POST /plan/approve`** — locks the plan, inspects the first enabled step’s capability to determine whether the input form should be `"structured"` (MCP) or `"freetext"` (LLM). For MCP capabilities, it connects to the MCP server and calls `tools/list` to retrieve the live input JSON schema, returning it as `input_contract: { json_schema, schema_guide }` alongside `prefilled_inputs` (LLM-guessed values from planning time). The frontend renders a schema-driven form directly from this response. Does **not** start execution.

2. **`POST /run`** — accepts the user-confirmed `run_inputs`, sets status to `executing`, and schedules the execution agent as a background task.

#### Capability Manifest Cache

The planner-service maintains its own capability manifest cache (Redis-backed with in-memory fallback) that is separate from the conductor-service’s copy.  It is warmed up at startup and kept current via a RabbitMQ consumer that reacts to `capability.updated` / `capability.created` events.  The cache serves both the planner graph (for capability selection) and the execution graph (for step resolution).

#### Event Channels

The planner-service uses two complementary channels for real-time events:

| Channel | Scope | Events |
|---|---|---|
| Direct WebSocket `/ws/sessions/{id}` | Per-session, session-private | Planner chat responses, plan updates, high-level execution lifecycle (`execution.started`, `execution.completed`, `execution.run_created`) |
| RabbitMQ → notification-service → WebSocket `/ws` | Workspace-broadcast | Step-level progress events (`step.started`, `step.completed`, etc.) published by `capability_executor_node` |

Session-private chat events (`planner.response`, `planner.error`) are delivered exclusively on the direct WebSocket and are never published to RabbitMQ, preventing duplicate delivery to frontend clients that subscribe to both channels.

---

### Capability Onboarding Service

The capability-onboarding-service is a stateless HTTP service (port **9026**) that provides the backend for the **MCP Capability Onboarding Wizard** — a 4-step UI that guides users through connecting an MCP server, selecting a tool, reviewing LLM-inferred metadata, and registering the result as a live ASTRA capability.

Unlike other ASTRA services it has **no database, no message broker, and no persistent state**. The entire wizard state travels as a single progressive JSON document (`CapabilityOnboardingDoc`) passed between the frontend and the two backend endpoints.

#### Why it exists

Registering a new MCP server as an ASTRA capability traditionally required manual construction of `GlobalCapabilityCreate` payloads, deep knowledge of the `cap.<group>.<action>` and `cam.<category>.<name>` naming conventions, and separate API calls to capability-service and artifact-service. The onboarding service automates all of this:

1. Connects to the MCP server and discovers its tools via `tools/list`
2. Uses an LLM (via polyllm + ConfigForge) to infer a complete capability metadata block from the tool name, description, and input schema
3. Lets the user review and edit the inferred metadata before committing
4. Registers the capability (and any new artifact kinds) in the appropriate services

#### UI Flow and API Mapping

```
Step 1 — Connect Server     →  POST /onboarding/resolve  (no tool_name)
Step 2 — Select Tool        →  POST /onboarding/resolve  (with tool_name, if multi-tool server)
Step 3 — Review & Edit      →  client-side only (edit doc.inferred in UI)
Step 4 — Register           →  POST /onboarding/register
```

Single-tool servers collapse steps 1 and 2 into one call — the response already has `status="inferred"` with all metadata populated.

#### Progressive Document Model

The `CapabilityOnboardingDoc` is the central data contract:

| Field | Populated by | Purpose |
|---|---|---|
| `server` | Step 1 | MCP server connection config (URL, auth, protocol path) |
| `available_tools` | Step 1 | All tools discovered on the server |
| `selected_tool` | Step 2 | The specific tool the user chose (or auto-selected if only one) |
| `inferred` | Step 2 | LLM-inferred `capability_id`, `capability_name`, `tags`, `group`, `produces_kinds` |
| `status` | Updated by each step | `"discovered"` → `"inferred"` → `"registered"` |
| `registered_capability_id` | Step 4 | The ID written to capability-service |
| `registered_kind_ids` | Step 4 | New artifact kind IDs written to artifact-service |

#### Endpoint: `POST /onboarding/resolve`

Accepts a `ResolveRequest` (server config + optional `tool_name`). Internally:

1. Builds `MCPTransportConfig` from the server config; resolves `AuthSpec` aliases (env-var names) into HTTP headers at call time — bearer, API key, or Basic auth.
2. Handles Docker networking: when `MCP_LOCALHOST_ALIAS` is set (e.g. `host.docker.internal`), rewrites `localhost`/`127.0.0.1` in the MCP URL and injects a `Host` header with the original hostname to prevent 421 responses from MCP servers that validate the `Host` header.
3. Calls `MCPConnection.connect()` → `list_tools()` → `aclose()` using `conductor_core.mcp`.
4. If no `tool_name` and multiple tools exist, returns `status="discovered"` for the UI to show a picker.
5. Otherwise, passes the selected tool's name, description, and full input schema to `LLMInferencer.infer()` and returns `status="inferred"` with all metadata populated.

#### LLM Inference (`LLMInferencer`)

The inferencer uses **polyllm** with the **ConfigForge** pattern (same as conductor-service):

- `CONFIG_FORGE_URL` + `ONBOARDING_LLM_CONFIG_REF` env vars — no raw API keys in service config.
- A structured system prompt enforces naming conventions (`cap.<group>.<action>`, `cam.<category>.<name>`) and valid group/category values.
- The user message contains the tool name, description, and full JSON input schema.
- The LLM must respond with a single JSON object containing `capability_id`, `capability_name`, `description`, `tags`, `group`, and `produces_kinds`.
- Response parsing falls back to markdown fence-stripping before raising a 502.

#### Endpoint: `POST /onboarding/register`

Accepts a `RegisterRequest` (the full `CapabilityOnboardingDoc` with `status="inferred"`, optionally edited by the user). Internally:

1. **Artifact kinds** — for each kind in `inferred.produces_kinds`:
   - `GET /registry/kinds/{kind_id}` on artifact-service → if 200, mark `is_new=False` and add to `kind_ids_existing`.
   - If 404, `POST /registry/kinds` with a minimal open-schema `KindRegistryDoc` (type: object, `additionalProperties: true`). 409 responses are absorbed (kind already exists).
2. **Capability** — builds a `GlobalCapabilityCreate` with `McpExecution(mode="mcp", transport=HTTPTransport(...), tool_name=selected_tool.name)` and `POST`s to `/capability/` on capability-service. A 409 raises a 409 back to the caller ("Capability already registered").
3. Returns `RegisterResponse` with `doc.status="registered"`, `registered_capability_id`, `kind_ids_registered`, and `kind_ids_existing`.

#### Key Design Decisions

- **Stateless by design** — no MongoDB, no RabbitMQ. The doc travels entirely in request/response bodies, keeping the service simple and horizontally scalable.
- **AuthSpec uses env-var aliases, not raw secrets** — `alias_token`, `alias_key`, etc. are environment variable *names*; the service resolves them via `os.getenv` at connection time. Secrets never appear in API payloads.
- **Minimal kind registration** — new artifact kinds are created with an open schema (`additionalProperties: true`) so they can immediately be used by the capability without requiring a full kind definition upfront. Kind authors can refine the schema later.
- **ConfigForge for LLM config** — matching conductor-service, all LLM provider details and API keys are stored in ConfigForge and referenced by a canonical string (`ONBOARDING_LLM_CONFIG_REF`). The service never holds raw LLM credentials.
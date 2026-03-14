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
| **`execution`** | Either an `McpExecution` or `LlmExecution` structure. | Declares the mode (`mcp` or `llm`) and contains detailed transport configuration, tool call specifications, I/O contracts and polling settings|

Important sub‑models used within `execution` include:

- **Execution modes:**
  - `McpExecution` defines transport (HTTP/STDIO), a list of tool calls (with argument schema, retries and streaming flags), discovery policies, connection hints and optional input/output contracts.
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

The artifact service manages persistent storage of artifacts, diagrams and narratives.  It exposes a REST API with the following features:

- **Create/upsert artifacts:** The `/artifact/{workspace_id}` endpoint builds an envelope from the incoming payload, computing the canonical kind id, natural key and fingerprint.  It passes through diagrams and narratives, then calls the data access layer to insert or update the artifact【956177183913673†L45-L74】.  When a new artifact is inserted or updated, the service publishes corresponding events for downstream consumers.

- **Batch upsert:** Clients can upsert multiple artifacts in one request; the service returns a summary of inserts, updates and no‑ops along with per‑item results.

- **List and retrieve:** The service lists artifacts with optional filters (kind, name prefix, deletion flag) and pagination【956177183913673†L294-L317】.  A workspace’s parent document (containing all artifacts) can be fetched, and deltas between runs (added, changed, unchanged artifacts) can be computed.

- **Replace and patch:** A PUT request can replace the data/diagrams/narratives of a specific artifact, guarded by an ETag to ensure optimistic concurrency.  PATCH requests use JSON Patch to partially update the `data` field; the service records patch history and emits events.

- **History and deletion:** Endpoints exist to retrieve the version history of an artifact and to soft‑delete it (marking `deleted_at`).  Deleted artifacts are excluded from normal listings unless explicitly requested.

- **Registry and categories:** The artifact service also provides a **kind registry** API: list, retrieve, adapt and validate artifact kinds, fetch prompt contracts, and perform admin operations such as upsert/patch/delete of kinds【157525849080598†L0-L172】.  A category API allows creating, updating and deleting high‑level categories (domain, data, code, etc.).

### Capability Service

The capability service manages capabilities, pack inputs and packs.  Key responsibilities include:

- **Capability CRUD and search:** Clients can create a `GlobalCapability`, retrieve by id, update, delete or search by tag, produced kind or execution mode.  Batch fetching of capabilities by id is supported.

- **Pack management:** The `/capability/packs` endpoint allows creating, listing, retrieving, updating and deleting capability packs.  Packs can be published, which marks them immutable and ready for execution.

- **Pack inputs:** `/capability/pack‑inputs` provides CRUD operations for PackInput documents.  A special endpoint resolves the effective input contract for a playbook using the rules described earlier.

- **Resolved pack view:** Clients can fetch a resolved view of a pack where capability ids are resolved to full capability documents, agent capabilities are included, and playbook steps are annotated with the mode and produced kinds.  This view is used by the conductor to orchestrate runs.

Internally, the capability service uses a data access layer to store documents in MongoDB and publishes events on creation or update.  The `CapabilityService`, `PackService` and `PackInputService` implement business logic, such as validating semver versions and ensuring referenced capabilities exist in a pack.  Packs can include **agent capabilities** (e.g., diagram generators) that are not part of any playbook step but are available to the conductor for enrichment.

### Conductor Service (Agent Runtime)

The conductor service orchestrates **runs** of a pack’s playbook.  It exposes an API to start a run and reports progress via events.  Its key components are:

- **Run API:** The `/runs/start` endpoint accepts a `StartRunRequest` containing the workspace id, pack id, playbook id, inputs and optional title/description.  It immediately records a `PlaybookRun` with status `created` and schedules the run as a background task.  The response includes the run id and current status.

- **Run repository:** Abstracts database operations for runs and step states.  It updates step statuses (pending, running, completed, failed) and persists audits, logs and summaries.

- **Clients:** The conductor uses clients for the capability and artifact services to fetch packs and store produced artifacts.

- **LLM Architecture:** The conductor uses **polyllm** — a unified LLM abstraction layer — to decouple the runtime from any specific LLM provider. All LLM configuration is stored externally in **ConfigForge** and referenced by a canonical string (e.g., `"dev.llm.bedrock.explicit-creds"`). The conductor maintains two distinct LLM roles:

  - **Agent LLM** (`CONDUCTOR_LLM_CONFIG_REF`) — used by `mcp_input_resolver` (to semantically map inputs to MCP tool arguments) and `narrative_enrichment` (to generate artifact narratives). Configured via the `CONDUCTOR_LLM_CONFIG_REF` environment variable.

  - **Execution LLM** — used by `llm_execution` when a capability declares `execution.mode = "llm"`. Each such capability specifies its own `llm_config_ref`; the conductor fetches the corresponding LLM client from ConfigForge at execution time. If the `OVERRIDE_CAPABILITY_LLM=1` flag is set, all capabilities fall back to the conductor's own agent LLM regardless of their declared `llm_config_ref`.

  polyllm supports `openai`, `google_genai`, `bedrock`, and `google_vertexai` as providers. Provider selection, API keys, and sampling parameters are all stored in ConfigForge profiles — never hardcoded in capability definitions or service configuration.

- **LangGraph‑based agent:** The heart of the conductor is an asynchronous state machine built with **LangGraph**.  The graph defines a state dictionary, nodes (executors) and directed edges representing the run’s workflow.  Each node returns a `Command` indicating the next node to run and an update to the state.  The conductor graph contains the following nodes:

  1. **input_resolver** – resolves the pack and playbook, fetches agent capabilities, validates user inputs against the PackInput JSON Schema and initialises step state.  It emits a `started` event immediately.

  2. **capability_executor** (router) – central coordinator that maintains the step index and phase (`discover`, `enrich`, or `narrative_enrich`).  It decides whether to dispatch to MCP or LLM execution based on the capability mode, whether to perform diagram or narrative enrichment, or whether to finalise the run.  It publishes events for `step.discovery_completed`, `step.enrichment_started`, `step.enrichment_completed`, `step.completed` and handles errors or invalid inputs.

  3. **mcp_input_resolver** – builds arguments for MCP tool calls.  For the first step, it synthesises arguments from the PackInput values and the capability’s execution input schema; for later steps, it also leverages upstream artifacts (filtered by `depends_on`).  The resolver uses an LLM to map input fields semantically and validates the result against JSON Schema.

  4. **mcp_execution** – executes the MCP tool(s) defined in the capability.  It constructs a transport configuration (HTTP/STDIO), handles retries, asynchronous polling, pagination and streaming.  It collects output artifacts using the declared artifacts property (e.g., `artifacts`) and stores them in `state.staged_artifacts` with provenance metadata.

  5. **llm_execution** – executes LLM‑based capabilities.  For each artifact kind declared in `produces_kinds`, it loads the capability's `llm_config_ref` from ConfigForge (or falls back to the conductor's own LLM if `OVERRIDE_CAPABILITY_LLM` is set), builds a prompt from the kind's schema and prompt contract together with upstream artifact dependencies and run inputs, calls the LLM, validates the JSON response against the kind's schema, and stages the produced artifact.  Retries once on failure.

  6. **diagram_enrichment** – first post‑processing stage (`enrich` phase).  After each successful discovery step, if the agent pack includes `cap.diagram.mermaid`, this node calls the diagram generator on each artifact produced in the current step.  It determines the appropriate `view` (e.g., flowchart, sequence) based on the artifact kind’s `diagram_recipes` metadata and attaches returned diagrams.  If no diagram capability is available or no artifacts were produced, enrichment is skipped with a summary.

  7. **narrative_enrichment** – second post‑processing stage (`narrative_enrich` phase), running after diagram enrichment for each step.  For every artifact produced in the current step, it reads the artifact kind’s `narratives_spec` (format, max length, locale) and the kind’s prompt context, then calls the conductor’s agent LLM to generate a human‑readable Markdown explanation.  The result is attached to the artifact as a narrative entry with `id: "auto:overview"` and `audience: "developer"`.  If `narratives_spec` is absent for a kind the artifact is skipped.  Enrichment failures are non‑fatal; the run continues with partial narratives.

  8. **persist_run** – finalises the run.  It normalises staged artifacts into `ArtifactEnvelope`s by deriving identity, schema version and provenance and persists them to the artifact service.  It computes counts of added/changed/unchanged artifacts, writes a run summary and sets the final status (`completed` or `failed`).  This node is idempotent and uses ETags when replacing baseline artifacts.

The conductor advances through three phases for each step: `discover` (MCP or LLM execution gathers raw artifacts), `enrich` (diagram_enrichment generates Mermaid diagrams), and `narrative_enrich` (narrative_enrichment generates Markdown explanations via the agent LLM).  Errors in either enrichment phase are non‑fatal and the run continues; errors during discovery immediately trigger `persist_run` with a failed status.  When all steps complete or inputs are invalid, the conductor calls `persist_run` and publishes final events.
# MCP Server Authoring Guide for ASTRA

This guide is for developers who want to build MCP servers and register them as capabilities in ASTRA.
It covers what ASTRA expects from an MCP server, how to design your tool for clean integration,
and what to avoid.

---

## 1. Tool Design

### One tool, one capability, one artifact kind

ASTRA's registration wizard enforces a 1:1:1 mapping:

```
one MCP tool  →  one ASTRA capability  →  one artifact kind
```

Each tool should do one well-scoped thing and return one type of structured output. If your server
has multiple distinct operations, implement them as separate tools.

**Good:**
```
raina.input.fetch      → fetches and validates a Raina input document
wiki.structure.read    → reads and structures a wiki page
diagram.mermaid.render → generates a Mermaid diagram from a context map
```

**Avoid:** A single "do everything" tool with a `mode` parameter that returns different shapes
depending on the input. ASTRA registers one schema per tool — a shape-shifting tool produces an
unusable schema.

### Lists are fine — all items must be the same kind

ASTRA supports tools that return a list of objects, but all items in the list must conform to the
same registered schema. Do not mix result types in a single list.

---

## 2. Return Types and Output Schema

### Always annotate your return type with a Pydantic model

FastMCP generates the `outputSchema` that ASTRA reads during registration from your Python return
type annotation. A typed Pydantic model produces a rich, accurate schema. A generic type produces
a useless one.

**Do this:**
```python
from pydantic import BaseModel

class RainaInputDoc(BaseModel):
    inputs: InputsBlock

@mcp.tool(name="raina.input.fetch")
async def raina_input_fetch(stories_url: str) -> RainaInputDoc:
    ...
```

**Not this:**
```python
from typing import Any, Dict

@mcp.tool(name="raina.input.fetch")
async def raina_input_fetch(stories_url: str) -> Dict[str, Any]:  # produces: {"type": "object"} — useless
    ...
```

### The output schema drives artifact kind inference

When you connect your server in the registration wizard, ASTRA displays the `outputSchema`
advertised by your tool and feeds it to the LLM to infer an artifact kind schema. A rich,
well-structured output schema produces a high-quality artifact kind with accurate field definitions.
A vague schema requires heavy manual correction.

---

## 3. Output Validation Contract

Once your tool is registered, ASTRA validates every response at runtime against the JSON schema
stored in the artifact kind registry. **Your server must always return output that matches the
schema it declared at registration.**

- If the schema says `inputs.avc` is required, every response must include it.
- If a field is `type: string`, never return an integer.
- If the schema marks `additionalProperties: false`, do not include undeclared fields.

A response that fails schema validation is silently dropped — no artifact is persisted and the
dependent steps in the playbook receive no input. Design your schema carefully and make it match
what you actually return.

### Schema validation policy

ASTRA sets `additional_props_policy` based on whether you provide a schema:

| Situation | Policy | Effect |
|-----------|--------|--------|
| Pydantic model with specific fields | `forbid` | Extra fields in response are rejected |
| No schema / open schema | `allow` | Any fields pass through |

Prefer `forbid` — it makes contract violations visible immediately rather than silently producing
malformed artifacts.

---

## 4. Transport Configuration

ASTRA communicates with your server using the **streamable-http** transport. Configure your server
to listen on HTTP, not stdio.

```python
# In your .env or docker-compose environment:
MCP_TRANSPORT=streamable-http
MCP_HOST=0.0.0.0
MCP_PORT=8003          # pick a port not already in use
MCP_MOUNT_PATH=/mcp    # ASTRA expects the MCP endpoint at /mcp
```

When running in Docker, expose the port and add `host.docker.internal` so the container can reach
services on the Docker host:

```yaml
# docker-compose.yml
ports:
  - "8003:8003"
extra_hosts:
  - "host.docker.internal:host-gateway"
```

The ASTRA registration wizard will need the full URL: `http://localhost:8003/mcp` (from the host)
or `http://host.docker.internal:8003/mcp` (from another container).

---

## 5. Authentication

If your MCP server requires authentication, use ASTRA's alias-based auth system. Never hard-code
credentials in your server or pass raw secrets through the wizard.

The wizard stores an **env var alias name** (not the secret value). At call time, the conductor
service resolves the alias from its environment.

Supported methods:

| Method | Env var alias field | Example |
|--------|--------------------|-|
| Bearer token | `alias_token` | `MY_SERVICE_TOKEN` |
| Basic auth | `alias_user` / `alias_password` | `MY_SVC_USER` / `MY_SVC_PASS` |
| API key (X-API-Key) | `alias_key` | `MY_API_KEY` |

In the wizard, enter the env var **name** (e.g. `MY_SERVICE_TOKEN`), not the value. The conductor
service must have that variable set in its environment.

---

## 6. Error Handling

Return structured errors, not plain exception strings. FastMCP will wrap your exception in an
MCP error response — ASTRA treats tool call errors as step failures and logs them. Do not:

- Swallow errors silently and return empty/null data (ASTRA will persist an empty artifact)
- Return error information in the normal result shape (ASTRA will try to validate it as an artifact)

Raise an exception clearly; ASTRA will mark the step as failed and surface the message.

---

## 7. Registration Walkthrough

After your server is running and accessible:

1. **Connect server** — Enter your server's URL and auth settings.
2. **Inspect tool** — Review the input schema and output schema ASTRA reads from your server.
   If the output schema looks wrong, check your return type annotation.
3. **Review & edit** — The LLM infers a capability ID, name, tags, and an artifact kind with a
   JSON schema derived from your output schema. Verify:
   - Capability ID follows `cap.<group>.<action>` (e.g. `cap.data.fetch_raina_input`)
   - Artifact kind ID follows `cam.<category>.<name>` (e.g. `cam.data.raina_input`)
   - The `json_schema` in the Artifact kind tab accurately reflects your tool's output structure
   - Switch to **json** view to see exactly what will be sent to ASTRA — this is what gets stored
4. **Register** — ASTRA creates the artifact kind and the capability. Both are immediately
   available for use in capability packs and playbooks.

---

## 8. Checklist

Before registering your server, verify:

- [ ] Return type is a typed Pydantic model (not `Dict[str, Any]`)
- [ ] Tool returns the same shape on every call (no conditional output structures)
- [ ] Server is reachable at `<base_url>/mcp` via streamable-http
- [ ] Output schema in the Inspect step matches your actual return structure
- [ ] Artifact kind JSON schema in the Review step accurately describes your output
- [ ] You have tested your tool end-to-end before registering (the conductor will validate
      every response against the registered schema at runtime)

---

## 9. Runtime Behaviour After Registration

Once registered, here is what happens every time your capability runs in a playbook:

1. Conductor connects to your MCP server at the URL stored in the capability's `execution.transport`
2. The configured tool is called with the resolved input arguments
3. The response is unwrapped from FastMCP's content envelope
4. ASTRA validates the response against the JSON schema stored in `schema_versions[0].json_schema`
   of the registered artifact kind
5. If validation passes, the artifact is persisted to the workspace and made available to
   downstream capabilities as a dependency input
6. If validation fails, the step is marked as failed and no artifact is written

Your server does not need to do anything special at steps 3–6. ASTRA handles all of that.

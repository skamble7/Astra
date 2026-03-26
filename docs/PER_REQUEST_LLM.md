# Per-Request LLM Configuration

## Overview

The conductor service now supports **per-request LLM configuration**, allowing users to customize the LLM provider, model, and parameters for each playbook execution. This provides flexibility for A/B testing, cost optimization, and provider comparison without requiring environment changes.

## Features

✅ **Optional LLM override per request**  
✅ **Fallback to environment settings** (.env)  
✅ **Capability override control** (use conductor's LLM for all capabilities)  
✅ **Partial overrides supported** (e.g., change only model, keep other params)  
✅ **Backward compatible** (existing clients work unchanged)

## API Schema

### Request Model

**Endpoint:** `POST /runs/start`

**New Field:** `llm_config` (optional)

```json
{
  "playbook_id": "pb.raina.microservices-arch.v1",
  "pack_id": "raina-microservices-arch@v1.0.0",
  "workspace_id": "uuid-here",
  "inputs": {...},
  "title": "Optional title",
  "description": "Optional description",
  "strategy": "delta",
  
  "llm_config": {
    "provider": "gemini",                 // Optional: openai, gemini, anthropic, etc.
    "model": "gemini-1.5-pro-latest",    // Optional: provider-specific model
    "temperature": 0.5,                   // Optional: 0.0 - 2.0
    "max_tokens": 8000,                   // Optional: max output tokens
    "strict_json": true,                  // Optional: JSON mode (OpenAI only)
    "override_capabilities": true         // Optional: force all capabilities to use these settings
  }
}
```

### LLMConfig Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `provider` | string | No | `LLM_PROVIDER` | LLM provider: openai, gemini, anthropic, etc. |
| `model` | string | No | `LLM_MODEL` | Provider-specific model name |
| `temperature` | float | No | `LLM_TEMPERATURE` | Sampling temperature (0.0 - 2.0) |
| `max_tokens` | int | No | `LLM_MAX_TOKENS` | Maximum output tokens |
| `strict_json` | bool | No | `LLM_STRICT_JSON` | Force JSON mode (OpenAI only) |
| `override_capabilities` | bool | No | `OVERRIDE_CAPABILITY_LLM` | Force all capabilities to use conductor's LLM |

## Fallback Priority

**Priority order for each field:**
1. **Request `llm_config`** → if provided
2. **Environment variables** (.env) → if request field is `null`

**Example:**
```json
{
  "llm_config": {
    "provider": "gemini",    // Uses Gemini
    "model": null,           // Falls back to LLM_MODEL from .env
    "temperature": 0.5       // Uses 0.5
  }
}
```
Result: Gemini with .env model + temperature 0.5 + other .env defaults

## Usage Examples

### Example 1: Full Override with Gemini Pro

**Use Case:** Production run with premium model

```bash
curl -X POST http://localhost:9022/runs/start \
  -H "Content-Type: application/json" \
  -d '{
    "playbook_id": "pb.raina.microservices-arch.v1",
    "pack_id": "raina-microservices-arch@v1.0.0",
    "workspace_id": "9cc0efc6-42c2-44d9-b39f-25c357955afa",
    "inputs": {"stories_url": "http://example.com"},
    "llm_config": {
      "provider": "gemini",
      "model": "gemini-1.5-pro-latest",
      "temperature": 0.3,
      "max_tokens": 8000,
      "override_capabilities": true
    }
  }'
```

**Result:**
- Conductor agent → Gemini 1.5 Pro (temp=0.3, max=8000)
- All capabilities → Gemini 1.5 Pro (override enabled)

---

### Example 2: Model-Only Override

**Use Case:** Test gpt-4o while keeping other settings

```json
{
  "playbook_id": "...",
  "llm_config": {
    "model": "gpt-4o"
  }
}
```

**Result:**
- Uses provider from `LLM_PROVIDER` (e.g., openai)
- Uses gpt-4o instead of `LLM_MODEL`
- Other params from .env

---

### Example 3: No Override (Environment Fallback)

**Use Case:** Standard execution with .env settings

```json
{
  "playbook_id": "...",
  "pack_id": "...",
  "workspace_id": "...",
  "inputs": {...}
  // No llm_config
}
```

**Result:**
- Uses all settings from .env
- `OVERRIDE_CAPABILITY_LLM` from .env applies

---

### Example 4: Mixed Providers

**Use Case:** Gemini for conductor, OpenAI for capabilities

```json
{
  "playbook_id": "...",
  "llm_config": {
    "provider": "gemini",
    "model": "gemini-1.5-flash-latest",
    "temperature": 0.2,
    "override_capabilities": false
  }
}
```

**Result:**
- Conductor agent → Gemini Flash (temp=0.2)
- Capabilities → Their own configs (e.g., OpenAI gpt-4o-mini)

---

### Example 5: Cost Optimization

**Use Case:** Cheap model for development

```json
{
  "playbook_id": "...",
  "llm_config": {
    "model": "gpt-4o-mini",
    "temperature": 0,
    "override_capabilities": true
  }
}
```

**Result:**
- All use gpt-4o-mini (cheapest)
- Temperature=0 for deterministic output

---

## Override Capabilities Behavior

The `override_capabilities` field controls whether capabilities use their own LLM configs or inherit from the conductor agent.

### `override_capabilities: true`

**All capabilities** use the conductor's LLM settings (from request or .env):

```json
{
  "llm_config": {
    "provider": "gemini",
    "model": "gemini-1.5-pro-latest",
    "override_capabilities": true
  }
}
```

**Flow:**
```
Conductor Agent → Gemini 1.5 Pro
   ↓
Capability 1 → Gemini 1.5 Pro (overridden)
Capability 2 → Gemini 1.5 Pro (overridden)
Capability 3 → Gemini 1.5 Pro (overridden)
```

### `override_capabilities: false`

**Each capability** uses its own configured LLM:

```json
{
  "llm_config": {
    "provider": "gemini",
    "model": "gemini-1.5-flash-latest",
    "override_capabilities": false
  }
}
```

**Flow:**
```
Conductor Agent → Gemini Flash
   ↓
Capability 1 → OpenAI gpt-4o-mini (from capability config)
Capability 2 → OpenAI gpt-4o-mini (from capability config)
Capability 3 → Gemini 1.5 Flash (from capability config)
```

### Default (not specified)

Falls back to `OVERRIDE_CAPABILITY_LLM` environment variable:

```bash
# .env
OVERRIDE_CAPABILITY_LLM=0  # Capabilities use own configs
```

---

## Implementation Details

### Code Changes

**1. Models (`app/models/run_models.py`)**
```python
class LLMConfig(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, gt=0)
    strict_json: Optional[bool] = None
    override_capabilities: Optional[bool] = None

class StartRunRequest(BaseModel):
    # ... existing fields ...
    llm_config: Optional[LLMConfig] = None
```

**2. Factory (`app/llm/factory.py`)**
```python
def get_agent_llm(llm_config: Optional[Dict[str, Any]] = None) -> AgentLLM:
    # Merge request config with env fallback
    provider = llm_config.get("provider") or settings.llm_provider
    model = llm_config.get("model") or settings.llm_model
    # ... build adapter with merged config
```

**3. Graph (`app/agent/graph.py`)**
```python
def run_input_bootstrap(..., start_request: Dict[str, Any], ...):
    llm_config_dict = start_request.get("llm_config")
    compiled = ConductorGraph(...).build(llm_config=llm_config_dict)
```

**4. Execution (`app/agent/nodes/llm_execution.py`)**
```python
# Priority: request override > env override
request_llm_config = state.get("request", {}).get("llm_config") or {}
override_capabilities = request_llm_config.get("override_capabilities")
if override_capabilities is None:
    override_capabilities = settings.override_capability_llm
```

---

## Use Cases

### A/B Testing
Compare different models on the same playbook:
```bash
# Test 1: OpenAI gpt-4o
{"llm_config": {"model": "gpt-4o"}}

# Test 2: Gemini Pro
{"llm_config": {"provider": "gemini", "model": "gemini-1.5-pro-latest"}}
```

### Cost Control
Force cheap model for dev, premium for prod:
```python
# Development
{"llm_config": {"model": "gpt-4o-mini", "override_capabilities": true}}

# Production (no llm_config, uses .env with premium models)
```

### Provider Comparison
Run same playbook with different providers:
```bash
# Run 1: All OpenAI
{"llm_config": {"provider": "openai", "override_capabilities": true}}

# Run 2: All Gemini
{"llm_config": {"provider": "gemini", "override_capabilities": true}}
```

### Temperature Tuning
Test different creativity levels:
```bash
# Conservative (more deterministic)
{"llm_config": {"temperature": 0}}

# Creative (more varied)
{"llm_config": {"temperature": 1.5}}
```

---

## Migration Guide

### For Existing Clients

**No changes required!** Existing requests work as before:

```json
{
  "playbook_id": "...",
  "pack_id": "...",
  "workspace_id": "...",
  "inputs": {...}
}
```

This still uses environment settings from .env.

### To Enable Per-Request LLM

**Add `llm_config` field:**

```json
{
  "playbook_id": "...",
  "llm_config": {
    "provider": "gemini",
    "model": "gemini-1.5-flash-latest"
  }
}
```

### Environment Variables Still Supported

All existing .env variables work:
```bash
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
LLM_TEMPERATURE=0.1
LLM_MAX_TOKENS=4000
LLM_STRICT_JSON=1
OVERRIDE_CAPABILITY_LLM=0
```

These become **fallback defaults** when request doesn't specify `llm_config`.

---

## Validation

### Invalid Provider
```json
{"llm_config": {"provider": "invalid"}}
```
**Error:** `ValueError: Unsupported LLM provider: invalid`

### Invalid Temperature
```json
{"llm_config": {"temperature": 3.0}}
```
**Error:** Pydantic validation error (must be ≤ 2.0)

### Invalid Tokens
```json
{"llm_config": {"max_tokens": 0}}
```
**Error:** Pydantic validation error (must be > 0)

---

## Benefits

✅ **Flexibility**: Different LLM per run  
✅ **Testing**: A/B test models easily  
✅ **Cost Control**: Override with cheap/premium models  
✅ **Backward Compatible**: No breaking changes  
✅ **Gradual Adoption**: Add `llm_config` when needed  
✅ **Provider Agnostic**: Works with OpenAI, Gemini, Anthropic, etc.

---

## Future Enhancements

- [ ] Support for Anthropic Claude
- [ ] Support for Cohere Command
- [ ] Support for Azure OpenAI
- [ ] Per-capability LLM override (different LLM per step)
- [ ] Cost tracking per request
- [ ] Model performance metrics

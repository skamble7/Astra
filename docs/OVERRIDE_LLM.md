# LLM Override Feature

## Overview

The conductor service supports two modes of LLM execution for capabilities:

1. **Normal Mode** (default): Each capability uses its configured provider/model
2. **Override Mode**: All capabilities use the conductor's LLM settings

## Environment Variable

```bash
OVERRIDE_CAPABILITY_LLM=0  # 0 = disabled (default), 1 = enabled
```

## Use Cases

### Override Enabled (`OVERRIDE_CAPABILITY_LLM=1`)

**When to use:**
- 🧪 **Testing**: Test playbooks with single provider before production
- 💰 **Cost Control**: Force all capabilities to use cheaper model
- 🎯 **Demos**: Ensure consistent provider for demonstrations
- 🔧 **Debugging**: Isolate provider-specific issues
- 📊 **Benchmarking**: Compare same playbook across different providers

**Example scenario:**
```bash
# Force entire playbook to use Gemini, regardless of capability configs
LLM_PROVIDER=gemini
LLM_MODEL=gemini-1.5-flash-latest
LLM_API_KEY=AIzaSy...
OVERRIDE_CAPABILITY_LLM=1
```

Result: All capabilities execute with Gemini, even if they specify `provider: openai`

### Override Disabled (`OVERRIDE_CAPABILITY_LLM=0`)

**When to use:**
- 🚀 **Production**: Let capabilities use their optimized provider/model
- 🎨 **Mixed Providers**: Use OpenAI for some tasks, Gemini for others
- 💪 **Flexibility**: Each capability chooses best LLM for its task
- 🔐 **Magic Token**: Automatic provider-based key resolution

**Example scenario:**
```bash
# Capabilities will use their own provider configs
OPENAI_API_KEY=sk-proj-...
GEMINI_API_KEY=AIzaSy...
ANTHROPIC_API_KEY=sk-ant-...
OVERRIDE_CAPABILITY_LLM=0
```

Result: 
- Capabilities with `provider: openai` use OpenAI
- Capabilities with `provider: gemini` use Gemini
- Keys auto-resolved via `PROVIDER_API_KEY` magic token

## How It Works

### Normal Mode Flow

```
Capability Config (MongoDB)
├── provider: openai
├── model: gpt-4o-mini
├── auth: {alias_key: "PROVIDER_API_KEY"}
└── parameters: {temperature: 0, max_tokens: 2000}
         ↓
SecretResolver.resolve_auth(provider="openai")
         ↓
PROVIDER_API_KEY + provider="openai" → OPENAI_API_KEY
         ↓
Execution with OpenAI
```

### Override Mode Flow

```
Capability Config (MongoDB)
├── provider: openai  ← IGNORED
├── model: gpt-4o-mini  ← IGNORED
├── auth: {...}  ← IGNORED
└── parameters: {...}  ← IGNORED
         ↓
Override with Conductor Settings
├── provider: gemini  ← from LLM_PROVIDER
├── model: gemini-1.5-flash-latest  ← from LLM_MODEL
├── auth: {alias_key: "LLM_API_KEY"}  ← conductor's key
└── parameters: {temperature: 0.7, max_tokens: 4000}
         ↓
Execution with Gemini
```

## Code Reference

### Configuration (`app/config.py`)

```python
class Settings(BaseSettings):
    override_capability_llm: bool = bool(int(os.getenv("OVERRIDE_CAPABILITY_LLM", "0")))
```

### Execution Logic (`app/agent/nodes/llm_execution.py`)

```python
if settings.override_capability_llm:
    logger.info("[llm] OVERRIDE: Using conductor LLM settings instead of capability config")
    provider = settings.llm_provider
    model = settings.llm_model
    temperature = settings.llm_temperature
    max_tokens = settings.llm_max_tokens
    auth_alias = {"method": "api_key", "alias_key": "LLM_API_KEY"}
else:
    # Use capability's configuration
    exec_cfg = capability.get("execution", {}).get("llm_config", {})
    provider = exec_cfg.get("provider")
    model = exec_cfg.get("model")
    # ... extract from capability
```

## Examples

### Example 1: Development Testing

Test playbook with single provider before adding multi-provider support:

```bash
# .env
LLM_PROVIDER=gemini
LLM_MODEL=gemini-1.5-flash-latest
LLM_API_KEY=AIzaSy...
OVERRIDE_CAPABILITY_LLM=1  # Force all to Gemini

# Run playbook - all capabilities use Gemini
```

### Example 2: Cost Optimization

Force cheaper model for batch processing:

```bash
# .env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini  # Cheaper than gpt-4o
LLM_API_KEY=sk-proj-...
OVERRIDE_CAPABILITY_LLM=1

# All capabilities use gpt-4o-mini regardless of their config
```

### Example 3: Production Mixed Providers

Let capabilities optimize their own LLM:

```bash
# .env
OPENAI_API_KEY=sk-proj-...
GEMINI_API_KEY=AIzaSy...
OVERRIDE_CAPABILITY_LLM=0  # Allow capability choice

# Microservices discovery → OpenAI gpt-4o-mini
# Data pipeline analysis → Gemini gemini-1.5-flash-latest
# Each uses best model for task
```

## Verification

Check current override state:

```bash
docker exec astra-conductor-service python -c "
from app.config import settings
print(f'Override: {settings.override_capability_llm}')
print(f'Provider: {settings.llm_provider}')
print(f'Model: {settings.llm_model}')
"
```

## Logs

When override is active, you'll see:

```
[llm] OVERRIDE: Using conductor LLM settings instead of capability config
[llm] Building exec LLM with provider=gemini, model=gemini-1.5-flash-latest
```

When override is disabled, you'll see:

```
[llm] Using capability LLM config: provider=openai, model=gpt-4o-mini
[llm] Magic token PROVIDER_API_KEY resolved to OPENAI_API_KEY
```

## Migration Notes

No database migration required! This is a runtime flag:

- ✅ Capabilities keep their stored configs
- ✅ Toggle override without reseeding
- ✅ No API changes
- ✅ Backward compatible

## Best Practices

1. **Default to Disabled**: Use override only when needed
2. **Document Usage**: Comment why override is enabled in production
3. **Test Both Modes**: Verify playbooks work with and without override
4. **Monitor Costs**: Track provider usage when override disabled
5. **Log Review**: Check override logs match expected behavior

## Troubleshooting

**Problem**: Override not working
- Check: `OVERRIDE_CAPABILITY_LLM=1` (not "true" or "yes")
- Restart: Container must restart after env change

**Problem**: Wrong provider used
- Check: Override disabled? Capability config takes precedence
- Check: Magic token resolution logs show correct provider mapping

**Problem**: Authentication errors
- Check: Override enabled? Need `LLM_API_KEY` not provider-specific key
- Check: Override disabled? Need provider-specific keys (OPENAI_API_KEY, etc.)

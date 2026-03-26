# Adding a New LLM Provider to ASTRA Conductor Service

**Document Version:** 1.0  
**Last Updated:** February 23, 2026  
**Maintainer:** ASTRA Platform Team

---

## Overview

This guide provides step-by-step instructions for adding a new LLM provider (e.g., Anthropic Claude, Ollama, Azure OpenAI, etc.) to the ASTRA Conductor Service. The conductor uses LLMs for two purposes:

1. **Agent Orchestration** - Semantic input mapping in the `mcp_input_resolver_node`
2. **Capability Execution** - Running LLM-type capabilities defined in playbooks

---

## Architecture Overview

### Dual LLM Usage Pattern

The conductor has **two separate LLM usage patterns** that both need implementation:

| Pattern | Purpose | Interface | Used By |
|---------|---------|-----------|---------|
| **Agent LLM** | Drives conductor orchestration logic | `AgentLLM` protocol | `mcp_input_resolver_node` |
| **Execution LLM** | Executes LLM-type capabilities | `ExecLLM` protocol | `llm_execution_node` |

### Key Design Principles

- **Vendor Agnostic:** Single `LLM_API_KEY` environment variable works for all providers
- **Factory Pattern:** Provider selection via `LLM_PROVIDER` environment variable
- **Protocol-Based:** Each adapter implements a protocol interface for loose coupling
- **Configuration-Driven:** No code changes needed to switch providers at runtime

---

## Prerequisites

Before starting, ensure you have:

- [ ] Access to the ASTRA repository
- [ ] Understanding of Python async/await patterns
- [ ] API key for the new LLM provider
- [ ] Familiarity with the provider's SDK or REST API
- [ ] Docker and docker-compose installed (for testing)

---

## Implementation Checklist

### Phase 1: Core Implementation (Est. 2-4 hours)

#### Task 1: Create Agent LLM Adapter
**File:** `services/conductor-service/app/llm/<provider>_adapter.py`

- [ ] Create new file following naming convention: `{provider}_adapter.py`
- [ ] Import provider's SDK or HTTP client library
- [ ] Implement `AgentLLM` protocol with two methods:
  - [ ] `async def acomplete()` - Free-form text completion
  - [ ] `async def acomplete_json()` - JSON-constrained completion with schema
- [ ] Add error handling for API failures
- [ ] Add logging for debugging
- [ ] Handle provider-specific configuration (temperature, max_tokens, etc.)

**Example Structure:**
```python
from __future__ import annotations
import logging
from typing import Any, Dict, Optional

from <provider_sdk> import AsyncClient  # Replace with actual SDK
from app.config import settings
from app.llm.base import AgentLLM, CompletionResult

logger = logging.getLogger("app.llm.<provider>")

class <Provider>Adapter(AgentLLM):
    def __init__(self) -> None:
        if not settings.llm_api_key:
            raise RuntimeError("LLM_API_KEY is not configured")
        
        self.client = AsyncClient(api_key=settings.llm_api_key)
        self.model = settings.llm_model
        # ... other config
    
    async def acomplete(self, prompt: str, *, temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> CompletionResult:
        # Implementation here
        pass
    
    async def acomplete_json(self, prompt: str, schema: Dict[str, Any], *, temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> CompletionResult:
        # Implementation here
        pass
```

**Reference Implementation:** See `app/llm/gemini_adapter.py` or `app/llm/openai_adapter.py`

---

#### Task 2: Create Execution LLM Adapter
**File:** `services/conductor-service/app/llm/execution_<provider>.py`

- [ ] Create new file following naming convention: `execution_{provider}.py`
- [ ] Import provider's SDK or HTTP client library
- [ ] Implement `ExecLLM` protocol with one method:
  - [ ] `async def acomplete()` - Accepts system_prompt, user_prompt, temperature, top_p, max_tokens
- [ ] Handle auth configuration (API key, headers, etc.)
- [ ] Add token usage tracking in response metadata
- [ ] Return `ExecResult` with text and raw response data

**Example Structure:**
```python
from __future__ import annotations
import logging
from typing import Any, Dict, Optional

from <provider_sdk> import AsyncClient
from app.llm.execution_base import ExecLLM, ExecResult

logger = logging.getLogger("app.llm.exec.<provider>")

class <Provider>ExecAdapter(ExecLLM):
    def __init__(self, *, api_key: Optional[str], model: str, timeout_sec: int, headers: Dict[str, str], query_params: Dict[str, str]) -> None:
        if not api_key:
            raise RuntimeError(f"{provider} API key is required")
        
        self.client = AsyncClient(api_key=api_key)
        self.model_name = model
        # ... other config
    
    async def acomplete(self, *, system_prompt: Optional[str], user_prompt: str, temperature: Optional[float], top_p: Optional[float], max_tokens: Optional[int]) -> ExecResult:
        # Implementation here
        pass
```

**Reference Implementation:** See `app/llm/execution_gemini.py` or `app/llm/execution_openai.py`

---

#### Task 3: Register in Agent Factory
**File:** `services/conductor-service/app/llm/factory.py`

- [ ] Import the new adapter class
- [ ] Add provider case to `get_agent_llm()` function
- [ ] Return instance of new adapter

**Changes Required:**
```python
from app.llm.<provider>_adapter import <Provider>Adapter

def get_agent_llm() -> AgentLLM:
    provider = settings.llm_provider.lower()
    if provider == "openai":
        return OpenAIAdapter()
    elif provider == "gemini":
        return GeminiAdapter()
    elif provider == "<provider>":  # Add this
        return <Provider>Adapter()
    raise ValueError(f"Unsupported LLM provider: {provider}")
```

---

#### Task 4: Register in Execution Factory
**File:** `services/conductor-service/app/llm/execution_factory.py`

- [ ] Import the new execution adapter class
- [ ] Add provider case to `build_exec_llm()` function
- [ ] Pass required parameters (api_key, model, timeout_sec, headers, query_params)

**Changes Required:**
```python
from app.llm.execution_<provider> import <Provider>ExecAdapter

def build_exec_llm(...) -> ExecLLM:
    # ... existing code ...
    
    elif provider == "<provider>":
        return <Provider>ExecAdapter(
            api_key=auth.token or auth.key,
            model=model,
            timeout_sec=timeout_sec,
            headers=headers,
            query_params=query_params,
        )
    
    # ... rest of function ...
```

---

### Phase 2: Dependencies & Configuration (Est. 30 min - 1 hour)

#### Task 5: Update Dependencies
**File:** `services/conductor-service/pyproject.toml`

- [ ] Add provider's SDK to `dependencies` list
- [ ] Specify minimum version requirement
- [ ] Test installation locally: `pip install '<provider-sdk>>=x.y.z'`

**Example:**
```toml
dependencies = [
  # ... existing deps ...
  "openai>=1.35",
  "google-genai>=0.1.0",
  "<provider-sdk>>=x.y.z",  # Add this
  # ... rest of deps ...
]
```

---

#### Task 6: Update Environment Configuration
**File:** `services/conductor-service/.env.example`

- [ ] Add provider example to supported providers comment
- [ ] Add model examples in configuration comment
- [ ] Optionally add secret alias example (for capability execution)

**Example:**
```bash
# ──────────────────────────────
# LLM driving the conductor agent
# ──────────────────────────────
# Supported providers: openai, gemini, <provider>
LLM_PROVIDER=openai

# Vendor-agnostic API key (works for any provider)
LLM_API_KEY=your-api-key-here

# Model configuration (provider-specific)
# For OpenAI: gpt-4o-mini, gpt-4o, gpt-4-turbo, etc.
# For Gemini: gemini-1.5-pro, gemini-1.5-flash, gemini-1.0-pro, etc.
# For <Provider>: <model-1>, <model-2>, etc.
LLM_MODEL=gpt-4o-mini

# ... rest of config ...

# Secret resolution examples
ASTRA_SECRET_OPENAI=sk-xxx
ASTRA_SECRET_GEMINI=xxx
ASTRA_SECRET_<PROVIDER>=xxx  # Add this
```

---

### Phase 3: Testing (Est. 1-2 hours)

#### Task 7: Local Testing

- [ ] Install dependencies: `cd services/conductor-service && pip install -e .`
- [ ] Create test script to verify imports:
  ```python
  from app.llm.<provider>_adapter import <Provider>Adapter
  from app.llm.execution_<provider> import <Provider>ExecAdapter
  print("✓ Adapters import successfully")
  ```
- [ ] Run import test: `python test_imports.py`
- [ ] Check for import errors or missing dependencies

---

#### Task 8: Integration Testing

- [ ] Update `.env.example` with test API key and model:
  ```bash
  LLM_PROVIDER=<provider>
  LLM_API_KEY=your-test-key
  LLM_MODEL=<provider-model-name>
  ```
- [ ] Build Docker image:
  ```bash
  cd deploy
  docker compose build astra-conductor-service
  ```
- [ ] Start service:
  ```bash
  docker compose up -d astra-conductor-service
  ```
- [ ] Verify environment variables in container:
  ```bash
  docker exec astra-conductor-service env | grep LLM_
  ```
- [ ] Check service logs for startup errors:
  ```bash
  docker logs astra-conductor-service --tail 50
  ```
- [ ] Test with actual playbook execution (see test plan below)

---

#### Task 9: Create Test Playbook Run

- [ ] Create minimal capability pack with LLM capability
- [ ] Trigger run via API:
  ```bash
  curl -X POST http://localhost:9022/runs/start \
    -H "Content-Type: application/json" \
    -d '{
      "workspace_id": "test-workspace",
      "pack_id": "test-pack",
      "playbook_id": "test-playbook",
      "inputs": {}
    }'
  ```
- [ ] Monitor logs for LLM execution:
  ```bash
  docker logs -f astra-conductor-service | grep -E "llm|<provider>"
  ```
- [ ] Verify successful completion and artifact generation
- [ ] Check for any error messages or warnings

---

### Phase 4: Documentation (Est. 30 min)

#### Task 10: Update Documentation

- [ ] Update this guide with provider-specific notes (if any)
- [ ] Add provider to README or main documentation
- [ ] Document any provider-specific configuration requirements
- [ ] Add example usage with the new provider
- [ ] Update architecture diagrams (if applicable)

---

### Phase 5: Code Review & Deployment (Est. 1-2 hours)

#### Task 11: Code Review Preparation

- [ ] Run linter: `ruff check services/conductor-service/app/llm/`
- [ ] Run formatter: `black services/conductor-service/app/llm/`
- [ ] Check for type errors: `mypy services/conductor-service/app/llm/` (if configured)
- [ ] Review error handling and logging
- [ ] Verify no hardcoded secrets or API keys
- [ ] Check that all exceptions are properly caught and logged

---

#### Task 12: Git Workflow

- [ ] Create feature branch: `git checkout -b feat/add-<provider>-llm`
- [ ] Stage changes: `git add services/conductor-service/`
- [ ] Commit with descriptive message:
  ```bash
  git commit -m "feat(conductor): Add <Provider> LLM support
  
  - Implement AgentLLM adapter for orchestration
  - Implement ExecLLM adapter for capability execution
  - Register in factory patterns
  - Add dependencies and configuration
  - Update documentation
  
  Tested with <provider> API and verified both agent
  orchestration and LLM capability execution."
  ```
- [ ] Push to remote: `git push origin feat/add-<provider>-llm`
- [ ] Create pull request with detailed description

---

#### Task 13: Deployment Checklist

- [ ] Obtain production API keys for the provider
- [ ] Update production `.env` or secrets management system
- [ ] Plan deployment window (if needed)
- [ ] Deploy to staging environment first
- [ ] Run smoke tests in staging
- [ ] Monitor staging for 24-48 hours
- [ ] Deploy to production
- [ ] Verify with production playbook run
- [ ] Monitor error rates and performance

---

## Provider-Specific Considerations

### API Differences to Handle

| Aspect | Considerations |
|--------|----------------|
| **Authentication** | Bearer token, API key header, OAuth, custom auth |
| **Request Format** | REST, gRPC, WebSocket |
| **System Prompts** | Separate role vs. combined with user prompt |
| **JSON Mode** | Native support, schema enforcement, or prompt engineering |
| **Streaming** | Supported, not supported, or partial support |
| **Rate Limits** | Provider-specific throttling and retry logic |
| **Token Counting** | Included in response vs. separate API call |
| **Error Codes** | Provider-specific error handling |

### Common Challenges & Solutions

| Challenge | Solution |
|-----------|----------|
| **No native JSON mode** | Enhance prompt with schema + parse response |
| **No async SDK** | Wrap synchronous calls with `asyncio.to_thread()` |
| **Different message formats** | Transform to/from provider format in adapter |
| **Rate limiting** | Implement exponential backoff with `tenacity` |
| **Token limits** | Validate before sending, truncate if needed |
| **Streaming responses** | Collect full response or implement streaming handler |

---

## Testing Strategy

### Unit Tests (Optional but Recommended)

Create `tests/llm/test_<provider>_adapter.py`:

```python
import pytest
from app.llm.<provider>_adapter import <Provider>Adapter

@pytest.mark.asyncio
async def test_acomplete():
    adapter = <Provider>Adapter()
    result = await adapter.acomplete("Hello, world!")
    assert result.text
    assert result.raw

@pytest.mark.asyncio
async def test_acomplete_json():
    adapter = <Provider>Adapter()
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    result = await adapter.acomplete_json("Generate a name", schema)
    assert result.text
    import json
    data = json.loads(result.text)
    assert "name" in data
```

### Integration Tests

- [ ] Test with real API (using test account)
- [ ] Test with invalid API key (should raise RuntimeError)
- [ ] Test with network timeout
- [ ] Test with rate limiting
- [ ] Test token usage tracking
- [ ] Test both text and JSON completions

---

## Rollback Plan

If issues arise after deployment:

1. **Immediate Rollback:**
   ```bash
   # Switch back to OpenAI in .env
   LLM_PROVIDER=openai
   LLM_API_KEY=<openai-key>
   
   # Restart service
   docker compose up -d --force-recreate astra-conductor-service
   ```

2. **Code Rollback:**
   ```bash
   git revert <commit-hash>
   git push origin main
   # Redeploy previous version
   ```

3. **Verify:**
   - Check service logs
   - Run test playbook
   - Monitor for errors

---

## Estimated Effort Summary

| Phase | Tasks | Estimated Time |
|-------|-------|----------------|
| **Phase 1: Core Implementation** | Tasks 1-4 | 2-4 hours |
| **Phase 2: Dependencies & Config** | Tasks 5-6 | 30 min - 1 hour |
| **Phase 3: Testing** | Tasks 7-9 | 1-2 hours |
| **Phase 4: Documentation** | Task 10 | 30 min |
| **Phase 5: Review & Deployment** | Tasks 11-13 | 1-2 hours |
| **Total** | 13 tasks | **5-10 hours** |

**Note:** Time estimates assume familiarity with the provider's SDK and ASTRA codebase.

---

## Examples of Providers to Add

### Priority Providers

1. **Anthropic Claude** - High demand, excellent reasoning capabilities
2. **Azure OpenAI** - Enterprise customers with Azure infrastructure
3. **Ollama** - Local/on-premise deployments, privacy-sensitive use cases
4. **OpenRouter** - Multi-provider aggregation, cost optimization

### Provider Templates

Each provider should follow this template structure:

```
services/conductor-service/app/llm/
├── <provider>_adapter.py          # Agent LLM adapter
├── execution_<provider>.py        # Execution LLM adapter
└── factory.py                     # Updated with new provider
```

---

## Support & Resources

- **ASTRA Documentation:** `/docs/`
- **Code Examples:** See existing `openai_adapter.py` and `gemini_adapter.py`
- **Protocol Definitions:** `app/llm/base.py` and `app/llm/execution_base.py`
- **Team Contact:** ASTRA Platform Team
- **Issue Tracking:** GitHub Issues

---

## Appendix: Quick Reference

### Key Files to Modify

```
services/conductor-service/
├── app/
│   ├── config.py                    # No changes needed
│   └── llm/
│       ├── base.py                  # AgentLLM protocol (read-only)
│       ├── execution_base.py        # ExecLLM protocol (read-only)
│       ├── factory.py               # ✏️ Add provider case
│       ├── execution_factory.py     # ✏️ Add provider case
│       ├── <provider>_adapter.py    # ✨ Create new
│       └── execution_<provider>.py  # ✨ Create new
├── pyproject.toml                   # ✏️ Add SDK dependency
└── .env.example                     # ✏️ Update examples
```

### Environment Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `LLM_PROVIDER` | Select provider | `openai`, `gemini`, `<provider>` |
| `LLM_API_KEY` | Authentication | Provider's API key |
| `LLM_MODEL` | Model selection | `gpt-4o-mini`, `gemini-1.5-flash` |
| `LLM_TEMPERATURE` | Sampling temp | `0.1` - `2.0` |
| `LLM_MAX_TOKENS` | Response limit | `4000` |

---

**End of Guide**

For questions or issues, contact the ASTRA Platform Team or open a GitHub issue.

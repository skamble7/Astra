# LangGraph InvalidUpdateError Fix

## Problem

```
langgraph.errors.InvalidUpdateError: At key 'dispatch': Can receive only one value per step. 
langgraph.errors.InvalidUpdateError: At key 'last_mcp_error': Can receive only one value per step.
Use an Annotated key to handle multiple values.
```

## Root Cause

Multiple fields in `GraphState` were being written to by different nodes in the same execution step:

1. **capability_executor_node** → writes to `dispatch`, `last_mcp_error`, etc. and routes to next node
2. **mcp_input_resolver_node** → writes to same fields again before routing to execution
3. **llm_execution_node** → writes to error/summary fields during execution

By default, LangGraph's `LastValue` channel only accepts one write per step. When multiple nodes try to update the same field in one step, it raises `InvalidUpdateError`.

## Solution

Changed multiple fields from simple types to `Annotated` types with reducer functions:

```python
# Before
dispatch: Dict[str, Any]
last_mcp_error: Optional[str]
last_mcp_summary: Dict[str, Any]
last_enrichment_error: Optional[str]
last_enrichment_summary: Dict[str, Any]

# After  
dispatch: Annotated[Dict[str, Any], lambda left, right: right]
last_mcp_error: Annotated[Optional[str], lambda left, right: right]
last_mcp_summary: Annotated[Dict[str, Any], lambda left, right: right]
last_enrichment_error: Annotated[Optional[str], lambda left, right: right]
last_enrichment_summary: Annotated[Dict[str, Any], lambda left, right: right]
```

The reducer function `lambda left, right: right` tells LangGraph how to handle multiple writes:
- `left`: Previous value
- `right`: New value
- Return `right`: Always use the latest value (overwrite)

## Files Changed

### `/services/conductor-service/app/agent/graph.py`

**Added import:**
```python
from typing import Any, Dict, Optional, TypedDict, Annotated
```

**Updated GraphState:**
```python
class GraphState(TypedDict, total=False):
    # ... other fields ...
    
    # Use Annotated with reducer to allow multiple writes per step
    dispatch: Annotated[Dict[str, Any], lambda left, right: right]
    
    # These fields can be written by multiple nodes in the same step
    last_mcp_summary: Annotated[Dict[str, Any], lambda left, right: right]
    last_mcp_error: Annotated[Optional[str], lambda left, right: right]
    last_enrichment_summary: Annotated[Dict[str, Any], lambda left, right: right]
    last_enrichment_error: Annotated[Optional[str], lambda left, right: right]
    
    # ... other fields ...
```

## How It Works

### Before (Error)
```
Step 1:
├─ capability_executor writes: dispatch = {capability: X, step: Y}
├─ Routes to: mcp_input_resolver
├─ mcp_input_resolver writes: dispatch = {capability: X, step: Y, resolved: Z}
└─ ❌ ERROR: Two writes to 'dispatch' in same step!
```

### After (Fixed)
```
Step 1:
├─ capability_executor writes: dispatch = {capability: X, step: Y}
├─ Routes to: mcp_input_resolver
├─ mcp_input_resolver writes: dispatch = {capability: X, step: Y, resolved: Z}
└─ ✅ Reducer: lambda(left, right) → right (keep latest)
```

## Alternative Reducers

Other common reducer patterns:

```python
# Merge dictionaries (deep merge)
dispatch: Annotated[Dict[str, Any], lambda left, right: {**left, **right}]

# Accumulate in list
dispatch: Annotated[List[Dict], lambda left, right: left + [right]]

# Custom logic
def merge_dispatch(left, right):
    result = left.copy()
    result.update(right)
    return result

dispatch: Annotated[Dict[str, Any], merge_dispatch]
```

## Why "Take Right" Strategy

In our case, `lambda left, right: right` (always take latest) is correct because:

1. **capability_executor** → **mcp_input_resolver** → **mcp_execution** flow
2. Each node enriches or clears the state fields (dispatch, errors, summaries)
3. Later nodes need the most recent state, not accumulated history
4. Error/summary fields are explicitly cleared by capability_executor before dispatching

If we used merge (`{**left, **right}`), we might accumulate stale data from previous steps.

## What Changed with OVERRIDE_CAPABILITY_LLM

The OVERRIDE_CAPABILITY_LLM feature didn't directly cause this issue, but it may have changed timing or execution flow that exposed the pre-existing race condition where multiple nodes write to the same state fields in one step. The fix ensures all state fields that can be written by multiple nodes use `Annotated` with a reducer.

## Testing

After deploying the fix:

```bash
# Rebuild
docker compose build astra-conductor-service

# Restart
docker compose up -d astra-conductor-service

# Verify startup
docker logs astra-conductor-service --tail 20
```

Should see:
```
✅ Application startup complete.
✅ Uvicorn running on http://0.0.0.0:9022
```

## References

- [LangGraph Error Docs](https://docs.langchain.com/oss/python/langgraph/errors/INVALID_CONCURRENT_GRAPH_UPDATE)
- [LangGraph State Reducers](https://langchain-ai.github.io/langgraph/concepts/low_level/#reducers)
- [Annotated Types](https://docs.python.org/3/library/typing.html#typing.Annotated)

# services/conductor-service/app/mcp_host/invoker.py

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from app.mcp_host.types import InvokePage, InvokeResult, ToolCallSpec

logger = logging.getLogger("app.mcp.invoker")


class CancelToken:
    def __init__(self) -> None:
        self._evt = asyncio.Event()

    def cancel(self) -> None:
        self._evt.set()

    @property
    def is_cancelled(self) -> bool:
        return self._evt.is_set()

    async def wait(self) -> None:
        await self._evt.wait()


def _retryable(retries: int):
    retries = max(1, int(retries))
    return retry(
        stop=stop_after_attempt(retries),
        wait=wait_exponential_jitter(initial=0.2, max=2.0),
        reraise=True,
    )


@_retryable(retries=1)
async def _invoke_once(
    *,
    client,  # HttpMcpClient | StdioMcpClient (duck-typed)
    spec: ToolCallSpec,
    args: Dict[str, Any],
    start_cursor: Optional[str],
    cancel: Optional[CancelToken],
) -> InvokeResult:
    if cancel and cancel.is_cancelled:
        raise asyncio.CancelledError()

    return await client.invoke_tool(
        tool=spec.tool,
        args=args,
        expects_stream=spec.expects_stream,
        cursor=start_cursor,
        cancel=cancel,
        timeout_sec=spec.timeout_sec,
    )


async def invoke_tool_call(
    *,
    client,
    spec: ToolCallSpec,
    args: Dict[str, Any],
    start_cursor: Optional[str] = None,
    cancel: Optional[CancelToken] = None,
) -> InvokeResult:
    """
    Unified invocation entrypoint handling:
      - non-streaming pagination (handled inside transport)
      - streaming (async iterator passthrough)
      - cancellation (cooperative)
      - retries (per ToolCallSpec.retries)
    """
    # Rebind the retry decorator with the spec's retries at runtime
    retrying = _retryable(spec.retries)(_invoke_once)  # type: ignore[misc]

    result = await retrying(
        client=client,
        spec=spec,
        args=args,
        start_cursor=start_cursor,
        cancel=cancel,
    )

    # For streaming, simply return the stream iterator
    if result.stream is not None:
        return result

    # Non-streaming already contains all pages; we still allow cooperative cancel between pages
    if cancel and cancel.is_cancelled:
        raise asyncio.CancelledError()

    return result
from __future__ import annotations
import base64
import httpx
from typing import Any, Dict, Optional

from app.llm.execution_base import ExecLLM, ExecResult

class GenericHTTPExecAdapter(ExecLLM):
    """
    A minimal generic HTTP adapter:
      - POST {base_url} with JSON body:
          { system, user, temperature, top_p, max_tokens }
      - Expects response: { text: string, raw?: any }
    Useful for gateways like OpenRouter (with headers) or custom proxies.
    """
    def __init__(
        self,
        *,
        base_url: str,
        headers: Dict[str, str],
        timeout_sec: int,
        query_params: Dict[str, str],
        auth_header: Optional[str],
        basic_tuple: Optional[tuple[str, str]],
        api_key_header: Optional[tuple[str, str]],  # (headerName, key)
    ):
        self.base_url = base_url
        self.headers = dict(headers or {})
        if auth_header:
            self.headers["Authorization"] = auth_header
        if api_key_header:
            k, v = api_key_header
            self.headers[k] = v
        self.timeout = timeout_sec
        self.query = dict(query_params or {})
        self.basic = basic_tuple

    async def acomplete(
        self,
        *,
        system_prompt: Optional[str],
        user_prompt: str,
        temperature: Optional[float],
        top_p: Optional[float],
        max_tokens: Optional[int],
    ) -> ExecResult:
        auth = None
        if self.basic:
            auth = httpx.BasicAuth(self.basic[0], self.basic[1])

        payload = {
            "system": system_prompt,
            "user": user_prompt,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                self.base_url,
                params=self.query,
                headers=self.headers,
                json=payload,
                auth=auth,
            )
            r.raise_for_status()
            js = r.json()
            return ExecResult(text=(js.get("text") or "").strip(), raw=js)
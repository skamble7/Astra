# services/planner-service/app/agent/planner_agent.py
"""
Planner agentic loop node.

A self-contained ReAct-style loop that runs inside a single LangGraph node:
  1. Build system prompt (includes current plan) + conversation history
  2. Bind tools to the LangChain ChatModel
  3. Loop: invoke model → execute tool calls → invoke model again
  4. Extract final response text and any plan update written by update_plan()

The loop is bounded to MAX_ITERATIONS to prevent runaway costs.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from app.cache.manifest_cache import ManifestCache
from app.agent.planner_tools import make_planner_tools
from app.events.stream import publish_to_session
from app.llm.planner_llm import get_planner_chat_model

logger = logging.getLogger("app.agent.planner_agent")

MAX_ITERATIONS = 8  # max tool-call rounds per turn


def _extract_text(content: Any) -> str:
    """Normalize AIMessageChunk.content to a plain string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in content
        )
    return ""


_SYSTEM_PROMPT = """\
You are the ASTRA Planner — a conversational AI that helps users assemble and refine \
capability pipelines.

ASTRA is a general-purpose capability orchestration platform. Registered capabilities \
can do anything — parse COBOL, discover microservices architectures, modernise legacy \
code, generate API documentation, run security scans, analyse user stories, build \
knowledge graphs, and more. Each capability has a unique ID, takes structured inputs, \
and produces typed artifact outputs.

Your role:
- Help users discover which capabilities fit their goal
- Assemble an ordered pipeline (plan) of capabilities to solve that goal
- Answer questions about specific capabilities (inputs, outputs, artifact kinds)
- Modify existing plans based on user feedback

Available tools:
- search_capabilities(query) — find capabilities by keyword or domain
- get_capability_details(cap_id) — full details: description, inputs, artifact outputs
- list_all_capabilities() — browse all registered capabilities grouped by tag
- update_plan(steps) — create or replace the current execution plan

Rules:
- Always respond in Markdown: use **bold**, bullet lists, ## headings, proper punctuation
- When building or modifying a plan, call update_plan() with the complete ordered step list
- When a user asks about a specific capability, call get_capability_details() first
- For discovery queries, call search_capabilities() or list_all_capabilities()
- If the user asks to remove, reorder, or add steps, call update_plan() with the \
  updated complete list — YOU are the orchestrator, not a capability
- Be concise but informative
"""


def _format_current_plan(existing_plan: List[Dict[str, Any]]) -> str:
    if not existing_plan:
        return ""
    lines = ["\n\n---\n**Current plan:**\n"]
    for step in existing_plan:
        order = step.get("order", "?")
        title = step.get("title", step.get("capability_id", ""))
        cap_id = step.get("capability_id", "")
        lines.append(f"{order}. **{title}** (`{cap_id}`)")
    return "\n".join(lines)


def _build_history_messages(messages: List[Dict[str, Any]], current_message: str) -> List:
    """Convert session chat history (excluding the current message) to LangChain messages."""
    result = []
    # messages contains the full history including the current message at the end;
    # take the last 10 prior messages for context
    prior = [m for m in messages if m.get("content") != current_message][-10:]
    for m in prior:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "user":
            result.append(HumanMessage(content=content))
        else:
            result.append(AIMessage(content=content))
    return result


def planner_agent_node(*, cache: ManifestCache):
    """Factory — returns the async LangGraph node function."""

    async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        error = state.get("error")
        if error:
            return {}

        session_id = state.get("session_id", "")
        current_message = state.get("current_message", "")
        messages = state.get("messages") or []
        existing_plan = state.get("existing_plan") or []

        # Mutable container for update_plan() to write into
        state_ref: Dict[str, Any] = {"draft_plan": existing_plan}

        # Build tools and bind to model
        try:
            base_model = await get_planner_chat_model()
        except Exception as e:
            logger.exception("[planner_agent] failed to init LLM: %s", e)
            return {
                "draft_plan": existing_plan,
                "response_message": f"Planner LLM unavailable: {e}",
            }

        tools = make_planner_tools(cache, state_ref)
        model = base_model.bind_tools(tools)
        tool_map = {t.name: t for t in tools}

        # Build initial message list
        system_content = _SYSTEM_PROMPT + _format_current_plan(existing_plan)
        agent_messages: List = [SystemMessage(content=system_content)]
        agent_messages.extend(_build_history_messages(messages, current_message))
        agent_messages.append(HumanMessage(content=current_message))

        # Agentic loop
        final_response_text = ""
        for iteration in range(MAX_ITERATIONS):
            accumulated: Optional[AIMessageChunk] = None
            try:
                async for chunk in model.astream(agent_messages):
                    accumulated = chunk if accumulated is None else accumulated + chunk
                    # Publish text tokens live; tool-call chunks have non-empty tool_call_chunks
                    if not getattr(chunk, "tool_call_chunks", None):
                        token = _extract_text(chunk.content)
                        if token:
                            publish_to_session(session_id, {
                                "type": "planner.token",
                                "session_id": session_id,
                                "token": token,
                                "at": datetime.now(timezone.utc).isoformat(),
                            })
            except Exception as e:
                logger.exception("[planner_agent] LLM call failed session=%s iter=%d: %s", session_id, iteration, e)
                final_response_text = f"I encountered an error while processing your request: {e}"
                break

            if accumulated is None:
                break

            response = accumulated
            agent_messages.append(response)

            if not response.tool_calls:
                # Final textual response — extract content
                content = response.content
                if isinstance(content, list):
                    # Some providers return a list of content blocks
                    parts = [
                        block.get("text", "") if isinstance(block, dict) else str(block)
                        for block in content
                    ]
                    final_response_text = "\n".join(p for p in parts if p)
                else:
                    final_response_text = str(content or "")
                break

            # Execute tool calls
            for tc in response.tool_calls:
                tool_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
                tool_args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
                tool_call_id = tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", "")

                tool_fn = tool_map.get(tool_name)
                if not tool_fn:
                    tool_result = f"Unknown tool: {tool_name}"
                    logger.warning("[planner_agent] unknown tool=%s session=%s", tool_name, session_id)
                else:
                    try:
                        tool_result = await tool_fn.ainvoke(tool_args)
                    except Exception as e:
                        tool_result = f"Tool {tool_name} failed: {e}"
                        logger.warning("[planner_agent] tool %s failed: %s", tool_name, e)

                logger.debug("[planner_agent] tool=%s result_len=%d", tool_name, len(str(tool_result)))
                agent_messages.append(
                    ToolMessage(content=str(tool_result), tool_call_id=tool_call_id)
                )
        else:
            # Hit iteration limit without a final response
            logger.warning("[planner_agent] hit MAX_ITERATIONS=%d session=%s", MAX_ITERATIONS, session_id)
            if not final_response_text:
                final_response_text = "I reached my reasoning limit. Please try rephrasing your request."

        # Read the plan from state_ref (may have been updated by update_plan tool)
        draft_plan = state_ref.get("draft_plan") or existing_plan

        logger.info(
            "[planner_agent] done session=%s steps=%d response_len=%d",
            session_id, len(draft_plan), len(final_response_text),
        )

        return {
            "draft_plan": draft_plan,
            "response_message": final_response_text,
            "intent": {"intent_type": "planner_agent", "description": current_message},
        }

    return _node

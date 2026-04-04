"""
agent.py
--------
LangGraph conversational agent with persistent session history.

Architecture:
  - LLM:        OpenAI GPT-4o (configurable)
  - Memory:     LangGraph MemorySaver (in-process, keyed by session_id)
  - Tools:      8 Snowflake query tools from tools.py
  - Prompt:     Full semantic model context from semantic_model.py
  - Graph:      create_react_agent — ReAct loop (agent → tools → agent → ...)

Public API:
  chat(session_id, user_message)  -> str    (main entry point)
  reset_session(session_id)       -> None   (clear a session's history)
  get_session_history(session_id) -> list   (retrieve raw messages)
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from config import app_config
from semantic_model import SYSTEM_PROMPT
from tools import ALL_TOOLS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM setup
# ---------------------------------------------------------------------------

_llm = ChatOpenAI(
    model=app_config.openai_model,
    api_key=app_config.openai_api_key,
    temperature=0,          # Deterministic SQL / analysis outputs
    max_tokens=4096,
    streaming=False,
)

# ---------------------------------------------------------------------------
# Memory (in-process; one saver shared across all sessions)
# ---------------------------------------------------------------------------

_checkpointer = MemorySaver()

# ---------------------------------------------------------------------------
# Build the agent
# ---------------------------------------------------------------------------

_agent = create_react_agent(
    model=_llm,
    tools=ALL_TOOLS,
    state_modifier=SYSTEM_PROMPT,
    checkpointer=_checkpointer,
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def chat(session_id: str, user_message: str) -> str:
    """
    Send a message in a session and return the assistant's response.

    Session history is automatically maintained by the LangGraph checkpointer.
    Each unique session_id has its own isolated message history.

    Parameters
    ----------
    session_id : str
        A string that uniquely identifies the conversation session.
        Use a stable ID (e.g. UUID, username) so that multiple turns
        within the same conversation share history.
    user_message : str
        The human's message / question.

    Returns
    -------
    str
        The agent's final text response (after any tool calls).
    """
    config: dict[str, Any] = {"configurable": {"thread_id": session_id}}

    input_state = {"messages": [HumanMessage(content=user_message)]}

    try:
        result = _agent.invoke(input_state, config=config)
    except Exception as exc:
        logger.error("Agent error for session %s: %s", session_id, exc)
        return f"I encountered an error while processing your request: {exc}"

    # The last message in the result state is the assistant's final response
    messages: list[BaseMessage] = result.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return str(msg.content)

    return "I was unable to generate a response. Please try rephrasing your question."


def reset_session(session_id: str) -> None:
    """
    Clear all history for a given session.
    Subsequent calls to chat() with the same session_id start fresh.
    """
    # MemorySaver stores state under the thread_id key.
    # The cleanest way to reset is to write an empty state.
    config: dict[str, Any] = {"configurable": {"thread_id": session_id}}
    try:
        _checkpointer.put(
            config,
            {"v": 1, "ts": "0", "channel_values": {"messages": []}, "channel_versions": {}, "versions_seen": {}, "pending_sends": []},
            {},
            {},
        )
        logger.info("Session %s reset.", session_id)
    except Exception as exc:
        logger.warning("Could not reset session %s: %s", session_id, exc)


def get_session_history(session_id: str) -> list[dict[str, str]]:
    """
    Return the conversation history for a session as a list of
    {'role': 'human'|'assistant', 'content': '...'} dicts.
    """
    config: dict[str, Any] = {"configurable": {"thread_id": session_id}}
    try:
        checkpoint = _checkpointer.get(config)
        if checkpoint is None:
            return []
        messages: list[BaseMessage] = (
            checkpoint.get("channel_values", {}).get("messages", [])
        )
        history = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                history.append({"role": "human", "content": str(msg.content)})
            elif isinstance(msg, AIMessage):
                history.append({"role": "assistant", "content": str(msg.content)})
        return history
    except Exception as exc:
        logger.warning("Could not retrieve session history for %s: %s", session_id, exc)
        return []


# ---------------------------------------------------------------------------
# Quick smoke-test (run directly: python agent.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    TEST_SESSION = "smoke-test-001"

    questions = [
        "Give me a quick funnel summary — how many leads became prospects and how many were rejected?",
        "Why might there be a drop in prospects — what are the most common rejection reasons?",
        "What are the top SFMC engagement events recorded? Break it down by journey.",
    ]

    for q in questions:
        print(f"\n{'='*70}\nQ: {q}\n{'-'*70}")
        answer = chat(TEST_SESSION, q)
        print(f"A: {answer}")

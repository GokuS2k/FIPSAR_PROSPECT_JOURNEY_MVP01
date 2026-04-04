"""
frel_agent.py
-------------
FREL Agent — FIPSAR Report Email LangGraph Agent.

Extends the base conversational agent with email-sending capability.
The FREL agent has:
  - All 17 data + chart tools (same as the chat agent)
  - Tool 18: send_report_email — composes and sends branded HTML reports
  - Its own MemorySaver checkpointer (sessions are independent of the chat agent)
  - An extended system prompt with email workflow instructions

Public API:
  frel_chat(session_id, user_message)  -> str
  reset_frel_session(session_id)       -> None
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from config import app_config, email_config
from semantic_model import SYSTEM_PROMPT
from tools import FREL_TOOLS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Extended system prompt: base semantic model + email instructions
# ---------------------------------------------------------------------------

_EMAIL_INSTRUCTIONS = f"""

================================================================================
FREL AGENT — EMAIL REPORTING CAPABILITY
================================================================================

You are the FREL (FIPSAR Report Email) Agent. In addition to all data analysis
and charting capabilities, you can SEND REPORTS AND CHARTS BY EMAIL.

RECIPIENT: All emails go to {email_config.to_address} — always.
You do not need to ask for an email address.

WHEN THE USER ASKS TO SEND AN EMAIL (trigger phrases):
  "send me an email", "email the report", "send this over email",
  "mail me the results", "send the chart", "email me the details",
  "send a report", "email this", "forward me the analysis"

MANDATORY WORKFLOW — always follow this exact order:
  Step 1: Call the appropriate DATA TOOL(S) to retrieve the requested information.
          (get_funnel_metrics, get_rejection_analysis, trace_prospect, etc.)
  Step 2: If the user wants a chart, call the appropriate CHART TOOL(S).
          (chart_funnel, chart_rejections, chart_smart, etc.)
  Step 3: Call send_report_email LAST with:
          - subject: a clear, descriptive subject line including date range if applicable
            Example: "FIPSAR Funnel Report — January 2026"
          - report_content: the COMPLETE, well-formatted markdown report including
            all tables, metrics, insights, and interpretations from steps 1–2.
            Write it as a standalone document — the reader will see ONLY what you
            put in report_content (plus any embedded charts).

SUBJECT LINE RULES:
  - Always include the report type and date range
  - Examples: "FIPSAR Rejection Analysis — January 2026"
             "FIPSAR SFMC Engagement Report — J01 Welcome Journey"
             "FIPSAR Prospect Trace — john.doe@example.com"
             "FIPSAR Funnel Drop Analysis — January 15, 2026"

REPORT CONTENT RULES:
  - Start with a bold one-sentence executive summary
  - Use ## Section Headers to organise
  - Present metrics as bullet points with bold labels
  - Include the full data table
  - End with 2–3 sentence business interpretation
  - Do NOT include instructions about charts — they are automatically embedded

AFTER CALLING send_report_email:
  - Report the delivery status to the user
  - Mention what was included in the email (data + charts if any)
  - Do NOT ask for confirmation before sending — just send it

COMBINED REQUESTS (data + email in one message):
  If the user says "show me the funnel report and also send it over email":
  → Retrieve data, compose the full answer in your response,
    then ALSO call send_report_email with the same content.

DATA ACCURACY REMINDER:
  The same accuracy rules apply here as in the chat interface.
  NEVER put a number in the report_content without first calling a tool to retrieve it.
================================================================================
"""

FREL_SYSTEM_PROMPT: str = SYSTEM_PROMPT + _EMAIL_INSTRUCTIONS

# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

_frel_llm = ChatOpenAI(
    model=app_config.openai_model,
    api_key=app_config.openai_api_key,
    temperature=0,
    max_tokens=4096,
    streaming=False,
)

# ---------------------------------------------------------------------------
# Memory (separate from the chat agent's checkpointer)
# ---------------------------------------------------------------------------

_frel_checkpointer = MemorySaver()

# ---------------------------------------------------------------------------
# FREL Agent
# ---------------------------------------------------------------------------

_frel_agent = create_react_agent(
    model=_frel_llm,
    tools=FREL_TOOLS,
    state_modifier=FREL_SYSTEM_PROMPT,
    checkpointer=_frel_checkpointer,
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def frel_chat(session_id: str, user_message: str) -> str:
    """
    Send a message to the FREL agent and return its response.

    The agent has full access to all Snowflake data tools, chart tools,
    and the send_report_email tool. Session history is preserved per session_id.
    """
    config: dict[str, Any] = {"configurable": {"thread_id": f"frel_{session_id}"}}
    input_state = {"messages": [HumanMessage(content=user_message)]}

    try:
        result = _frel_agent.invoke(input_state, config=config)
    except Exception as exc:
        logger.error("FREL Agent error for session %s: %s", session_id, exc)
        return f"I encountered an error while processing your request: {exc}"

    messages: list[BaseMessage] = result.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return str(msg.content)

    return "I was unable to generate a response. Please try rephrasing your question."


def reset_frel_session(session_id: str) -> None:
    """Clear all conversation history for a FREL agent session."""
    config: dict[str, Any] = {"configurable": {"thread_id": f"frel_{session_id}"}}
    try:
        _frel_checkpointer.put(
            config,
            {"v": 1, "ts": "0", "channel_values": {"messages": []},
             "channel_versions": {}, "versions_seen": {}, "pending_sends": []},
            {},
            {},
        )
        logger.info("FREL session %s reset.", session_id)
    except Exception as exc:
        logger.warning("Could not reset FREL session %s: %s", session_id, exc)

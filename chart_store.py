"""
chart_store.py
--------------
Lightweight in-process store that lets LangChain tools queue Plotly figures
during an agent turn, which app.py then renders after chat() returns.

Usage:
    # In app.py before calling chat():
    chart_store.set_session(session_id)

    # In any tool:
    chart_store.push(fig)

    # In app.py after chat() returns:
    for fig in chart_store.pop_all(session_id):
        st.plotly_chart(fig, use_container_width=True)
"""

from __future__ import annotations
from collections import defaultdict

# Active session being served right now (set by app.py before each chat() call)
_active_session: str = "default"

# session_id -> list of plotly Figure objects
_queue: dict[str, list] = defaultdict(list)


def set_session(session_id: str) -> None:
    """Call this from app.py immediately before invoking chat()."""
    global _active_session
    _active_session = session_id


def push(fig) -> None:
    """Queue a Plotly figure for the current active session."""
    _queue[_active_session].append(fig)


def pop_all(session_id: str) -> list:
    """Return and clear all queued figures for a session."""
    return _queue.pop(session_id, [])


def peek_all_current() -> list:
    """
    Return queued figures for the current active session WITHOUT removing them.
    Used by the email tool to embed charts in the email while still leaving
    them in the queue for app.py to render inline in the UI.
    """
    return list(_queue.get(_active_session, []))

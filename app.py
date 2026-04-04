"""
app.py
------
Streamlit UI for FIPSAR Prospect Journey Intelligence.

Four tabs (in order):
  📊 Analytics      — live KPI dashboard with filters (FIRST tab)
  💬 Chat           — multi-turn text chat
  🎤 Voice Assistant — recorder at bottom, conversation scrolls above
  📧 FREL Agent     — chat + email reports

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import uuid
import logging

import streamlit as st
import streamlit.components.v1 as components

# Must be the first Streamlit command
st.set_page_config(
    page_title="FIPSAR Prospect Journey Intelligence",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

from snowflake_connector import test_connection
from agent import chat, reset_session
from frel_agent import frel_chat, reset_frel_session
import chart_store
from voice_assistant import transcribe_audio, text_to_speech
from config import email_config
from email_sender import test_email_connection, send_email
from analytics_dashboard import render_analytics_dashboard

logging.basicConfig(level=logging.WARNING)

# ===========================================================================
# GLOBAL CSS — applied once, covers all tabs and sidebar
# ===========================================================================

st.markdown("""
<style>
/* ── Fonts & base ──────────────────────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: 'Inter', 'Segoe UI', Arial, sans-serif;
}
.block-container {
    padding-top: 1.2rem !important;
    padding-bottom: 2rem !important;
    max-width: 1420px;
}

/* ── Page background ───────────────────────────────────────────────────── */
[data-testid="stMain"] {
    background-color: #f4f6fb;
}
[data-testid="stMain"] > div {
    background-color: #f4f6fb;
}

/* ── Sidebar ───────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: linear-gradient(175deg, #0b2151 0%, #1a3f8f 60%, #1a4a9e 100%) !important;
    border-right: none !important;
}
[data-testid="stSidebar"] > div {
    background: transparent !important;
}
/* All sidebar text */
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] small,
[data-testid="stSidebar"] li {
    color: #cdd8f0 !important;
}
[data-testid="stSidebar"] h1 {
    color: #ffffff !important;
    font-size: 1.15rem !important;
    font-weight: 800 !important;
    letter-spacing: 0.3px;
}
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: #8fb4e8 !important;
    font-size: 0.72rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 1.2px !important;
}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
    color: #7a9fd4 !important;
    font-size: 0.73rem !important;
}
[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.14) !important;
    margin: 10px 0 !important;
}
/* Sidebar buttons */
[data-testid="stSidebar"] .stButton > button {
    background: rgba(255,255,255,0.10) !important;
    color: #dde8fc !important;
    border: 1px solid rgba(255,255,255,0.22) !important;
    border-radius: 8px !important;
    font-size: 0.76rem !important;
    font-weight: 600 !important;
    padding: 6px 10px !important;
    transition: background 0.2s, border-color 0.2s !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,0.20) !important;
    border-color: rgba(255,255,255,0.40) !important;
    color: #ffffff !important;
}
/* Sidebar expanders */
[data-testid="stSidebar"] [data-testid="stExpander"] {
    background: rgba(255,255,255,0.07) !important;
    border: 1px solid rgba(255,255,255,0.13) !important;
    border-radius: 8px !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] summary {
    color: #c0d4f0 !important;
    font-size: 0.78rem !important;
}
/* Sidebar expander button rows */
[data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button {
    background: rgba(255,255,255,0.06) !important;
    font-size: 0.73rem !important;
    text-align: left !important;
    padding: 5px 8px !important;
    border-radius: 6px !important;
    white-space: normal !important;
    height: auto !important;
    line-height: 1.3 !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button:hover {
    background: rgba(255,255,255,0.18) !important;
}
/* Sidebar success/error/info/warning */
[data-testid="stSidebar"] [data-testid="stAlert"] {
    background: rgba(255,255,255,0.09) !important;
    border-radius: 8px !important;
    border-left: 3px solid rgba(255,255,255,0.4) !important;
}

/* ── Sticky tab bar ─────────────────────────────────────────────────────── */
[data-testid="stTabs"] > div:first-child {
    position: sticky;
    top: 0;
    z-index: 999;
    background-color: #f4f6fb !important;
    padding: 10px 0 0 0;
    box-shadow: 0 3px 10px rgba(0,0,0,0.08);
}
/* Tab list pill container */
[data-baseweb="tab-list"] {
    background: #ffffff !important;
    border-radius: 14px !important;
    padding: 5px !important;
    gap: 3px !important;
    box-shadow: 0 2px 10px rgba(13,42,94,0.10) !important;
    border: 1px solid #e8ecf4 !important;
}
[data-baseweb="tab"] {
    background: transparent !important;
    border-radius: 10px !important;
    padding: 9px 22px !important;
    font-weight: 600 !important;
    font-size: 0.83rem !important;
    color: #64748b !important;
    border: none !important;
    transition: all 0.18s ease !important;
}
[data-baseweb="tab"]:hover {
    background: #f0f4ff !important;
    color: #1a3a6b !important;
}
[aria-selected="true"][data-baseweb="tab"] {
    background: linear-gradient(135deg, #0d2a5e 0%, #1a4a9e 100%) !important;
    color: #ffffff !important;
    box-shadow: 0 2px 8px rgba(13,42,94,0.30) !important;
}
[data-baseweb="tab-highlight"] {
    background-color: transparent !important;
    height: 0 !important;
}
[data-baseweb="tab-border"] {
    display: none !important;
}

/* ── Chat messages ──────────────────────────────────────────────────────── */
[data-testid="stChatMessage"] {
    border-radius: 14px !important;
    box-shadow: 0 2px 10px rgba(13,42,94,0.07) !important;
    margin: 4px 0 10px 0 !important;
    border: 1px solid #e8ecf4 !important;
    background: #ffffff !important;
    padding: 4px 8px !important;
}

/* ── Chat input ─────────────────────────────────────────────────────────── */
[data-testid="stChatInput"] {
    border-radius: 14px !important;
    box-shadow: 0 2px 12px rgba(13,42,94,0.10) !important;
    border: 1.5px solid #dde4f0 !important;
    background: #ffffff !important;
}
[data-testid="stChatInput"]:focus-within {
    border-color: #1a4a9e !important;
    box-shadow: 0 0 0 3px rgba(26,74,158,0.10), 0 2px 12px rgba(13,42,94,0.10) !important;
}

/* ── Main area buttons ──────────────────────────────────────────────────── */
.stButton > button {
    border-radius: 9px !important;
    font-weight: 600 !important;
    font-size: 0.82rem !important;
    transition: all 0.18s ease !important;
    padding: 6px 14px !important;
}

/* ── Plotly chart wrapper ───────────────────────────────────────────────── */
[data-testid="stPlotlyChart"] {
    background: #ffffff !important;
    border-radius: 14px !important;
    box-shadow: 0 2px 14px rgba(13,42,94,0.08) !important;
    border: 1px solid #e8ecf4 !important;
    padding: 6px !important;
}

/* ── Expanders ──────────────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    border-radius: 10px !important;
    border: 1px solid #e2e8f0 !important;
    background: #ffffff !important;
}

/* ── Info / success / warning / error alerts ────────────────────────────── */
[data-testid="stAlert"] {
    border-radius: 10px !important;
}
[data-testid="stAlert"][kind="info"] {
    background: #eff6ff !important;
    border-color: #bfdbfe !important;
}
[data-testid="stAlert"][kind="success"] {
    background: #f0fdf4 !important;
    border-color: #bbf7d0 !important;
}
[data-testid="stAlert"][kind="warning"] {
    background: #fffbeb !important;
    border-color: #fde68a !important;
}

/* ── Dividers ───────────────────────────────────────────────────────────── */
[data-testid="stHorizontalBlock"] hr {
    border-color: #e2e8f0 !important;
    margin: 8px 0 !important;
}

/* ── Custom scrollbar ───────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: #f1f5f9; border-radius: 8px; }
::-webkit-scrollbar-thumb { background: #94a3b8; border-radius: 8px; }
::-webkit-scrollbar-thumb:hover { background: #64748b; }

/* ── Spinner text ───────────────────────────────────────────────────────── */
[data-testid="stSpinner"] > div {
    color: #1a4a9e !important;
}

/* ── Select boxes & date inputs ─────────────────────────────────────────── */
[data-testid="stSelectbox"] > div > div,
[data-testid="stDateInput"] > div > div {
    border-radius: 9px !important;
    border-color: #dde4f0 !important;
}
</style>
""", unsafe_allow_html=True)


# ===========================================================================
# Shared UI helpers  (defined before tabs so every tab can call them)
# ===========================================================================

def _render_email_badge(meta: dict) -> None:
    """Render the green 'EMAIL SENT' confirmation card."""
    charts_note = (
        f" · {meta.get('charts_attached', 0)} chart(s) embedded"
        if meta.get("charts_attached", 0) > 0 else ""
    )
    st.markdown(
        f"""<div style="background:linear-gradient(135deg,#0a2e1a 0%,#16532e 100%);
        border:1px solid #22c55e;border-radius:12px;padding:16px 20px;margin-top:12px;
        box-shadow:0 4px 16px rgba(22,101,52,0.25)">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
            <span style="font-size:1.1rem">✅</span>
            <span style="color:#4ade80;font-size:0.82rem;font-weight:700;
                         text-transform:uppercase;letter-spacing:0.8px">
                Email Sent Successfully
            </span>
        </div>
        <div style="color:#bbf7d0;font-size:0.88rem;line-height:1.7">
            <b style="color:#86efac">To:</b> {meta.get("to", "")}<br>
            <b style="color:#86efac">Subject:</b> {meta.get("subject", "FIPSAR Report")}<br>
            <b style="color:#86efac">Sent at:</b> {meta.get("sent_at", "")}{charts_note}
        </div></div>""",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Auto-scroll helper
# ---------------------------------------------------------------------------

_SCROLL_JS = """
<script>
setTimeout(function() {
    var doc = window.parent.document;
    var main = doc.querySelector('section[data-testid="stMain"]')
             || doc.querySelector('[data-testid="stMain"]')
             || doc.querySelector('section.main')
             || doc.querySelector('.main');
    if (main) { main.scrollTop = main.scrollHeight; }
    doc.querySelectorAll('[data-testid="stVerticalBlockBorderWrapper"]')
       .forEach(function(c) { c.scrollTop = c.scrollHeight; });
    window.parent.scrollTo(0, 99999);
}, 120);
</script>
"""

def _scroll_to_bottom() -> None:
    components.html(_SCROLL_JS, height=0, scrolling=False)


# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []
if "snowflake_ok" not in st.session_state:
    st.session_state.snowflake_ok = None

# Voice
if "voice_session_id" not in st.session_state:
    st.session_state.voice_session_id = str(uuid.uuid4())
if "voice_messages" not in st.session_state:
    st.session_state.voice_messages = []
if "last_audio_key" not in st.session_state:
    st.session_state.last_audio_key = None

# FREL Agent
if "frel_session_id" not in st.session_state:
    st.session_state.frel_session_id = str(uuid.uuid4())
if "frel_messages" not in st.session_state:
    st.session_state.frel_messages = []
if "email_test_result" not in st.session_state:
    st.session_state.email_test_result = None


# ===========================================================================
# SIDEBAR
# ===========================================================================

with st.sidebar:
    # Brand header
    st.markdown("""
    <div style="text-align:center;padding:12px 0 16px">
        <div style="font-size:1.6rem;margin-bottom:4px">📊</div>
        <div style="font-size:1.1rem;font-weight:800;color:#ffffff;letter-spacing:0.4px">
            FIPSAR Intelligence
        </div>
        <div style="font-size:0.71rem;color:#7fa8d8;margin-top:3px;letter-spacing:0.3px">
            Prospect Journey AI · LangGraph + Snowflake
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # ── Snowflake connection ──────────────────────────────────────────────
    st.markdown("""<div style="font-size:0.72rem;font-weight:700;color:#8fb4e8;
        text-transform:uppercase;letter-spacing:1.2px;margin-bottom:8px">
        🔌 Connection Status</div>""", unsafe_allow_html=True)

    if st.button("Test Snowflake Connection", use_container_width=True):
        with st.spinner("Connecting..."):
            st.session_state.snowflake_ok = test_connection()

    if st.session_state.snowflake_ok is True:
        st.markdown("""<div style="background:rgba(34,197,94,0.15);border:1px solid rgba(34,197,94,0.4);
            border-radius:8px;padding:7px 12px;font-size:0.78rem;color:#4ade80;font-weight:600;
            display:flex;align-items:center;gap:6px;margin-top:4px">
            <span>●</span> Snowflake Connected</div>""", unsafe_allow_html=True)
    elif st.session_state.snowflake_ok is False:
        st.markdown("""<div style="background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.4);
            border-radius:8px;padding:7px 12px;font-size:0.78rem;color:#f87171;font-weight:600;
            display:flex;align-items:center;gap:6px;margin-top:4px">
            <span>●</span> Connection Failed</div>""", unsafe_allow_html=True)
    else:
        st.markdown("""<div style="background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.14);
            border-radius:8px;padding:7px 12px;font-size:0.77rem;color:#93b8e0;margin-top:4px">
            Click above to test connection</div>""", unsafe_allow_html=True)

    st.divider()

    # ── Email status ──────────────────────────────────────────────────────
    st.markdown("""<div style="font-size:0.72rem;font-weight:700;color:#8fb4e8;
        text-transform:uppercase;letter-spacing:1.2px;margin-bottom:6px">
        📧 Email (FREL Agent)</div>""", unsafe_allow_html=True)

    st.markdown(
        f"""<div style="font-size:0.73rem;color:#93b8e0;margin-bottom:8px">
        Recipient: <span style="color:#c0d4f0;font-family:monospace">{email_config.to_address}</span>
        </div>""",
        unsafe_allow_html=True,
    )

    col_etest, col_esend = st.columns(2)
    with col_etest:
        if st.button("Test SMTP", use_container_width=True, key="test_smtp"):
            with st.spinner("Testing..."):
                st.session_state.email_test_result = test_email_connection()
    with col_esend:
        if st.button("Send Test", use_container_width=True, key="send_test_email"):
            with st.spinner("Sending..."):
                st.session_state.email_test_result = send_email(
                    subject="FIPSAR Intelligence — Email Test",
                    report_markdown=(
                        "## Connection Test\n\nThis is a test email from FIPSAR Intelligence.\n\n"
                        "Your email configuration is working correctly.\n\n"
                        "- **SMTP Host:** " + email_config.smtp_host + "\n"
                        "- **From:** " + (email_config.from_address or email_config.smtp_user) + "\n"
                        "- **To:** " + email_config.to_address
                    ),
                )

    if st.session_state.email_test_result is not None:
        r = st.session_state.email_test_result
        if r.get("success"):
            st.markdown(
                f"""<div style="background:rgba(34,197,94,0.12);border:1px solid rgba(34,197,94,0.35);
                border-radius:8px;padding:7px 10px;font-size:0.73rem;color:#4ade80;margin-top:6px">
                ✅ {r["message"][:80]}</div>""",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""<div style="background:rgba(239,68,68,0.12);border:1px solid rgba(239,68,68,0.35);
                border-radius:8px;padding:7px 10px;font-size:0.73rem;color:#f87171;margin-top:6px">
                ⚠️ {r["message"][:100]}</div>""",
                unsafe_allow_html=True,
            )
            with st.expander("Gmail App Password guide", expanded=False):
                st.markdown(
                    "1. myaccount.google.com → Security → 2-Step Verification\n"
                    "2. App Passwords → App: Mail · Device: Other → name `FIPSAR`\n"
                    "3. Copy 16-char code → paste as `EMAIL_SMTP_PASSWORD` in `.env`\n"
                    "4. Restart app → click Test SMTP"
                )

    st.divider()

    # ── Sessions ──────────────────────────────────────────────────────────
    st.markdown("""<div style="font-size:0.72rem;font-weight:700;color:#8fb4e8;
        text-transform:uppercase;letter-spacing:1.2px;margin-bottom:8px">
        🔄 Sessions</div>""", unsafe_allow_html=True)

    st.markdown(
        f"""<div style="font-size:0.71rem;color:#7fa8d8;line-height:1.9;margin-bottom:8px">
        💬 Chat: <code style="color:#a8c8f0;background:rgba(255,255,255,0.08);
        padding:1px 5px;border-radius:4px">{st.session_state.session_id[:8]}…</code><br>
        🎤 Voice: <code style="color:#a8c8f0;background:rgba(255,255,255,0.08);
        padding:1px 5px;border-radius:4px">{st.session_state.voice_session_id[:8]}…</code><br>
        📧 FREL: <code style="color:#a8c8f0;background:rgba(255,255,255,0.08);
        padding:1px 5px;border-radius:4px">{st.session_state.frel_session_id[:8]}…</code>
        </div>""",
        unsafe_allow_html=True,
    )

    col_new, col_clear = st.columns(2)
    with col_new:
        if st.button("New Session", use_container_width=True):
            for key in ["session_id", "voice_session_id", "frel_session_id"]:
                st.session_state[key] = str(uuid.uuid4())
            st.session_state.messages = []
            st.session_state.voice_messages = []
            st.session_state.frel_messages = []
            st.session_state.last_audio_key = None
            st.rerun()
    with col_clear:
        if st.button("Clear All", use_container_width=True):
            reset_session(st.session_state.session_id)
            reset_frel_session(st.session_state.frel_session_id)
            st.session_state.messages = []
            st.session_state.voice_messages = []
            st.session_state.frel_messages = []
            st.session_state.last_audio_key = None
            st.rerun()

    st.divider()

    # ── Sample questions ──────────────────────────────────────────────────
    st.markdown("""<div style="font-size:0.72rem;font-weight:700;color:#8fb4e8;
        text-transform:uppercase;letter-spacing:1.2px;margin-bottom:8px">
        💡 Sample Questions</div>""", unsafe_allow_html=True)
    st.markdown("""<div style="font-size:0.71rem;color:#7fa8d8;margin-bottom:6px">
        Sends to the 💬 Chat tab.</div>""", unsafe_allow_html=True)

    SAMPLE_QUESTIONS: dict[str, list[str]] = {
        "📈 Funnel & Drop Analysis": [
            "Give me a full funnel summary — leads to prospects to engagement.",
            "Show me the funnel chart for all time.",
            "Why is there a volume drop? What are the top rejection reasons?",
            "Show me the lead-to-prospect conversion rate.",
        ],
        "❌ Rejections & DQ": [
            "Who got dropped and why? List all rejection reasons.",
            "Show me a chart of rejection reasons.",
            "How many NULL_EMAIL rejections are there?",
            "What are the SUPPRESSED and FATAL_ERROR patterns?",
        ],
        "📧 SFMC Journey & Events": [
            "What are the SFMC event counts broken down by journey?",
            "Show me an SFMC engagement chart.",
            "How is the Welcome journey performing?",
            "Which journey stage has the highest bounce rate?",
        ],
        "🔍 Prospect Trace": [
            "Trace prospect with email john.doe@example.com through the pipeline.",
            "Show me the journey history for MASTER_PATIENT_ID P001.",
        ],
        "🤖 AI & Scores": [
            "What is the conversion and drop-off probability for active prospects?",
            "Show me a conversion segment chart.",
            "Which prospects are at risk of dropping off?",
        ],
        "📅 Trends": [
            "Show me the monthly intake trend for 2026.",
            "Plot weekly lead and prospect volume for January 2026.",
        ],
        "🔬 Observability": [
            "Show pipeline run health for the last 30 days.",
            "Are there any data quality issues I should know about?",
        ],
    }

    for category, questions in SAMPLE_QUESTIONS.items():
        with st.expander(category, expanded=False):
            for q in questions:
                if st.button(q, key=f"sample_{q[:30]}", use_container_width=True):
                    st.session_state.messages.append({"role": "user", "content": q})
                    with st.spinner("Thinking..."):
                        chart_store.set_session(st.session_state.session_id)
                        response = chat(st.session_state.session_id, q)
                    pending_charts = chart_store.pop_all(st.session_state.session_id)
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": response,
                        "charts": pending_charts,
                    })
                    st.rerun()


# ===========================================================================
# Four tabs
# ===========================================================================

tab_analytics, tab_chat, tab_voice, tab_frel = st.tabs([
    "📊  Analytics", "💬  Chat", "🎤  Voice Assistant", "📧  FREL Agent"
])


# ===========================================================================
# TAB 1 — ANALYTICS DASHBOARD
# ===========================================================================

with tab_analytics:
    render_analytics_dashboard()


# ===========================================================================
# TAB 2 — CHAT
# ===========================================================================

with tab_chat:

    # Page header
    st.markdown("""
    <div style="background:linear-gradient(135deg,#0d2a5e 0%,#1a4a9e 100%);
         border-radius:16px;padding:22px 28px;margin-bottom:20px;
         box-shadow:0 4px 20px rgba(13,42,94,0.22)">
        <div style="display:flex;align-items:center;gap:14px">
            <div style="font-size:2rem">💬</div>
            <div>
                <div style="font-size:1.25rem;font-weight:800;color:#ffffff;letter-spacing:0.3px">
                    Prospect Journey Intelligence
                </div>
                <div style="font-size:0.82rem;color:#a8c4f0;margin-top:3px">
                    Ask anything about lead intake · prospect mastering · SFMC journeys ·
                    engagement events · data quality · AI scores · funnel drop-offs
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Message history
    chat_container = st.container()
    with chat_container:
        if not st.session_state.messages:
            st.markdown("""
            <div style="text-align:center;padding:50px 20px 40px;color:#94a3b8">
                <div style="font-size:3rem;margin-bottom:12px">🧠</div>
                <div style="font-size:1rem;font-weight:600;color:#64748b;margin-bottom:6px">
                    No conversation yet
                </div>
                <div style="font-size:0.85rem;max-width:420px;margin:0 auto;line-height:1.6">
                    Type a question below or pick one from the
                    <b>Sample Questions</b> panel in the sidebar.
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            for msg in st.session_state.messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
                    for fig in msg.get("charts", []):
                        st.plotly_chart(fig, use_container_width=True)

    # Sticky chat input
    if user_input := st.chat_input("Ask about your prospect journey data…", key="chat_input"):
        st.session_state.messages.append({"role": "user", "content": user_input})
        with chat_container:
            with st.chat_message("user"):
                st.markdown(user_input)
            with st.chat_message("assistant"):
                with st.spinner("Querying Snowflake and reasoning…"):
                    chart_store.set_session(st.session_state.session_id)
                    response = chat(st.session_state.session_id, user_input)
                st.markdown(response)
                pending_charts = chart_store.pop_all(st.session_state.session_id)
                for fig in pending_charts:
                    st.plotly_chart(fig, use_container_width=True)

        st.session_state.messages.append({
            "role": "assistant",
            "content": response,
            "charts": pending_charts,
        })
        _scroll_to_bottom()

    # Footer
    st.markdown("""
    <div style="text-align:center;margin-top:12px">
        <span style="font-size:0.73rem;color:#94a3b8">
            FIPSAR Prospect Journey Intelligence &nbsp;·&nbsp;
            Data: Snowflake &nbsp;·&nbsp; AI: GPT-4o via LangGraph
        </span>
    </div>
    """, unsafe_allow_html=True)


# ===========================================================================
# TAB 3 — VOICE ASSISTANT
# ===========================================================================

with tab_voice:

    # Header
    st.markdown("""
    <div style="background:linear-gradient(135deg,#1a1a3e 0%,#2d2d6b 100%);
         border-radius:16px;padding:20px 26px;margin-bottom:18px;
         box-shadow:0 4px 18px rgba(26,26,62,0.30)">
        <div style="display:flex;align-items:center;gap:14px">
            <div style="font-size:2rem">🎤</div>
            <div>
                <div style="font-size:1.15rem;font-weight:800;color:#ffffff">
                    Voice Assistant
                </div>
                <div style="font-size:0.8rem;color:#a0a8d8;margin-top:3px">
                    Speak your question — transcribed by Whisper · answered · read back as audio
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    _, col_vclear = st.columns([5, 1])
    with col_vclear:
        if st.button("🗑 Clear", use_container_width=True, key="voice_clear"):
            st.session_state.voice_session_id = str(uuid.uuid4())
            st.session_state.voice_messages = []
            st.session_state.last_audio_key = None
            st.rerun()

    st.divider()

    # Conversation history
    n_msgs = len(st.session_state.voice_messages)
    box_height = min(120 + n_msgs * 80, 520)
    voice_box = st.container(height=box_height, border=False)

    with voice_box:
        if st.session_state.voice_messages:
            for msg in st.session_state.voice_messages:
                if msg["role"] == "user":
                    st.markdown(
                        f"""<div style="background:linear-gradient(135deg,#1e3a5f,#1a2e4a);
                        border-left:4px solid #60a5fa;border-radius:12px;
                        padding:12px 16px;margin:8px 0;
                        box-shadow:0 2px 8px rgba(30,58,95,0.30)">
                        <div style="color:#93c5fd;font-size:0.72rem;font-weight:700;
                             text-transform:uppercase;letter-spacing:0.8px;margin-bottom:6px">
                            🎙 You Said
                        </div>
                        <div style="color:#dbeafe;font-size:0.92rem;line-height:1.5">
                            {msg["content"]}
                        </div></div>""",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        """<div style="background:linear-gradient(135deg,#0f2d1f,#14402a);
                        border-left:4px solid #4ade80;border-radius:12px;
                        padding:10px 16px 6px;margin:6px 0 2px;
                        box-shadow:0 2px 8px rgba(15,45,31,0.30)">
                        <div style="color:#86efac;font-size:0.72rem;font-weight:700;
                             text-transform:uppercase;letter-spacing:0.8px">
                            🤖 FIPSAR AI
                        </div></div>""",
                        unsafe_allow_html=True,
                    )
                    with st.expander("View response", expanded=True):
                        st.markdown(msg["content"])
                    if msg.get("audio"):
                        st.audio(msg["audio"], format="audio/mp3", autoplay=False)
                    else:
                        st.warning("Audio unavailable for this response.")
                    for fig in msg.get("charts", []):
                        st.plotly_chart(fig, use_container_width=True)
        else:
            st.markdown("""
            <div style="text-align:center;padding:40px 20px;color:#64748b">
                <div style="font-size:3rem;margin-bottom:10px">🎤</div>
                <div style="font-size:0.9rem;font-weight:600;color:#475569">
                    Your conversation will appear here
                </div>
                <div style="font-size:0.8rem;margin-top:6px;color:#94a3b8">
                    Record your question using the microphone below
                </div>
            </div>
            """, unsafe_allow_html=True)

    # Recorder section
    st.divider()

    with st.expander("⚙️ Voice Settings", expanded=False):
        voice_choice = st.selectbox(
            "AI Response Voice",
            ["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
            index=0,
        )
        speech_speed = st.slider("Playback Speed", 0.75, 1.5, 1.0, 0.25)

    audio_input = st.audio_input(
        "🎙 Click to start recording · click again to stop · response appears above",
        key="voice_recorder",
    )

    st.markdown("""<div style="text-align:center;margin-top:6px">
        <span style="font-size:0.71rem;color:#94a3b8">
            Whisper (transcription) · FIPSAR LangGraph Agent · gpt-4o-mini-tts
        </span></div>""", unsafe_allow_html=True)

    # Process new recording
    if audio_input is not None:
        audio_bytes = audio_input.read()
        audio_hash = hash(audio_bytes)

        if st.session_state.last_audio_key != audio_hash:
            st.session_state.last_audio_key = audio_hash

            with st.spinner("Transcribing…"):
                transcript = transcribe_audio(audio_bytes)

            if not transcript:
                st.error("Could not transcribe. Please try again.")
            else:
                st.session_state.voice_messages.append({
                    "role": "user", "content": transcript, "audio": None, "charts": [],
                })

                with st.spinner("Querying Snowflake and reasoning…"):
                    chart_store.set_session(st.session_state.voice_session_id)
                    ai_response = chat(st.session_state.voice_session_id, transcript)
                pending_charts = chart_store.pop_all(st.session_state.voice_session_id)

                with st.spinner("Generating audio…"):
                    response_audio = text_to_speech(
                        ai_response, voice=voice_choice, speed=speech_speed,
                    )

                st.session_state.voice_messages.append({
                    "role": "assistant",
                    "content": ai_response,
                    "audio": response_audio,
                    "charts": pending_charts,
                })
                st.rerun()

    _scroll_to_bottom()


# ===========================================================================
# TAB 4 — FREL AGENT
# ===========================================================================

with tab_frel:

    # Header
    st.markdown(
        f"""<div style="background:linear-gradient(135deg,#1a0a2e 0%,#3d1a6e 100%);
        border-radius:16px;padding:22px 28px;margin-bottom:18px;
        box-shadow:0 4px 20px rgba(61,26,110,0.30)">
        <div style="display:flex;align-items:center;justify-content:space-between">
            <div style="display:flex;align-items:center;gap:14px">
                <div style="font-size:2rem">📧</div>
                <div>
                    <div style="font-size:1.2rem;font-weight:800;color:#ffffff">
                        FREL Agent
                    </div>
                    <div style="font-size:0.8rem;color:#c4a8f8;margin-top:3px">
                        Full data intelligence + one-click email delivery ·
                        Say <b style="color:#e9d5ff">"send it over email"</b>
                        → report goes to <b style="color:#e9d5ff">{email_config.to_address}</b>
                    </div>
                </div>
            </div>
        </div></div>""",
        unsafe_allow_html=True,
    )

    col_info, col_fclr = st.columns([4, 1])
    with col_info:
        if email_config.is_configured:
            st.markdown(
                f"""<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;
                padding:9px 14px;font-size:0.82rem;color:#166534;display:flex;align-items:center;gap:8px">
                <span style="font-size:1rem">✅</span>
                Email ready · Reports sent to <b>{email_config.to_address}</b>
                </div>""",
                unsafe_allow_html=True,
            )
        else:
            st.markdown("""<div style="background:#fffbeb;border:1px solid #fde68a;border-radius:10px;
                padding:9px 14px;font-size:0.82rem;color:#92400e;display:flex;align-items:center;gap:8px">
                <span>⚠️</span> Email not configured — check sidebar.
                </div>""", unsafe_allow_html=True)
    with col_fclr:
        if st.button("🗑 Clear", use_container_width=True, key="frel_clear"):
            reset_frel_session(st.session_state.frel_session_id)
            st.session_state.frel_session_id = str(uuid.uuid4())
            st.session_state.frel_messages = []
            st.rerun()

    st.divider()

    with st.expander("💡 Example requests", expanded=False):
        st.markdown(
            """
| Request | What happens |
|---|---|
| `Send me the funnel report for January 2026` | Queries → emails full report |
| `Email me the rejection analysis with a chart` | Queries + chart → emails with embedded image |
| `Send the SFMC journey performance report` | Queries all journeys → emails table |
| `Email details about prospect john.doe@example.com` | Traces → emails report |
| `Give me the conversion analysis and email it` | Shows in UI + emails |
            """
        )

    # Message history
    frel_container = st.container()
    with frel_container:
        if not st.session_state.frel_messages:
            st.markdown(
                f"""<div style="text-align:center;padding:50px 20px;color:#94a3b8">
                <div style="font-size:3rem;margin-bottom:12px">📬</div>
                <div style="font-size:1rem;font-weight:600;color:#64748b;margin-bottom:6px">
                    Ready to assist
                </div>
                <div style="font-size:0.85rem;max-width:440px;margin:0 auto;line-height:1.6">
                    Ask any question about your prospect data.<br>
                    Say <b>"send it over email"</b> and the full report
                    will be delivered to <b>{email_config.to_address}</b>.
                </div></div>""",
                unsafe_allow_html=True,
            )
        else:
            for msg in st.session_state.frel_messages:
                if msg["role"] == "user":
                    with st.chat_message("user"):
                        st.markdown(msg["content"])
                else:
                    with st.chat_message("assistant"):
                        st.markdown(msg["content"])
                        if msg.get("email_sent") and msg.get("email_meta"):
                            _render_email_badge(msg["email_meta"])
                        for fig in msg.get("charts", []):
                            st.plotly_chart(fig, use_container_width=True)

    # Sticky chat input
    if frel_input := st.chat_input(
        "Ask a question or say 'send me the funnel report over email'…",
        key="frel_input",
    ):
        st.session_state.frel_messages.append({"role": "user", "content": frel_input})
        with frel_container:
            with st.chat_message("user"):
                st.markdown(frel_input)

            with st.chat_message("assistant"):
                with st.spinner("Analysing data and preparing report…"):
                    chart_store.set_session(st.session_state.frel_session_id)
                    frel_response = frel_chat(st.session_state.frel_session_id, frel_input)

                pending_charts = chart_store.pop_all(st.session_state.frel_session_id)
                st.markdown(frel_response)

                email_sent = (
                    "✅ Email sent successfully" in frel_response
                    or "email sent" in frel_response.lower()
                )
                email_meta = None
                if email_sent:
                    import re
                    from datetime import datetime as _dt
                    sm = re.search(r"Subject:\s*['\"]?([^\n'\"]+)", frel_response)
                    tm = re.search(r"To:\s*([^\s\n]+@[^\s\n]+)", frel_response)
                    cm = re.search(r"(\d+)\s+chart", frel_response)
                    email_meta = {
                        "to": tm.group(1) if tm else email_config.to_address,
                        "subject": sm.group(1).strip() if sm else "FIPSAR Report",
                        "sent_at": _dt.now().strftime("%B %d, %Y  %I:%M %p"),
                        "charts_attached": int(cm.group(1)) if cm else 0,
                    }
                    _render_email_badge(email_meta)

                for fig in pending_charts:
                    st.plotly_chart(fig, use_container_width=True)

        st.session_state.frel_messages.append({
            "role": "assistant",
            "content": frel_response,
            "charts": pending_charts,
            "email_sent": email_sent,
            "email_meta": email_meta,
        })
        _scroll_to_bottom()

    # Footer
    st.markdown(
        f"""<div style="text-align:center;margin-top:12px">
        <span style="font-size:0.73rem;color:#94a3b8">
            FREL Agent · 18 tools · Reports sent to {email_config.to_address}
        </span></div>""",
        unsafe_allow_html=True,
    )

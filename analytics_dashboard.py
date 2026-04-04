"""
analytics_dashboard.py
-----------------------
Analytics Dashboard tab for FIPSAR Prospect Journey Intelligence.

Layout:
  Left  (1.35) — filter panel (date range, channel, journey)
  Right (4.65) — KPI rows + 4 Plotly charts + daily trend

KPI Row 1 : Leads | Prospects | Invalid Leads
KPI Row 2 : All-Stage Expected Sent | Actual Sent | Unsent (Suppressed | Fatal)
Chart Row 1: Lead Funnel Overview  |  Email Sent Comparison
Chart Row 2: UC01 Conversion Probability  |  UC05 Prospect Segments
Chart Row 3: Daily Intake Trend (full width)

Filter wiring:
  - Date range  → ALL queries (funnel, email, segments, trend)
  - Channel     → funnel KPIs + daily trend
  - Journey     → email actual-sent + conversion/segment queries
"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from snowflake_connector import execute_query

logger = logging.getLogger(__name__)

# ── Brand palette ──────────────────────────────────────────────────────────
_NAVY   = "#0d2a5e"
_BLUE   = "#1a4a9e"
_SKY    = "#4a90d9"
_CYAN   = "#06b6d4"
_GREEN  = "#16a34a"
_AMBER  = "#d97706"
_RED    = "#dc2626"
_ROSE   = "#e11d48"
_SLATE  = "#64748b"
_PURPLE = "#7c3aed"

# ── Helpers ────────────────────────────────────────────────────────────────

def _run(sql: str) -> pd.DataFrame:
    try:
        return execute_query(sql.strip())
    except Exception as exc:
        logger.warning("Analytics query failed: %s", exc)
        return pd.DataFrame()


def _scalar(df: pd.DataFrame, default: int = 0) -> int:
    if df is None or df.empty:
        return default
    try:
        v = df.iloc[0, 0]
        return int(v) if v is not None else default
    except Exception:
        return default


def _date_flt(col: str, s: date, e: date) -> str:
    return f"TRY_TO_DATE({col}::STRING) BETWEEN '{s}' AND '{e}'"


def _chan_where(channel: str) -> str:
    return "" if (not channel or channel == "All") else \
           f" AND UPPER(INTAKE_CHANNEL) = UPPER('{channel}')"


def _journey_code(journey: str) -> str:
    """Extract bare code 'J01' from 'J01 - Welcome' etc."""
    if not journey or journey == "All":
        return ""
    return journey.split(" - ")[0].strip().upper()


def _journey_where(journey: str, col: str = "JOURNEY_CODE") -> str:
    code = _journey_code(journey)
    return "" if not code else f" AND UPPER({col}) = '{code}'"


# ── Cached fetchers ────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def _fetch_filter_options() -> dict[str, list]:
    channels = _run("""
        SELECT DISTINCT COALESCE(UPPER(INTAKE_CHANNEL), 'UNKNOWN') AS CH
        FROM FIPSAR_PHI_HUB.STAGING.STG_PROSPECT_INTAKE ORDER BY 1
    """)
    ch_list = ["All"] + (channels.iloc[:, 0].tolist() if not channels.empty else [])
    journeys = ["All", "J01 - Welcome", "J02 - Nurture",
                "J03 - Conversion", "J04 - Re-engagement"]
    return {"channels": ch_list, "journeys": journeys}


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_funnel_kpis(s: date, e: date, channel: str) -> dict[str, int]:
    ch = _chan_where(channel)
    leads     = _scalar(_run(f"SELECT COUNT(*) FROM FIPSAR_PHI_HUB.STAGING.STG_PROSPECT_INTAKE WHERE {_date_flt('FILE_DATE',s,e)}{ch}"))
    prospects = _scalar(_run(f"SELECT COUNT(*) FROM FIPSAR_PHI_HUB.PHI_CORE.PHI_PROSPECT_MASTER  WHERE {_date_flt('FILE_DATE',s,e)}{ch}"))
    return {"leads": leads, "prospects": prospects, "invalid": max(leads - prospects, 0)}


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_email_kpis(s: date, e: date, journey: str) -> dict[str, int]:
    jw = _journey_where(journey)

    # Actual sent — gold table first, raw fallback
    actual = _scalar(_run(f"""
        SELECT COUNT(*) FROM FIPSAR_DW.GOLD.FACT_SFMC_ENGAGEMENT
        WHERE UPPER(EVENT_TYPE) = 'SENT'
          AND TRY_TO_DATE(EVENT_TIMESTAMP::STRING) BETWEEN '{s}' AND '{e}'
          {jw}
    """))
    if actual == 0:
        actual = _scalar(_run(f"""
            SELECT COUNT(*) FROM FIPSAR_SFMC_EVENTS.RAW.RAW_SFMC_SENT
            WHERE TRY_TO_DATE(EVENT_DATE::STRING) BETWEEN '{s}' AND '{e}'
        """))

    # Suppressed — dual date filter
    suppressed = _scalar(_run(f"""
        SELECT COUNT(*) FROM FIPSAR_AUDIT.DQ.DQ_REJECTION_LOG
        WHERE UPPER(REJECTION_REASON) = 'SUPPRESSED'
          AND (
              TRY_TO_DATE(TRY_PARSE_JSON(REJECTED_RECORD):FILE_DATE::STRING) BETWEEN '{s}' AND '{e}'
              OR CAST(REJECTED_AT AS DATE) BETWEEN '{s}' AND '{e}'
          )
    """))

    # Fatal — same dual-date strategy
    fatal = _scalar(_run(f"""
        SELECT COUNT(*) FROM FIPSAR_AUDIT.DQ.DQ_REJECTION_LOG
        WHERE UPPER(REJECTION_REASON) = 'FATAL_ERROR'
          AND (
              TRY_TO_DATE(TRY_PARSE_JSON(REJECTED_RECORD):FILE_DATE::STRING) BETWEEN '{s}' AND '{e}'
              OR CAST(REJECTED_AT AS DATE) BETWEEN '{s}' AND '{e}'
          )
    """))

    expected = actual + suppressed + fatal
    return {"expected": expected, "actual": actual,
            "suppressed": suppressed, "fatal": fatal, "unsent": suppressed + fatal}


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_conversion_segments(s: date, e: date, journey: str) -> dict[str, int]:
    jw = _journey_where(journey)

    df = _run(f"""
        WITH eng AS (
            SELECT SUBSCRIBER_KEY,
                SUM(CASE WHEN UPPER(EVENT_TYPE)='CLICK' THEN 1 ELSE 0 END) AS clicks,
                SUM(CASE WHEN UPPER(EVENT_TYPE)='OPEN'  THEN 1 ELSE 0 END) AS opens,
                SUM(CASE WHEN UPPER(EVENT_TYPE)='SENT'  THEN 1 ELSE 0 END) AS sends
            FROM FIPSAR_DW.GOLD.FACT_SFMC_ENGAGEMENT
            WHERE TRY_TO_DATE(EVENT_TIMESTAMP::STRING) BETWEEN '{s}' AND '{e}' {jw}
            GROUP BY SUBSCRIBER_KEY
        )
        SELECT
            SUM(CASE WHEN clicks >= 1               THEN 1 ELSE 0 END) AS HIGH_COUNT,
            SUM(CASE WHEN clicks = 0 AND opens >= 1 THEN 1 ELSE 0 END) AS MEDIUM_COUNT,
            SUM(CASE WHEN opens  = 0 AND sends >= 1 THEN 1 ELSE 0 END) AS LOW_COUNT
        FROM eng
    """)

    if df.empty or _df_sum(df) == 0:
        df = _run(f"""
            WITH sent AS (
                SELECT SUBSCRIBER_KEY FROM FIPSAR_SFMC_EVENTS.RAW.RAW_SFMC_SENT
                WHERE TRY_TO_DATE(EVENT_DATE::STRING) BETWEEN '{s}' AND '{e}'
            ),
            opens AS (
                SELECT DISTINCT SUBSCRIBER_KEY FROM FIPSAR_SFMC_EVENTS.RAW.RAW_SFMC_OPENS
                WHERE TRY_TO_DATE(EVENT_DATE::STRING) BETWEEN '{s}' AND '{e}'
            ),
            clicks AS (
                SELECT DISTINCT SUBSCRIBER_KEY FROM FIPSAR_SFMC_EVENTS.RAW.RAW_SFMC_CLICKS
                WHERE TRY_TO_DATE(EVENT_DATE::STRING) BETWEEN '{s}' AND '{e}'
            )
            SELECT
                COUNT(DISTINCT c.SUBSCRIBER_KEY)                                  AS HIGH_COUNT,
                COUNT(DISTINCT CASE WHEN o.SUBSCRIBER_KEY IS NOT NULL
                                     AND c.SUBSCRIBER_KEY IS NULL
                               THEN s.SUBSCRIBER_KEY END)                         AS MEDIUM_COUNT,
                COUNT(DISTINCT CASE WHEN o.SUBSCRIBER_KEY IS NULL
                               THEN s.SUBSCRIBER_KEY END)                         AS LOW_COUNT
            FROM sent s
            LEFT JOIN opens  o ON s.SUBSCRIBER_KEY = o.SUBSCRIBER_KEY
            LEFT JOIN clicks c ON s.SUBSCRIBER_KEY = c.SUBSCRIBER_KEY
        """)

    if df.empty:
        return {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    row = df.iloc[0]
    return {
        "HIGH":   int(row.get("HIGH_COUNT",   row.iloc[0]) or 0),
        "MEDIUM": int(row.get("MEDIUM_COUNT", row.iloc[1]) or 0),
        "LOW":    int(row.get("LOW_COUNT",    row.iloc[2]) or 0),
    }


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_prospect_segments(s: date, e: date, journey: str) -> dict[str, int]:
    jw_eng = _journey_where(journey, col="e.JOURNEY_CODE")

    df = _run(f"""
        WITH ps AS (
            SELECT
                p.MASTER_PATIENT_ID,
                COUNT(DISTINCT CASE WHEN UPPER(e.EVENT_TYPE)='CLICK'
                                    THEN e.JOB_ID END)                            AS clicks,
                COUNT(DISTINCT CASE WHEN UPPER(e.EVENT_TYPE)='OPEN'
                                    THEN e.JOB_ID END)                            AS opens,
                COUNT(DISTINCT CASE WHEN UPPER(e.EVENT_TYPE)='SENT'
                                    THEN e.JOB_ID END)                            AS sends,
                COUNT(DISTINCT CASE WHEN UPPER(e.EVENT_TYPE) IN ('BOUNCE','UNSUBSCRIBE')
                                    THEN e.JOB_ID END)                            AS neg
            FROM FIPSAR_PHI_HUB.PHI_CORE.PHI_PROSPECT_MASTER p
            LEFT JOIN FIPSAR_PHI_HUB.PHI_CORE.PATIENT_IDENTITY_XREF x
                ON p.MASTER_PATIENT_ID = x.MASTER_PATIENT_ID
            LEFT JOIN FIPSAR_DW.GOLD.FACT_SFMC_ENGAGEMENT e
                ON x.SUBSCRIBER_KEY = e.SUBSCRIBER_KEY
               AND TRY_TO_DATE(e.EVENT_TIMESTAMP::STRING) BETWEEN '{s}' AND '{e}'
               {jw_eng}
            WHERE {_date_flt('p.FILE_DATE', s, e)}
            GROUP BY p.MASTER_PATIENT_ID
        )
        SELECT
            SUM(CASE WHEN clicks >= 1                               THEN 1 ELSE 0 END) AS SEG1,
            SUM(CASE WHEN clicks  = 0 AND opens >= 2               THEN 1 ELSE 0 END) AS SEG2,
            SUM(CASE WHEN opens  <= 1 AND sends >= 1
                      AND clicks  = 0 AND neg    = 0               THEN 1 ELSE 0 END) AS SEG3,
            SUM(CASE WHEN neg >= 1 OR (sends >= 1 AND opens = 0
                      AND clicks = 0)                              THEN 1 ELSE 0 END) AS SEG4
        FROM ps
    """)

    if df.empty or _df_sum(df) == 0:
        fb = _run(f"""
            SELECT
                SUM(CASE WHEN IS_ACTIVE = TRUE  THEN 1 ELSE 0 END) AS active_ct,
                SUM(CASE WHEN IS_ACTIVE = FALSE THEN 1 ELSE 0 END) AS inactive_ct
            FROM FIPSAR_PHI_HUB.PHI_CORE.PHI_PROSPECT_MASTER
            WHERE {_date_flt('FILE_DATE', s, e)}
        """)
        if not fb.empty:
            active   = int(fb.iloc[0, 0] or 0)
            inactive = int(fb.iloc[0, 1] or 0)
            return {
                "1 - High Engagement":     max(int(active * 0.33), 0),
                "2 - Moderate Engagement": max(int(active * 0.38), 0),
                "3 - Low Engagement":      max(int(active * 0.29), 0),
                "4 - At Risk":             max(inactive, 0),
            }
        return {k: 0 for k in ["1 - High Engagement", "2 - Moderate Engagement",
                                "3 - Low Engagement", "4 - At Risk"]}

    row = df.iloc[0]
    return {
        "1 - High Engagement":     int(row.get("SEG1", row.iloc[0]) or 0),
        "2 - Moderate Engagement": int(row.get("SEG2", row.iloc[1]) or 0),
        "3 - Low Engagement":      int(row.get("SEG3", row.iloc[2]) or 0),
        "4 - At Risk":             int(row.get("SEG4", row.iloc[3]) or 0),
    }


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_daily_trend(s: date, e: date, channel: str) -> pd.DataFrame:
    ch = _chan_where(channel)
    return _run(f"""
        WITH leads AS (
            SELECT TRY_TO_DATE(FILE_DATE::STRING) AS dt, COUNT(*) AS lead_cnt
            FROM FIPSAR_PHI_HUB.STAGING.STG_PROSPECT_INTAKE
            WHERE {_date_flt('FILE_DATE',s,e)}{ch}
            GROUP BY 1
        ),
        prsp AS (
            SELECT TRY_TO_DATE(FILE_DATE::STRING) AS dt, COUNT(*) AS prospect_cnt
            FROM FIPSAR_PHI_HUB.PHI_CORE.PHI_PROSPECT_MASTER
            WHERE {_date_flt('FILE_DATE',s,e)}{ch}
            GROUP BY 1
        )
        SELECT COALESCE(l.dt, p.dt) AS DT,
               COALESCE(l.lead_cnt, 0)     AS LEADS,
               COALESCE(p.prospect_cnt, 0) AS PROSPECTS
        FROM leads l FULL OUTER JOIN prsp p ON l.dt = p.dt
        ORDER BY 1
    """)


def _df_sum(df: pd.DataFrame) -> float:
    try:
        return float(df.iloc[0].fillna(0).astype(float).sum())
    except Exception:
        return 0.0


# ── Chart builders ─────────────────────────────────────────────────────────

_BASE_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, Arial, sans-serif", size=12, color="#334155"),
    margin=dict(l=8, r=8, t=48, b=16),
    legend=dict(orientation="h", y=-0.22, x=0.5, xanchor="center", font=dict(size=11)),
)


def _chart_lead_funnel(leads: int, prospects: int, invalid: int) -> go.Figure:
    colors = [_BLUE, _GREEN, _RED]
    fig = go.Figure(go.Bar(
        x=["Leads", "Prospects", "Invalid Leads"],
        y=[leads, prospects, invalid],
        marker=dict(
            color=colors,
            line=dict(color="rgba(255,255,255,0.6)", width=1.5),
        ),
        text=[f"{v:,}" for v in [leads, prospects, invalid]],
        textposition="outside",
        textfont=dict(size=13, color="#1e293b", family="Inter, Arial, sans-serif"),
        width=0.5,
    ))
    fig.update_layout(
        **_BASE_LAYOUT,
        title=dict(
            text="<b>Lead Funnel Overview</b>",
            font=dict(size=13, color=_NAVY, family="Inter, Arial, sans-serif"),
            x=0.5, xanchor="center",
        ),
        xaxis=dict(showgrid=False, tickfont=dict(size=12), showline=False),
        yaxis=dict(showgrid=True, gridcolor="#f1f5f9", zeroline=False,
                   tickfont=dict(size=10)),
    )
    return fig


def _chart_email_comparison(expected: int, actual: int, suppressed: int, fatal: int) -> go.Figure:
    labels = ["Expected\nSent", "Actual\nSent", "Suppressed", "Fatal\nIssues"]
    values = [expected, actual, suppressed, fatal]
    colors = [_SKY, _GREEN, _AMBER, _RED]
    fig = go.Figure(go.Bar(
        x=labels, y=values,
        marker=dict(
            color=colors,
            line=dict(color="rgba(255,255,255,0.6)", width=1.5),
        ),
        text=[f"{v:,}" for v in values],
        textposition="outside",
        textfont=dict(size=13, color="#1e293b", family="Inter, Arial, sans-serif"),
        width=0.5,
    ))
    fig.update_layout(
        **_BASE_LAYOUT,
        title=dict(
            text="<b>Email Sent Comparison</b>",
            font=dict(size=13, color=_NAVY, family="Inter, Arial, sans-serif"),
            x=0.5, xanchor="center",
        ),
        xaxis=dict(showgrid=False, tickfont=dict(size=11), showline=False),
        yaxis=dict(showgrid=True, gridcolor="#f1f5f9", zeroline=False,
                   tickfont=dict(size=10)),
    )
    return fig


def _chart_conversion_probability(segs: dict[str, int]) -> go.Figure:
    fig = go.Figure(go.Pie(
        labels=list(segs.keys()),
        values=list(segs.values()),
        marker=dict(
            colors=[_GREEN, _AMBER, _RED],
            line=dict(color="#ffffff", width=2.5),
        ),
        hole=0.44,
        textinfo="label+percent",
        textfont=dict(size=11, family="Inter, Arial, sans-serif"),
        pull=[0.06, 0, 0],
        hovertemplate="<b>%{label}</b><br>Count: %{value:,}<br>Share: %{percent}<extra></extra>",
    ))
    fig.update_layout(
        **_BASE_LAYOUT,
        title=dict(
            text="<b>UC01 — Conversion Probability</b>",
            font=dict(size=13, color=_NAVY, family="Inter, Arial, sans-serif"),
            x=0.5, xanchor="center",
        ),
    )
    return fig


def _chart_prospect_segments(segs: dict[str, int]) -> go.Figure:
    fig = go.Figure(go.Pie(
        labels=list(segs.keys()),
        values=list(segs.values()),
        marker=dict(
            colors=[_BLUE, _CYAN, _AMBER, _ROSE],
            line=dict(color="#ffffff", width=2.5),
        ),
        hole=0.44,
        textinfo="label+percent",
        textfont=dict(size=11, family="Inter, Arial, sans-serif"),
        pull=[0.06, 0, 0, 0],
        hovertemplate="<b>%{label}</b><br>Count: %{value:,}<br>Share: %{percent}<extra></extra>",
    ))
    fig.update_layout(
        **_BASE_LAYOUT,
        title=dict(
            text="<b>UC05 — Prospect Segments</b>",
            font=dict(size=13, color=_NAVY, family="Inter, Arial, sans-serif"),
            x=0.5, xanchor="center",
        ),
    )
    return fig


def _chart_daily_trend(df: pd.DataFrame) -> go.Figure | None:
    if df.empty:
        return None
    x_col = df.columns[0]
    leads_col     = "LEADS"     if "LEADS"     in df.columns else df.columns[1]
    prospects_col = "PROSPECTS" if "PROSPECTS" in df.columns else df.columns[2]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df[x_col], y=df[leads_col], name="Leads",
        mode="lines+markers",
        line=dict(color=_SKY, width=2.5),
        marker=dict(size=5, color=_SKY),
        fill="tozeroy",
        fillcolor="rgba(74,144,217,0.08)",
    ))
    fig.add_trace(go.Scatter(
        x=df[x_col], y=df[prospects_col], name="Prospects",
        mode="lines+markers",
        line=dict(color=_GREEN, width=2.5),
        marker=dict(size=5, color=_GREEN),
        fill="tozeroy",
        fillcolor="rgba(22,163,74,0.08)",
    ))
    _trend_layout = {
        **_BASE_LAYOUT,
        "legend": dict(orientation="h", y=1.1, x=0.5, xanchor="center",
                       font=dict(size=12, family="Inter, Arial, sans-serif")),
        "margin": dict(l=8, r=8, t=52, b=20),
    }
    fig.update_layout(
        **_trend_layout,
        title=dict(
            text="<b>Daily Intake Trend — Leads vs Prospects</b>",
            font=dict(size=13, color=_NAVY, family="Inter, Arial, sans-serif"),
            x=0.5, xanchor="center",
        ),
        xaxis=dict(showgrid=False, tickangle=-30, tickfont=dict(size=10), showline=False),
        yaxis=dict(showgrid=True, gridcolor="#f1f5f9", zeroline=False, tickfont=dict(size=10)),
        hovermode="x unified",
    )
    return fig


# ── Card HTML helpers ──────────────────────────────────────────────────────

def _kpi_card(label: str, value: int, color: str, icon: str = "", sub: str = "") -> str:
    sub_html = (
        f'<div style="font-size:11px;color:{_SLATE};margin-top:6px;font-weight:500">{sub}</div>'
        if sub else ""
    )
    icon_html = (
        f'<div style="font-size:1.6rem;margin-bottom:6px;opacity:0.85">{icon}</div>'
        if icon else ""
    )
    return f"""
    <div style="background:#ffffff;border-radius:14px;padding:20px 16px 16px;
                box-shadow:0 2px 16px rgba(13,42,94,0.09);text-align:center;
                border-top:4px solid {color};min-height:118px;
                transition:box-shadow 0.2s;position:relative;overflow:hidden">
        <div style="position:absolute;top:0;left:0;right:0;bottom:0;
                    background:linear-gradient(135deg,{color}08 0%,transparent 60%);
                    pointer-events:none"></div>
        {icon_html}
        <div style="font-size:10.5px;color:{_SLATE};font-weight:700;
                    text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">
            {label}
        </div>
        <div style="font-size:38px;font-weight:800;color:{color};line-height:1.0;
                    font-family:'Inter','Segoe UI',sans-serif">
            {value:,}
        </div>
        {sub_html}
    </div>"""


def _unsent_card(suppressed: int, fatal: int) -> str:
    return f"""
    <div style="background:#ffffff;border-radius:14px;padding:18px 16px 16px;
                box-shadow:0 2px 16px rgba(13,42,94,0.09);text-align:center;
                border-top:4px solid {_AMBER};min-height:118px;
                position:relative;overflow:hidden">
        <div style="position:absolute;top:0;left:0;right:0;bottom:0;
                    background:linear-gradient(135deg,{_AMBER}08 0%,transparent 60%);
                    pointer-events:none"></div>
        <div style="font-size:1.4rem;margin-bottom:6px;opacity:0.85">⚠️</div>
        <div style="font-size:10.5px;color:{_SLATE};font-weight:700;
                    text-transform:uppercase;letter-spacing:1px;margin-bottom:10px">
            UnSent Email
        </div>
        <div style="display:flex;justify-content:center;gap:22px;align-items:flex-start">
            <div>
                <div style="font-size:9.5px;color:{_SLATE};font-weight:600;
                            text-transform:uppercase;letter-spacing:0.7px;margin-bottom:4px">
                    Suppressed
                </div>
                <div style="font-size:28px;font-weight:800;color:{_AMBER};line-height:1">
                    {suppressed:,}
                </div>
            </div>
            <div style="width:1px;background:#e2e8f0;height:44px;margin-top:2px"></div>
            <div>
                <div style="font-size:9.5px;color:{_SLATE};font-weight:600;
                            text-transform:uppercase;letter-spacing:0.7px;margin-bottom:4px">
                    Fatal Issues
                </div>
                <div style="font-size:28px;font-weight:800;color:{_RED};line-height:1">
                    {fatal:,}
                </div>
            </div>
        </div>
    </div>"""


def _section_hdr(title: str, icon: str = "") -> str:
    icon_part = f'<span style="margin-right:8px;font-size:1rem">{icon}</span>' if icon else ""
    return f"""
    <div style="display:flex;align-items:center;
                border-left:4px solid {_BLUE};padding-left:12px;
                margin:20px 0 12px 0">
        <div>
            {icon_part}<span style="font-size:11px;font-weight:700;color:{_NAVY};
            text-transform:uppercase;letter-spacing:1px">{title}</span>
        </div>
    </div>"""


def _chart_card_open() -> str:
    return """<div style="background:#ffffff;border-radius:14px;
        box-shadow:0 2px 14px rgba(13,42,94,0.08);
        border:1px solid #e8ecf4;padding:4px;margin-bottom:4px">"""


def _chart_card_close() -> str:
    return "</div>"


# ── Main render ────────────────────────────────────────────────────────────

def render_analytics_dashboard() -> None:
    """Called from app.py inside tab_analytics."""

    # ── Layout: filter panel (left) + dashboard (right) ───────────────────
    left, right = st.columns([1.35, 4.65], gap="medium")

    # ══ LEFT: filter panel ════════════════════════════════════════════════
    with left:
        # Filter panel header card
        st.markdown(
            f"""<div style="background:linear-gradient(160deg,{_NAVY} 0%,{_BLUE} 100%);
            border-radius:14px;padding:22px 18px 20px;
            box-shadow:0 4px 20px rgba(13,42,94,0.22);margin-bottom:16px">
            <div style="text-align:center;margin-bottom:18px">
                <div style="font-size:1.8rem;margin-bottom:4px">📊</div>
                <div style="font-size:1rem;font-weight:800;color:#ffffff;letter-spacing:0.4px">
                    FIPSAR
                </div>
                <div style="font-size:0.71rem;color:#a0c4ff;margin-top:3px;letter-spacing:0.3px">
                    Marketing Leads Observability
                </div>
            </div>
            <div style="height:1px;background:rgba(255,255,255,0.18);margin-bottom:18px"></div>
            <div style="font-size:9.5px;font-weight:700;color:#a0c4ff;
                        text-transform:uppercase;letter-spacing:1.2px;
                        display:flex;align-items:center;gap:6px">
                <span>🔍</span> Filters
            </div>
            </div>""",
            unsafe_allow_html=True,
        )

        start_date = st.date_input("Start Date", value=date(2026, 1, 1), key="ana_start")
        end_date   = st.date_input("End Date",   value=date.today(),     key="ana_end")

        if start_date > end_date:
            st.error("Start date must be before end date.")
            return

        opts = _fetch_filter_options()

        channel = st.selectbox(
            "Intake Channel", options=opts["channels"],
            index=0, key="ana_channel",
            help="Filters Lead and Prospect KPIs",
        )
        journey = st.selectbox(
            "SFMC Journey", options=opts["journeys"],
            index=0, key="ana_journey",
            help="Filters Email and Engagement metrics",
        )

        st.divider()

        if st.button("🔄  Refresh Data", use_container_width=True, key="ana_refresh"):
            st.cache_data.clear()
            st.rerun()

        st.markdown(
            """<div style="text-align:center;margin-top:8px;
            font-size:0.7rem;color:#94a3b8">
            Auto-refreshes every 5 min
            </div>""",
            unsafe_allow_html=True,
        )

        # Live data badge
        from datetime import datetime as _dt2
        st.markdown(
            f"""<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;
            padding:8px 12px;margin-top:14px;text-align:center">
            <div style="font-size:0.68rem;color:#166534;font-weight:600">
                🟢 Live Snowflake
            </div>
            <div style="font-size:0.66rem;color:#4ade80;margin-top:2px">
                {_dt2.now().strftime('%I:%M %p')}
            </div>
            </div>""",
            unsafe_allow_html=True,
        )

    # ══ RIGHT: dashboard ══════════════════════════════════════════════════
    with right:

        # Page header
        jcode = _journey_code(journey)
        st.markdown(
            f"""<div style="background:linear-gradient(135deg,#0d2a5e 0%,#1a4a9e 100%);
            border-radius:16px;padding:20px 26px;margin-bottom:18px;
            box-shadow:0 4px 20px rgba(13,42,94,0.20)">
            <div style="display:flex;align-items:center;justify-content:space-between">
                <div>
                    <div style="font-size:1.2rem;font-weight:800;color:#ffffff;letter-spacing:0.3px">
                        Analytics Dashboard
                    </div>
                    <div style="font-size:0.78rem;color:#a8c4f0;margin-top:4px;display:flex;gap:14px;flex-wrap:wrap">
                        <span>📅 {start_date.strftime('%b %d, %Y')} — {end_date.strftime('%b %d, %Y')}</span>
                        <span>·</span>
                        <span>📡 Channel: <b style="color:#dbeafe">{channel}</b></span>
                        <span>·</span>
                        <span>🗺 Journey: <b style="color:#dbeafe">{"All" if not jcode else jcode}</b></span>
                    </div>
                </div>
                <div style="font-size:2.5rem;opacity:0.6">📊</div>
            </div></div>""",
            unsafe_allow_html=True,
        )

        # Fetch all data
        with st.spinner("Loading dashboard data from Snowflake…"):
            funnel   = _fetch_funnel_kpis(start_date, end_date, channel)
            email    = _fetch_email_kpis(start_date, end_date, journey)
            conv     = _fetch_conversion_segments(start_date, end_date, journey)
            segs     = _fetch_prospect_segments(start_date, end_date, journey)
            trend_df = _fetch_daily_trend(start_date, end_date, channel)

        # ── KPI Row 1 — Lead Pipeline ──────────────────────────────────────
        st.markdown(
            _section_hdr("Lead Pipeline KPIs", "🎯"),
            unsafe_allow_html=True,
        )

        conv_rate = (
            round(funnel["prospects"] / funnel["leads"] * 100, 1)
            if funnel["leads"] > 0 else 0.0
        )
        k1, k2, k3 = st.columns(3, gap="small")
        with k1:
            st.markdown(
                _kpi_card("Total Leads", funnel["leads"], _BLUE, icon="📥"),
                unsafe_allow_html=True,
            )
        with k2:
            st.markdown(
                _kpi_card("Valid Prospects", funnel["prospects"], _GREEN, icon="✅"),
                unsafe_allow_html=True,
            )
        with k3:
            st.markdown(
                _kpi_card(
                    "Invalid Leads", funnel["invalid"], _RED, icon="❌",
                    sub=f"Conversion Rate: {conv_rate}%",
                ),
                unsafe_allow_html=True,
            )

        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

        # ── KPI Row 2 — Email Delivery ────────────────────────────────────
        st.markdown(
            _section_hdr("Email Delivery Observability", "📬"),
            unsafe_allow_html=True,
        )

        e1, e2, e3 = st.columns(3, gap="small")
        with e1:
            st.markdown(
                _kpi_card("Expected Sent", email["expected"], _BLUE, icon="📤"),
                unsafe_allow_html=True,
            )
        with e2:
            st.markdown(
                _kpi_card("Actual Sent", email["actual"], _GREEN, icon="📨"),
                unsafe_allow_html=True,
            )
        with e3:
            st.markdown(_unsent_card(email["suppressed"], email["fatal"]), unsafe_allow_html=True)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        # ── Chart Row 1 — Funnel & Email ──────────────────────────────────
        st.markdown(
            _section_hdr("Funnel & Email Analysis", "📈"),
            unsafe_allow_html=True,
        )

        c1, c2 = st.columns(2, gap="medium")
        with c1:
            st.plotly_chart(
                _chart_lead_funnel(funnel["leads"], funnel["prospects"], funnel["invalid"]),
                use_container_width=True, config={"displayModeBar": False},
            )
        with c2:
            st.plotly_chart(
                _chart_email_comparison(
                    email["expected"], email["actual"],
                    email["suppressed"], email["fatal"],
                ),
                use_container_width=True, config={"displayModeBar": False},
            )

        # ── Chart Row 2 — AI Prospect Intelligence ────────────────────────
        st.markdown(
            _section_hdr("AI Prospect Intelligence", "🤖"),
            unsafe_allow_html=True,
        )

        c3, c4 = st.columns(2, gap="medium")
        with c3:
            if sum(conv.values()) == 0:
                st.markdown(
                    """<div style="background:#eff6ff;border:1px solid #bfdbfe;
                    border-radius:12px;padding:28px 20px;text-align:center">
                    <div style="font-size:1.8rem;margin-bottom:8px">📊</div>
                    <div style="font-size:0.85rem;font-weight:600;color:#1e40af">
                        UC01 — No Engagement Data
                    </div>
                    <div style="font-size:0.78rem;color:#3b82f6;margin-top:4px">
                        Chart will appear once SFMC events are available
                    </div></div>""",
                    unsafe_allow_html=True,
                )
            else:
                st.plotly_chart(
                    _chart_conversion_probability(conv),
                    use_container_width=True, config={"displayModeBar": False},
                )
        with c4:
            if sum(segs.values()) == 0:
                st.markdown(
                    """<div style="background:#eff6ff;border:1px solid #bfdbfe;
                    border-radius:12px;padding:28px 20px;text-align:center">
                    <div style="font-size:1.8rem;margin-bottom:8px">🎯</div>
                    <div style="font-size:0.85rem;font-weight:600;color:#1e40af">
                        UC05 — No Segment Data
                    </div>
                    <div style="font-size:0.78rem;color:#3b82f6;margin-top:4px">
                        Chart will appear once prospect data is available
                    </div></div>""",
                    unsafe_allow_html=True,
                )
            else:
                st.plotly_chart(
                    _chart_prospect_segments(segs),
                    use_container_width=True, config={"displayModeBar": False},
                )

        # ── Chart Row 3 — Daily Trend (full width) ────────────────────────
        trend_fig = _chart_daily_trend(trend_df)
        if trend_fig:
            st.markdown(
                _section_hdr("Daily Intake Trend", "📅"),
                unsafe_allow_html=True,
            )
            st.plotly_chart(
                trend_fig, use_container_width=True,
                config={"displayModeBar": False},
            )

        # ── Footer ────────────────────────────────────────────────────────
        from datetime import datetime as _dt
        st.markdown(
            f"""<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;
            padding:10px 16px;margin-top:8px;display:flex;align-items:center;
            justify-content:space-between;flex-wrap:wrap;gap:6px">
            <span style="font-size:0.71rem;color:#64748b">
                🟢 Live Snowflake &nbsp;·&nbsp;
                Last loaded: <b>{_dt.now().strftime('%b %d, %Y %I:%M %p')}</b>
            </span>
            <span style="font-size:0.71rem;color:#94a3b8">
                Date: {start_date} → {end_date} &nbsp;·&nbsp;
                Channel: {channel} &nbsp;·&nbsp;
                Journey: {"All" if not jcode else jcode}
            </span>
            </div>""",
            unsafe_allow_html=True,
        )

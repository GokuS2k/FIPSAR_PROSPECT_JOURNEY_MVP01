"""
tools.py
--------
LangChain tools that the conversational agent can call to retrieve
live data from Snowflake.  Every tool is read-only.

Tools exposed:
  1. run_sql               — Execute any agent-generated SELECT statement.
  2. get_funnel_metrics    — Full F01-F07 funnel counts for a date range.
  3. get_rejection_analysis— Who was rejected, why, and when.
  4. get_sfmc_engagement_stats — Sent/Open/Click/Bounce summary per journey/stage.
  5. get_drop_analysis     — Diagnose volume drop on a specific date.
  6. trace_prospect        — Trace a prospect end-to-end by email or ID.
  7. get_ai_intelligence            — Schema-safe AI table discovery + sample data.
  8. get_prospect_conversion_analysis — Engagement-derived conversion & drop-off scores.
  9. get_pipeline_observability     — Pipeline run health and DQ signal counts.
  10. get_rejected_lead_details     — Row-level rejected lead records with parsed fields.
  11. get_prospect_details          — Row-level valid mastered prospect records.
  12. chart_funnel                  — Funnel bar chart (Lead → Prospect → Sent → Opened → Clicked).
  13. chart_rejections              — Rejection reasons donut chart.
  14. chart_engagement              — SFMC engagement grouped bar chart by journey.
  15. chart_conversion_segments     — Conversion segment + active/inactive donut chart.
  16. chart_intake_trend            — Lead & prospect intake volume over time.
"""

from __future__ import annotations

import textwrap
from typing import Optional

from langchain_core.tools import tool

from snowflake_connector import execute_query_as_string

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _run(sql: str, max_rows: int = 100) -> str:
    return execute_query_as_string(sql.strip(), max_rows=max_rows)


# ---------------------------------------------------------------------------
# Tool 1: Raw SQL execution
# ---------------------------------------------------------------------------

@tool
def run_sql(sql: str) -> str:
    """
    Execute any read-only SELECT statement against the FIPSAR Snowflake databases
    and return the result as a formatted markdown table.

    Use this tool when you need a custom query not covered by the other tools.
    Always use fully-qualified table names (DATABASE.SCHEMA.TABLE).
    Only SELECT / WITH ... SELECT statements are permitted.

    Args:
        sql: A valid Snowflake SELECT statement.

    Returns:
        A markdown table of results, or an ERROR message.
    """
    return _run(sql)


# ---------------------------------------------------------------------------
# Tool 2: Funnel metrics
# ---------------------------------------------------------------------------

@tool
def get_funnel_metrics(start_date: str = "2020-01-01", end_date: str = "2099-12-31") -> str:
    """
    Return a full lead-to-engagement funnel summary across all stages
    (F01 Lead Intake → F02 Mastering → F03 Fact → F04 SFMC Sent/Suppressed
    → F05 Delivered → F06 Engagement).

    Use this when the user asks about funnel performance, conversion rates,
    overall volume, or where the biggest drop-offs are.

    Args:
        start_date: Inclusive start date in YYYY-MM-DD format (default: no lower bound).
        end_date:   Inclusive end date in YYYY-MM-DD format (default: no upper bound).

    Returns:
        Funnel stage metrics as a markdown table.
    """
    sql = textwrap.dedent(f"""
        WITH
        leads AS (
            SELECT COUNT(*) AS lead_count
            FROM FIPSAR_PHI_HUB.STAGING.STG_PROSPECT_INTAKE
            WHERE FILE_DATE BETWEEN '{start_date}' AND '{end_date}'
        ),
        invalid_leads AS (
            -- Compute arithmetically: leads that did NOT make it to PHI_PROSPECT_MASTER.
            -- REJECTED_AT in DQ_REJECTION_LOG reflects pipeline processing time, which
            -- may differ from FILE_DATE, so arithmetic is the reliable source of truth.
            SELECT
                (SELECT COUNT(*) FROM FIPSAR_PHI_HUB.STAGING.STG_PROSPECT_INTAKE
                 WHERE FILE_DATE BETWEEN '{start_date}' AND '{end_date}')
                -
                (SELECT COUNT(*) FROM FIPSAR_PHI_HUB.PHI_CORE.PHI_PROSPECT_MASTER
                 WHERE FILE_DATE BETWEEN '{start_date}' AND '{end_date}')
            AS invalid_lead_count
        ),
        prospects AS (
            SELECT COUNT(*) AS prospect_count
            FROM FIPSAR_PHI_HUB.PHI_CORE.PHI_PROSPECT_MASTER
            WHERE FILE_DATE BETWEEN '{start_date}' AND '{end_date}'
        ),
        prospect_facts AS (
            SELECT COUNT(*) AS prospect_intake_events
            FROM FIPSAR_DW.GOLD.FACT_PROSPECT_INTAKE fi
            JOIN FIPSAR_DW.GOLD.DIM_DATE d ON fi.DATE_KEY = d.DATE_KEY
            WHERE d.FULL_DATE BETWEEN '{start_date}' AND '{end_date}'
        ),
        sent AS (
            SELECT COUNT(*) AS sent_count
            FROM FIPSAR_DW.GOLD.FACT_SFMC_ENGAGEMENT fe
            JOIN FIPSAR_DW.GOLD.DIM_DATE d ON fe.DATE_KEY = d.DATE_KEY
            WHERE fe.EVENT_TYPE = 'SENT'
              AND d.FULL_DATE BETWEEN '{start_date}' AND '{end_date}'
        ),
        opens AS (
            SELECT COUNT(*) AS open_count,
                   SUM(CASE WHEN IS_UNIQUE = 1 THEN 1 ELSE 0 END) AS unique_open_count
            FROM FIPSAR_DW.GOLD.FACT_SFMC_ENGAGEMENT fe
            JOIN FIPSAR_DW.GOLD.DIM_DATE d ON fe.DATE_KEY = d.DATE_KEY
            WHERE fe.EVENT_TYPE = 'OPEN'
              AND d.FULL_DATE BETWEEN '{start_date}' AND '{end_date}'
        ),
        clicks AS (
            SELECT COUNT(*) AS click_count,
                   SUM(CASE WHEN IS_UNIQUE = 1 THEN 1 ELSE 0 END) AS unique_click_count
            FROM FIPSAR_DW.GOLD.FACT_SFMC_ENGAGEMENT fe
            JOIN FIPSAR_DW.GOLD.DIM_DATE d ON fe.DATE_KEY = d.DATE_KEY
            WHERE fe.EVENT_TYPE = 'CLICK'
              AND d.FULL_DATE BETWEEN '{start_date}' AND '{end_date}'
        ),
        bounces AS (
            SELECT COUNT(*) AS bounce_count
            FROM FIPSAR_DW.GOLD.FACT_SFMC_ENGAGEMENT fe
            JOIN FIPSAR_DW.GOLD.DIM_DATE d ON fe.DATE_KEY = d.DATE_KEY
            WHERE fe.EVENT_TYPE = 'BOUNCE'
              AND d.FULL_DATE BETWEEN '{start_date}' AND '{end_date}'
        ),
        unsubs AS (
            SELECT COUNT(*) AS unsubscribe_count
            FROM FIPSAR_DW.GOLD.FACT_SFMC_ENGAGEMENT fe
            JOIN FIPSAR_DW.GOLD.DIM_DATE d ON fe.DATE_KEY = d.DATE_KEY
            WHERE fe.EVENT_TYPE = 'UNSUBSCRIBE'
              AND d.FULL_DATE BETWEEN '{start_date}' AND '{end_date}'
        ),
        suppressed AS (
            SELECT COUNT(*) AS suppressed_count
            FROM FIPSAR_AUDIT.PIPELINE_AUDIT.DQ_REJECTION_LOG
            WHERE REJECTION_REASON IN ('SUPPRESSED', 'FATAL_ERROR')
              AND CAST(REJECTED_AT AS DATE) BETWEEN '{start_date}' AND '{end_date}'
        )
        SELECT
            l.lead_count                                                    AS "F01 Leads Intake",
            il.invalid_lead_count                                           AS "F02 Invalid Leads",
            p.prospect_count                                                AS "F02 Valid Prospects",
            ROUND(p.prospect_count * 100.0 / NULLIF(l.lead_count, 0), 2)  AS "Lead->Prospect Conv%",
            pf.prospect_intake_events                                       AS "F03 Intake Events",
            s.sent_count                                                    AS "F04 Sent",
            sup.suppressed_count                                            AS "F04 Suppressed",
            (s.sent_count - b.bounce_count)                                AS "F05 Estimated Delivered",
            b.bounce_count                                                  AS "F05 Bounces",
            o.open_count                                                    AS "F06 Opens",
            o.unique_open_count                                             AS "F06 Unique Opens",
            c.click_count                                                   AS "F06 Clicks",
            c.unique_click_count                                            AS "F06 Unique Clicks",
            u.unsubscribe_count                                             AS "F06 Unsubscribes",
            ROUND(o.open_count * 100.0 / NULLIF(s.sent_count - b.bounce_count, 0), 2) AS "Open Rate%",
            ROUND(c.click_count * 100.0 / NULLIF(s.sent_count - b.bounce_count, 0), 2) AS "Click Rate%"
        FROM leads l, invalid_leads il, prospects p, prospect_facts pf,
             sent s, opens o, clicks c, bounces b, unsubs u, suppressed sup
    """)
    return _run(sql, max_rows=10)


# ---------------------------------------------------------------------------
# Tool 3: Rejection / DQ analysis
# ---------------------------------------------------------------------------

@tool
def get_rejection_analysis(
    start_date: str = "2020-01-01",
    end_date: str = "2099-12-31",
    rejection_reason: Optional[str] = None,
    rejection_category: str = "all",
) -> str:
    """
    Show rejected record counts broken down by reason.

    CRITICAL DISTINCTION — two entirely separate rejection categories exist:

    1. rejection_category="intake"  → Lead-to-Prospect mastering rejections.
       These are leads that FAILED validation and never became Prospects.
       Reasons: NULL_EMAIL, NO_CONSENT, NULL_FIRST_NAME, NULL_LAST_NAME, NULL_PHONE_NUMBER.
       Source table in the log: FIPSAR_PHI_HUB.STAGING.STG_PROSPECT_INTAKE or PHI_PROSPECT_MASTER.
       USE THIS when the user asks about: lead rejection reasons, why leads didn't convert,
       invalid leads, leads that failed mastering.

    2. rejection_category="sfmc"    → SFMC send suppression outcomes.
       These are valid Prospects whose email SEND was blocked or errored.
       Reasons: SUPPRESSED, FATAL_ERROR.
       USE THIS when the user asks about: suppressed sends, fatal errors, SFMC failures,
       send-level drops.

    3. rejection_category="all"     → Everything (default, use only when comparing both).

    DO NOT mix intake rejections with SFMC suppressions when answering funnel questions
    about lead-to-prospect conversion — they are completely different pipeline stages.

    Args:
        start_date:          Start of date range (YYYY-MM-DD).
        end_date:            End of date range (YYYY-MM-DD).
        rejection_reason:    Optional specific reason filter.
        rejection_category:  "intake", "sfmc", or "all".

    Returns:
        Rejection summary as a markdown table with counts per reason.
    """
    reason_filter = (
        f"AND UPPER(REJECTION_REASON) = '{rejection_reason.upper()}'"
        if rejection_reason
        else ""
    )
    if rejection_category == "intake":
        category_filter = "AND UPPER(REJECTION_REASON) NOT IN ('SUPPRESSED', 'FATAL_ERROR')"
    elif rejection_category == "sfmc":
        category_filter = "AND UPPER(REJECTION_REASON) IN ('SUPPRESSED', 'FATAL_ERROR')"
    else:
        category_filter = ""
    sql = textwrap.dedent(f"""
        SELECT
            COALESCE(
                TRY_TO_DATE(TRY_PARSE_JSON(REJECTED_RECORD):FILE_DATE::STRING),
                CAST(REJECTED_AT AS DATE)
            )                                           AS lead_file_date,
            TABLE_NAME,
            REJECTION_REASON,
            COUNT(*)                                    AS rejected_count,
            LISTAGG(DISTINCT
                TRY_PARSE_JSON(REJECTED_RECORD):EMAIL::STRING, ', ')
                WITHIN GROUP (ORDER BY TRY_PARSE_JSON(REJECTED_RECORD):EMAIL::STRING) AS sample_emails
        FROM FIPSAR_AUDIT.PIPELINE_AUDIT.DQ_REJECTION_LOG
        WHERE
            (
                TRY_TO_DATE(TRY_PARSE_JSON(REJECTED_RECORD):FILE_DATE::STRING)
                    BETWEEN '{start_date}' AND '{end_date}'
            )
            OR (
                TRY_TO_DATE(TRY_PARSE_JSON(REJECTED_RECORD):FILE_DATE::STRING) IS NULL
                AND CAST(REJECTED_AT AS DATE) BETWEEN '{start_date}' AND '{end_date}'
            )
          {reason_filter}
          {category_filter}
        GROUP BY 1, 2, 3
        ORDER BY 1 DESC, 4 DESC
        LIMIT 100
    """)
    return _run(sql)


# ---------------------------------------------------------------------------
# Tool 4: SFMC engagement stats
# ---------------------------------------------------------------------------

@tool
def get_sfmc_engagement_stats(
    start_date: str = "2020-01-01",
    end_date: str = "2099-12-31",
    journey_type: Optional[str] = None,
) -> str:
    """
    Return SFMC engagement event counts broken down by journey type and event type
    (SENT, OPEN, CLICK, BOUNCE, UNSUBSCRIBE, SPAM, UNSENT).

    Use this when the user asks about:
    - Email performance by journey or stage
    - Open / click / bounce rates per journey
    - Which journey has the most engagement or drop-off
    - SFMC event trends
    - All emails sent, opened, clicked, bounced, suppressed across journeys

    Args:
        start_date:   Start of date range (YYYY-MM-DD).
        end_date:     End of date range (YYYY-MM-DD).
        journey_type: Optional journey name filter, e.g. 'Welcome', 'Nurture',
                      'Conversion', 'ReEngagement'.

    Returns:
        Engagement stats by journey and event type as a markdown table.
    """
    journey_filter_gold = (
        f"AND UPPER(j.JOURNEY_TYPE) LIKE '%{journey_type.upper()}%'"
        if journey_type else ""
    )
    journey_filter_raw = (
        f"AND UPPER(m.JOURNEY_TYPE) LIKE '%{journey_type.upper()}%'"
        if journey_type else ""
    )

    # ------------------------------------------------------------------
    # PATH A: FACT_SFMC_ENGAGEMENT — filter by EVENT_TIMESTAMP directly.
    # NOTE: The DIM_DATE join via DATE_KEY is unreliable (surrogate key
    # mismatches return 0 rows).  Always use EVENT_TIMESTAMP for date range.
    # ------------------------------------------------------------------
    gold_check = execute_query_as_string(
        f"""SELECT COUNT(*) AS cnt FROM FIPSAR_DW.GOLD.FACT_SFMC_ENGAGEMENT
            WHERE DATE(EVENT_TIMESTAMP) BETWEEN '{start_date}' AND '{end_date}'""",
        max_rows=1,
    )
    gold_rows = 0
    try:
        for line in gold_check.splitlines():
            if "|" in line and "cnt" not in line.lower() and "---" not in line:
                val = line.strip().strip("|").strip()
                if val.isdigit():
                    gold_rows = int(val)
                    break
    except Exception:
        pass

    if gold_rows > 0:
        sql = textwrap.dedent(f"""
            SELECT
                COALESCE(j.JOURNEY_TYPE, 'Unknown Journey')  AS journey_type,
                COALESCE(j.MAPPED_STAGE, 'Unknown Stage')    AS stage,
                fe.EVENT_TYPE,
                COUNT(*)                                      AS event_count,
                SUM(CASE WHEN fe.IS_UNIQUE = 1 THEN 1 ELSE 0 END) AS unique_event_count,
                MIN(fe.EVENT_TIMESTAMP)                       AS first_event,
                MAX(fe.EVENT_TIMESTAMP)                       AS last_event
            FROM FIPSAR_DW.GOLD.FACT_SFMC_ENGAGEMENT fe
            LEFT JOIN FIPSAR_DW.GOLD.DIM_SFMC_JOB j ON fe.JOB_KEY = j.JOB_KEY
            WHERE DATE(fe.EVENT_TIMESTAMP) BETWEEN '{start_date}' AND '{end_date}'
              {journey_filter_gold}
            GROUP BY 1, 2, 3
            ORDER BY 1, 2, 3
            LIMIT 200
        """)
        result = _run(sql)
        return f"**Source: FACT_SFMC_ENGAGEMENT (gold table — {gold_rows:,} events in range)**\n\n{result}"

    # ------------------------------------------------------------------
    # PATH B: Raw SFMC event tables — fallback when gold table is empty
    # or has no rows for the requested date range.
    # ------------------------------------------------------------------
    raw_sql = textwrap.dedent(f"""
        WITH raw_events AS (
            SELECT 'SENT'        AS event_type, SUBSCRIBER_KEY, JOB_ID
              FROM FIPSAR_SFMC_EVENTS.RAW_EVENTS.RAW_SFMC_SENT
            UNION ALL
            SELECT 'OPEN',        SUBSCRIBER_KEY, JOB_ID
              FROM FIPSAR_SFMC_EVENTS.RAW_EVENTS.RAW_SFMC_OPENS
            UNION ALL
            SELECT 'CLICK',       SUBSCRIBER_KEY, JOB_ID
              FROM FIPSAR_SFMC_EVENTS.RAW_EVENTS.RAW_SFMC_CLICKS
            UNION ALL
            SELECT 'BOUNCE',      SUBSCRIBER_KEY, JOB_ID
              FROM FIPSAR_SFMC_EVENTS.RAW_EVENTS.RAW_SFMC_BOUNCES
            UNION ALL
            SELECT 'UNSUBSCRIBE', SUBSCRIBER_KEY, JOB_ID
              FROM FIPSAR_SFMC_EVENTS.RAW_EVENTS.RAW_SFMC_UNSUBSCRIBES
            UNION ALL
            SELECT 'SPAM',        SUBSCRIBER_KEY, JOB_ID
              FROM FIPSAR_SFMC_EVENTS.RAW_EVENTS.RAW_SFMC_SPAM
        )
        SELECT
            COALESCE(m.JOURNEY_TYPE, 'Unknown Journey')  AS journey_type,
            COALESCE(m.MAPPED_STAGE, 'Unknown Stage')    AS stage,
            e.event_type,
            COUNT(*)                                     AS event_count,
            COUNT(DISTINCT e.SUBSCRIBER_KEY)             AS unique_subscribers
        FROM raw_events e
        LEFT JOIN FIPSAR_DW.GOLD.DIM_SFMC_JOB m ON e.JOB_ID = m.JOB_ID
        WHERE 1=1
          {journey_filter_raw}
        GROUP BY 1, 2, 3
        ORDER BY 1, 2, 3
        LIMIT 200
    """)
    raw_result = _run(raw_sql)

    # Also add suppressed/fatal counts from DQ_REJECTION_LOG
    supp_sql = textwrap.dedent(f"""
        SELECT
            REJECTION_REASON                AS suppression_type,
            COUNT(*)                        AS count,
            MIN(CAST(REJECTED_AT AS DATE))  AS first_seen,
            MAX(CAST(REJECTED_AT AS DATE))  AS last_seen
        FROM FIPSAR_AUDIT.PIPELINE_AUDIT.DQ_REJECTION_LOG
        WHERE UPPER(REJECTION_REASON) IN ('SUPPRESSED', 'FATAL_ERROR')
          AND (
              TRY_TO_DATE(TRY_PARSE_JSON(REJECTED_RECORD):FILE_DATE::STRING)
                  BETWEEN '{start_date}' AND '{end_date}'
              OR CAST(REJECTED_AT AS DATE) BETWEEN '{start_date}' AND '{end_date}'
          )
        GROUP BY 1
        ORDER BY 2 DESC
    """)
    supp_result = _run(supp_sql)

    parts = [
        "**Source: Raw SFMC event tables (FACT_SFMC_ENGAGEMENT had no rows for this date range)**\n",
        "### Engagement Events by Journey / Stage\n" + raw_result,
        "### Suppression & Fatal Issues (DQ_REJECTION_LOG)\n" + supp_result,
    ]
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Tool 5: Date-specific drop analysis
# ---------------------------------------------------------------------------

@tool
def get_drop_analysis(target_date: str) -> str:
    """
    Investigate why prospect or send volume dropped on a specific date.
    Returns intake counts, rejection counts by reason, SFMC sent vs suppressed,
    and any pipeline errors logged on that date.

    Use this when the user asks:
    - "Why is there a drop on DATE X?"
    - "What happened on DATE X?"
    - "Why did we see fewer prospects on DATE X?"

    Args:
        target_date: The date to investigate (YYYY-MM-DD).

    Returns:
        Multi-signal drop diagnosis as markdown tables.
    """
    sql = textwrap.dedent(f"""
        -- Intake vs mastering on target date
        SELECT 'Lead Intake' AS signal,
               COUNT(*) AS count,
               '{target_date}' AS date
        FROM FIPSAR_PHI_HUB.STAGING.STG_PROSPECT_INTAKE
        WHERE FILE_DATE = '{target_date}'

        UNION ALL

        SELECT 'Valid Prospects Mastered' AS signal,
               COUNT(*) AS count,
               '{target_date}' AS date
        FROM FIPSAR_PHI_HUB.PHI_CORE.PHI_PROSPECT_MASTER
        WHERE FILE_DATE = '{target_date}'

        UNION ALL

        SELECT 'Rejected Leads - ' || REJECTION_REASON AS signal,
               COUNT(*) AS count,
               '{target_date}' AS date
        FROM FIPSAR_AUDIT.PIPELINE_AUDIT.DQ_REJECTION_LOG
        WHERE CAST(REJECTED_AT AS DATE) = '{target_date}'
          AND TABLE_NAME LIKE '%STG_PROSPECT_INTAKE%'
        GROUP BY REJECTION_REASON

        UNION ALL

        SELECT 'SFMC - ' || fe.EVENT_TYPE AS signal,
               COUNT(*) AS count,
               '{target_date}' AS date
        FROM FIPSAR_DW.GOLD.FACT_SFMC_ENGAGEMENT fe
        JOIN FIPSAR_DW.GOLD.DIM_DATE d ON fe.DATE_KEY = d.DATE_KEY
        WHERE d.FULL_DATE = '{target_date}'
        GROUP BY fe.EVENT_TYPE

        UNION ALL

        SELECT 'SFMC Suppression - ' || REJECTION_REASON AS signal,
               COUNT(*) AS count,
               '{target_date}' AS date
        FROM FIPSAR_AUDIT.PIPELINE_AUDIT.DQ_REJECTION_LOG
        WHERE REJECTION_REASON IN ('SUPPRESSED', 'FATAL_ERROR')
          AND CAST(REJECTED_AT AS DATE) = '{target_date}'
        GROUP BY REJECTION_REASON

        ORDER BY signal
    """)
    return _run(sql, max_rows=50)


# ---------------------------------------------------------------------------
# Tool 6: Prospect lineage trace
# ---------------------------------------------------------------------------

@tool
def trace_prospect(identifier: str) -> str:
    """
    Trace a specific prospect or lead through the entire FIPSAR pipeline:
    from intake → mastering → identity bridge → engagement events.

    Use this when the user asks:
    - "What happened to prospect X?"
    - "Show me the journey for email abc@example.com"
    - "Trace MASTER_PATIENT_ID P12345 through the pipeline"

    Args:
        identifier: Email address OR MASTER_PATIENT_ID of the prospect/lead.

    Returns:
        Pipeline trace results as markdown tables showing each layer.
    """
    # Determine if the identifier looks like an email or an ID
    is_email = "@" in identifier

    if is_email:
        match_clause_intake  = f"LOWER(EMAIL) = LOWER('{identifier}')"
        match_clause_master  = f"LOWER(EMAIL) = LOWER('{identifier}')"
        match_clause_xref    = f"LOWER(EMAIL) = LOWER('{identifier}')"
    else:
        # Treat as MASTER_PATIENT_ID
        match_clause_intake  = f"LOWER(FIRST_NAME) || ' ' || LOWER(LAST_NAME) LIKE '%{identifier.lower()}%'"
        match_clause_master  = f"MASTER_PATIENT_ID = '{identifier}'"
        match_clause_xref    = f"MASTER_PATIENT_ID = '{identifier}'"

    sql = textwrap.dedent(f"""
        -- Step 1: Intake / Lead layer
        SELECT 'A_Intake' AS layer, EMAIL, FIRST_NAME, LAST_NAME,
               CHANNEL, SUBMISSION_TIMESTAMP::STRING AS ts,
               'Lead' AS lifecycle_label
        FROM FIPSAR_PHI_HUB.STAGING.STG_PROSPECT_INTAKE
        WHERE {match_clause_intake}

        UNION ALL

        -- Step 2: Rejection log
        SELECT 'B_Rejected' AS layer,
               TRY_PARSE_JSON(REJECTED_RECORD):EMAIL::STRING AS EMAIL,
               TRY_PARSE_JSON(REJECTED_RECORD):FIRST_NAME::STRING AS FIRST_NAME,
               TRY_PARSE_JSON(REJECTED_RECORD):LAST_NAME::STRING AS LAST_NAME,
               REJECTION_REASON AS CHANNEL,
               REJECTED_AT::STRING AS ts,
               'Invalid Lead' AS lifecycle_label
        FROM FIPSAR_AUDIT.PIPELINE_AUDIT.DQ_REJECTION_LOG
        WHERE LOWER(TRY_PARSE_JSON(REJECTED_RECORD):EMAIL::STRING) = LOWER('{identifier if is_email else ""}')

        UNION ALL

        -- Step 3: Mastered Prospect
        SELECT 'C_Prospect' AS layer, EMAIL, FIRST_NAME, LAST_NAME,
               CHANNEL, SUBMISSION_TIMESTAMP::STRING AS ts,
               'Prospect' AS lifecycle_label
        FROM FIPSAR_PHI_HUB.PHI_CORE.PHI_PROSPECT_MASTER
        WHERE {match_clause_master}

        UNION ALL

        -- Step 4: Identity crosswalk (SFMC bridge)
        SELECT 'D_Identity_Xref' AS layer, EMAIL, FIRST_NAME, LAST_NAME,
               IDENTITY_KEY AS CHANNEL, NULL AS ts,
               'Identity Bridge' AS lifecycle_label
        FROM FIPSAR_PHI_HUB.PHI_CORE.PATIENT_IDENTITY_XREF
        WHERE {match_clause_xref}

        ORDER BY layer
        LIMIT 50
    """)
    base_result = _run(sql, max_rows=50)

    # Step 5: Also pull engagement if we have an identity key — do best-effort
    engagement_sql = textwrap.dedent(f"""
        SELECT fe.EVENT_TYPE, fe.EVENT_TIMESTAMP, j.JOURNEY_TYPE, j.MAPPED_STAGE,
               fe.SUBSCRIBER_KEY
        FROM FIPSAR_DW.GOLD.FACT_SFMC_ENGAGEMENT fe
        JOIN FIPSAR_DW.GOLD.DIM_SFMC_JOB j ON fe.JOB_KEY = j.JOB_KEY
        JOIN FIPSAR_PHI_HUB.PHI_CORE.PATIENT_IDENTITY_XREF x
             ON fe.SUBSCRIBER_KEY = x.IDENTITY_KEY
        WHERE {'LOWER(x.EMAIL) = LOWER(' + chr(39) + identifier + chr(39) + ')' if is_email
               else 'x.MASTER_PATIENT_ID = ' + chr(39) + identifier + chr(39)}
        ORDER BY fe.EVENT_TIMESTAMP
        LIMIT 50
    """)
    engagement_result = _run(engagement_sql, max_rows=50)

    return (
        "### Pipeline Trace — Intake / Mastering / Identity\n"
        + base_result
        + "\n\n### Pipeline Trace — SFMC Engagement Events\n"
        + engagement_result
    )


# ---------------------------------------------------------------------------
# Tool 7: AI intelligence — schema-safe, column-discovery based
# ---------------------------------------------------------------------------

def _discover_columns(full_table_name: str) -> list[str]:
    """Return actual column names for a table via INFORMATION_SCHEMA."""
    db, schema, table = full_table_name.split(".")
    sql = f"""
        SELECT COLUMN_NAME
        FROM {db}.INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = '{schema}'
          AND TABLE_NAME   = '{table}'
        ORDER BY ORDINAL_POSITION
    """
    result = execute_query_as_string(sql, max_rows=200)
    if result.startswith("ERROR") or "no rows" in result.lower():
        return []
    # Parse column names out of the markdown table
    cols = []
    for line in result.splitlines():
        line = line.strip()
        if line.startswith("|") and "COLUMN_NAME" not in line and "---" not in line:
            col = line.strip("|").strip()
            if col:
                cols.append(col)
    return cols


@tool
def get_ai_intelligence() -> str:
    """
    Discover the actual columns in all FIPSAR AI tables and return a
    representative sample of data from each table.

    Use this when the user asks about:
    - AI outcomes, AI scores, or model results
    - What AI data is available
    - Conversion probability, drop-off probability, suppression risk
    - Signal trust or send-time optimization scores

    This tool first discovers real column names, then queries each table safely.

    Returns:
        Schema + sample rows from each AI table as markdown.
    """
    ai_tables = [
        "FIPSAR_AI.AI_SEMANTIC.SEM_UCA_PROSPECT_360_SCORES",
        "FIPSAR_AI.AI_SEMANTIC.SEM_UCB_SIGNAL_TRUST_SCORES",
        "FIPSAR_AI.AI_SEMANTIC.SEM_UC03_SEND_TIME_SCORES",
        "FIPSAR_AI.AI_FEATURES.FEAT_UCA_PROSPECT_360",
        "FIPSAR_AI.AI_FEATURES.FEAT_UC03_SEND_TIME",
    ]
    output_parts = []
    for tbl in ai_tables:
        cols = _discover_columns(tbl)
        if not cols:
            output_parts.append(f"### {tbl}\n_Table not accessible or empty._\n")
            continue
        col_list = ", ".join(cols)
        count_sql  = f"SELECT COUNT(*) AS total_rows FROM {tbl}"
        sample_sql = f"SELECT {col_list} FROM {tbl} LIMIT 5"
        count_result  = execute_query_as_string(count_sql, max_rows=1)
        sample_result = execute_query_as_string(sample_sql, max_rows=5)
        output_parts.append(
            f"### {tbl}\n"
            f"**Columns:** {col_list}\n\n"
            f"**Row count:** {count_result}\n\n"
            f"**Sample rows:**\n{sample_result}\n"
        )
    return "\n\n".join(output_parts)


@tool
def get_prospect_conversion_analysis(
    start_date: str = "2020-01-01",
    end_date: str = "2099-12-31",
    active_only: bool = True,
) -> str:
    """
    Compute conversion probability and drop-off risk for active Prospects.

    Uses a 3-path strategy — always returns data regardless of which tables are populated:
      Path A: FACT_SFMC_ENGAGEMENT (engagement-based scores — richest signals)
      Path B: RAW_SFMC event tables (if gold engagement table is empty)
      Path C: PHI_PROSPECT_MASTER + DQ_REJECTION_LOG (always available — intake signals)

    Derived metrics:
      conversion_signal_score  (0–100): weighted click + open intensity
      dropoff_risk_score       (0–100): weighted bounce + unsub + suppression signals
      engagement_segment: High Engagement / Mid Engagement / At Risk / Low / No Activity

    Use this for:
    - "What is the conversion probability for active prospects?"
    - "What is the drop-off probability?"
    - "Which prospects are at risk of dropping off?"
    - "Show AI-level insights on active prospects"
    - "Who is most/least likely to convert?"

    Args:
        start_date:  Start of date range (YYYY-MM-DD).
        end_date:    End of date range (YYYY-MM-DD).
        active_only: Restrict to IS_ACTIVE = True prospects (default: True).

    Returns:
        Segment summary + ranked individual prospect scores.
    """
    active_filter = "AND p.IS_ACTIVE = TRUE" if active_only else ""
    parts = []

    # ------------------------------------------------------------------
    # PATH A: Gold engagement table — try without DIM_DATE join
    # Use EVENT_TIMESTAMP directly to avoid broken DATE_KEY → DIM_DATE join
    # ------------------------------------------------------------------
    path_a_check = execute_query_as_string(
        "SELECT COUNT(*) AS cnt FROM FIPSAR_DW.GOLD.FACT_SFMC_ENGAGEMENT", max_rows=1
    )
    engagement_rows = 0
    try:
        for line in path_a_check.splitlines():
            if "|" in line and "cnt" not in line and "---" not in line:
                val = line.strip("|").strip()
                if val.isdigit():
                    engagement_rows = int(val)
                    break
    except Exception:
        pass

    if engagement_rows > 0:
        seg_sql = textwrap.dedent(f"""
            WITH pe AS (
                SELECT
                    x.MASTER_PATIENT_ID,
                    p.FIRST_NAME, p.LAST_NAME, p.EMAIL, p.CHANNEL,
                    p.FILE_DATE AS intake_date,
                    COUNT(CASE WHEN fe.EVENT_TYPE = 'SENT'        THEN 1 END) AS sends,
                    COUNT(CASE WHEN fe.EVENT_TYPE = 'OPEN'        THEN 1 END) AS opens,
                    COUNT(CASE WHEN fe.EVENT_TYPE = 'CLICK'       THEN 1 END) AS clicks,
                    COUNT(CASE WHEN fe.EVENT_TYPE = 'BOUNCE'      THEN 1 END) AS bounces,
                    COUNT(CASE WHEN fe.EVENT_TYPE = 'UNSUBSCRIBE' THEN 1 END) AS unsubscribes,
                    COUNT(CASE WHEN fe.EVENT_TYPE = 'SPAM'        THEN 1 END) AS spam_complaints,
                    MAX(fe.EVENT_TIMESTAMP)                                    AS last_event_ts
                FROM FIPSAR_PHI_HUB.PHI_CORE.PHI_PROSPECT_MASTER p
                JOIN FIPSAR_PHI_HUB.PHI_CORE.PATIENT_IDENTITY_XREF x
                     ON p.MASTER_PATIENT_ID = x.MASTER_PATIENT_ID
                JOIN FIPSAR_DW.GOLD.FACT_SFMC_ENGAGEMENT fe
                     ON x.IDENTITY_KEY = fe.SUBSCRIBER_KEY
                WHERE fe.EVENT_TIMESTAMP BETWEEN '{start_date}' AND '{end_date}'
                  {active_filter}
                GROUP BY 1,2,3,4,5,6
            )
            SELECT
                MASTER_PATIENT_ID        AS master_prospect_id,
                FIRST_NAME, LAST_NAME, EMAIL, CHANNEL, intake_date,
                sends, opens, clicks, bounces, unsubscribes,
                ROUND((opens + clicks) * 100.0 / NULLIF(sends,0), 1)       AS engagement_rate_pct,
                ROUND(LEAST(100,(clicks*2.0 + opens*1.0)/NULLIF(sends,0)*50),1) AS conversion_signal_score,
                ROUND(LEAST(100,(bounces*1.5 + unsubscribes*2.0 + spam_complaints*3.0)/NULLIF(sends,0)*50),1) AS dropoff_risk_score,
                CASE
                    WHEN clicks > 0                           THEN 'High Engagement — Conversion Candidate'
                    WHEN opens > 0 AND clicks = 0             THEN 'Mid Engagement — Nurture Needed'
                    WHEN bounces > 0 OR unsubscribes > 0      THEN 'At Risk — Drop-off Signal'
                    WHEN sends > 0 AND opens = 0              THEN 'Low Engagement — Re-engagement Candidate'
                    ELSE 'No Activity'
                END AS engagement_segment
            FROM pe
            ORDER BY conversion_signal_score DESC, dropoff_risk_score ASC
            LIMIT 100
        """)
        detail_result = _run(seg_sql, max_rows=100)

        summary_sql = textwrap.dedent(f"""
            WITH pe AS (
                SELECT x.MASTER_PATIENT_ID,
                    COUNT(CASE WHEN fe.EVENT_TYPE='SENT'        THEN 1 END) AS sends,
                    COUNT(CASE WHEN fe.EVENT_TYPE='OPEN'        THEN 1 END) AS opens,
                    COUNT(CASE WHEN fe.EVENT_TYPE='CLICK'       THEN 1 END) AS clicks,
                    COUNT(CASE WHEN fe.EVENT_TYPE='BOUNCE'      THEN 1 END) AS bounces,
                    COUNT(CASE WHEN fe.EVENT_TYPE='UNSUBSCRIBE' THEN 1 END) AS unsubscribes
                FROM FIPSAR_PHI_HUB.PHI_CORE.PHI_PROSPECT_MASTER p
                JOIN FIPSAR_PHI_HUB.PHI_CORE.PATIENT_IDENTITY_XREF x
                     ON p.MASTER_PATIENT_ID = x.MASTER_PATIENT_ID
                JOIN FIPSAR_DW.GOLD.FACT_SFMC_ENGAGEMENT fe
                     ON x.IDENTITY_KEY = fe.SUBSCRIBER_KEY
                WHERE fe.EVENT_TIMESTAMP BETWEEN '{start_date}' AND '{end_date}'
                  {active_filter}
                GROUP BY 1
            ),
            seg AS (
                SELECT
                    CASE WHEN clicks>0 THEN 'High Engagement — Conversion Candidate'
                         WHEN opens>0 AND clicks=0 THEN 'Mid Engagement — Nurture Needed'
                         WHEN bounces>0 OR unsubscribes>0 THEN 'At Risk — Drop-off Signal'
                         WHEN sends>0 AND opens=0 THEN 'Low Engagement — Re-engagement Candidate'
                         ELSE 'No Activity' END AS segment,
                    COUNT(*) AS prospect_count,
                    ROUND(AVG((opens+clicks)*100.0/NULLIF(sends,0)),1) AS avg_engagement_rate_pct
                FROM pe GROUP BY 1
            )
            SELECT segment, prospect_count, avg_engagement_rate_pct,
                   ROUND(prospect_count*100.0/SUM(prospect_count) OVER(),1) AS pct_of_total
            FROM seg ORDER BY prospect_count DESC
        """)
        parts.append("**Data source: SFMC engagement events (Path A — richest signals)**\n")
        parts.append("### Segment Summary\n" + _run(summary_sql, max_rows=10))
        parts.append("### Individual Prospect Scores (ranked by conversion signal)\n" + detail_result)

    # ------------------------------------------------------------------
    # PATH B: RAW_SFMC event tables — fallback when gold table is empty
    # ------------------------------------------------------------------
    elif engagement_rows == 0:
        raw_check = execute_query_as_string(
            "SELECT COUNT(*) AS cnt FROM FIPSAR_SFMC_EVENTS.RAW_EVENTS.RAW_SFMC_SENT",
            max_rows=1,
        )
        raw_rows = 0
        try:
            for line in raw_check.splitlines():
                if "|" in line and "cnt" not in line and "---" not in line:
                    val = line.strip("|").strip()
                    if val.isdigit():
                        raw_rows = int(val)
                        break
        except Exception:
            pass

        if raw_rows > 0:
            raw_sql = textwrap.dedent(f"""
                SELECT
                    s.SUBSCRIBER_KEY,
                    COUNT(DISTINCT s.JOB_ID)                              AS total_sends,
                    COUNT(DISTINCT o.JOB_ID)                              AS total_opens,
                    COUNT(DISTINCT c.JOB_ID)                              AS total_clicks,
                    COUNT(DISTINCT b.JOB_ID)                              AS total_bounces,
                    COUNT(DISTINCT u.JOB_ID)                              AS total_unsubscribes,
                    ROUND(COUNT(DISTINCT o.JOB_ID)*100.0/NULLIF(COUNT(DISTINCT s.JOB_ID),0),1)
                                                                          AS open_rate_pct,
                    ROUND(COUNT(DISTINCT c.JOB_ID)*100.0/NULLIF(COUNT(DISTINCT s.JOB_ID),0),1)
                                                                          AS click_rate_pct,
                    CASE
                        WHEN COUNT(DISTINCT c.JOB_ID) > 0             THEN 'High Engagement — Conversion Candidate'
                        WHEN COUNT(DISTINCT o.JOB_ID) > 0             THEN 'Mid Engagement — Nurture Needed'
                        WHEN COUNT(DISTINCT b.JOB_ID) > 0
                          OR COUNT(DISTINCT u.JOB_ID) > 0             THEN 'At Risk — Drop-off Signal'
                        ELSE 'Low Engagement — Re-engagement Candidate'
                    END AS engagement_segment
                FROM FIPSAR_SFMC_EVENTS.RAW_EVENTS.RAW_SFMC_SENT s
                LEFT JOIN FIPSAR_SFMC_EVENTS.RAW_EVENTS.RAW_SFMC_OPENS       o ON s.SUBSCRIBER_KEY = o.SUBSCRIBER_KEY
                LEFT JOIN FIPSAR_SFMC_EVENTS.RAW_EVENTS.RAW_SFMC_CLICKS      c ON s.SUBSCRIBER_KEY = c.SUBSCRIBER_KEY
                LEFT JOIN FIPSAR_SFMC_EVENTS.RAW_EVENTS.RAW_SFMC_BOUNCES     b ON s.SUBSCRIBER_KEY = b.SUBSCRIBER_KEY
                LEFT JOIN FIPSAR_SFMC_EVENTS.RAW_EVENTS.RAW_SFMC_UNSUBSCRIBES u ON s.SUBSCRIBER_KEY = u.SUBSCRIBER_KEY
                GROUP BY 1
                ORDER BY click_rate_pct DESC, open_rate_pct DESC
                LIMIT 100
            """)
            parts.append("**Data source: Raw SFMC event tables (Path B — gold table currently empty)**\n")
            parts.append("### Prospect Engagement Scores from Raw Events\n" + _run(raw_sql, max_rows=100))

    # ------------------------------------------------------------------
    # PATH C: Prospect master — ALWAYS runs, provides intake-based signals
    # Active = mastered + IS_ACTIVE; Dropped = mastered but IS_ACTIVE = FALSE
    # Suppression = in DQ_REJECTION_LOG with SUPPRESSED/FATAL_ERROR
    # ------------------------------------------------------------------
    master_sql = textwrap.dedent(f"""
        SELECT
            p.CHANNEL,
            p.PATIENT_CONSENT                                              AS consent_status,
            COUNT(*)                                                       AS total_prospects,
            SUM(CASE WHEN p.IS_ACTIVE = TRUE  THEN 1 ELSE 0 END)          AS active_prospects,
            SUM(CASE WHEN p.IS_ACTIVE = FALSE THEN 1 ELSE 0 END)          AS inactive_prospects,
            ROUND(SUM(CASE WHEN p.IS_ACTIVE=TRUE  THEN 1 ELSE 0 END)*100.0/COUNT(*),1)
                                                                           AS active_rate_pct,
            ROUND(SUM(CASE WHEN p.IS_ACTIVE=FALSE THEN 1 ELSE 0 END)*100.0/COUNT(*),1)
                                                                           AS dropoff_rate_pct
        FROM FIPSAR_PHI_HUB.PHI_CORE.PHI_PROSPECT_MASTER p
        WHERE p.FILE_DATE BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY 1, 2
        ORDER BY total_prospects DESC
        LIMIT 50
    """)

    suppression_sql = textwrap.dedent(f"""
        SELECT
            REJECTION_REASON,
            COUNT(*)                                                       AS count,
            ROUND(COUNT(*)*100.0 / (
                SELECT COUNT(*) FROM FIPSAR_PHI_HUB.PHI_CORE.PHI_PROSPECT_MASTER
                WHERE FILE_DATE BETWEEN '{start_date}' AND '{end_date}'
            ), 2)                                                          AS pct_of_prospects
        FROM FIPSAR_AUDIT.PIPELINE_AUDIT.DQ_REJECTION_LOG
        WHERE UPPER(REJECTION_REASON) IN ('SUPPRESSED','FATAL_ERROR')
          AND (
              TRY_TO_DATE(TRY_PARSE_JSON(REJECTED_RECORD):FILE_DATE::STRING)
                  BETWEEN '{start_date}' AND '{end_date}'
              OR CAST(REJECTED_AT AS DATE) BETWEEN '{start_date}' AND '{end_date}'
          )
        GROUP BY 1
        ORDER BY 2 DESC
    """)

    parts.append(
        "**Data source: Prospect Master — intake-based activity & drop-off signals (Path C)**\n"
        "\n### Active vs Inactive Breakdown by Channel & Consent\n"
        + _run(master_sql, max_rows=50)
        + "\n\n### SFMC Send Suppression Signals (drop-off risk for mastered prospects)\n"
        + _run(suppression_sql, max_rows=10)
    )

    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Tool 8: Pipeline observability
# ---------------------------------------------------------------------------

@tool
def get_pipeline_observability(
    start_date: str = "2020-01-01",
    end_date: str = "2099-12-31",
) -> str:
    """
    Return pipeline run health: execution logs, DQ signal counts, and
    table-level row counts from the audit layer.

    Use this when the user asks about:
    - Pipeline health or run status
    - Data quality issue counts
    - Whether a pipeline run succeeded or failed
    - Observability across the data flow

    Args:
        start_date: Start of date range (YYYY-MM-DD).
        end_date:   End of date range (YYYY-MM-DD).

    Returns:
        Pipeline run + DQ signal summary as a markdown table.
    """
    sql = textwrap.dedent(f"""
        -- Pipeline run log summary
        SELECT
            TABLE_NAME,
            STATUS,
            COUNT(*) AS run_count,
            MIN(RUN_START_TIME)::STRING AS earliest_run,
            MAX(RUN_END_TIME)::STRING AS latest_run
        FROM FIPSAR_AUDIT.PIPELINE_AUDIT.PIPELINE_RUN_LOG
        WHERE CAST(RUN_START_TIME AS DATE) BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY 1, 2
        ORDER BY 3 DESC
        LIMIT 50
    """)
    run_result = _run(sql)

    dq_sql = textwrap.dedent(f"""
        SELECT
            TABLE_NAME,
            REJECTION_REASON,
            COUNT(*) AS rejection_count,
            MIN(CAST(REJECTED_AT AS DATE))::STRING AS first_seen,
            MAX(CAST(REJECTED_AT AS DATE))::STRING AS last_seen
        FROM FIPSAR_AUDIT.PIPELINE_AUDIT.DQ_REJECTION_LOG
        WHERE CAST(REJECTED_AT AS DATE) BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY 1, 2
        ORDER BY 3 DESC
        LIMIT 50
    """)
    dq_result = _run(dq_sql)

    return (
        "### Pipeline Run Log\n" + run_result
        + "\n\n### DQ Rejection Summary\n" + dq_result
    )


# ---------------------------------------------------------------------------
# Tool 9: Individual rejected lead records
# ---------------------------------------------------------------------------

@tool
def get_rejected_lead_details(
    start_date: str = "2020-01-01",
    end_date: str = "2099-12-31",
    rejection_reason: Optional[str] = None,
    rejection_category: str = "intake",
    limit: int = 100,
) -> str:
    """
    Return individual rejected lead records (row-level) from DQ_REJECTION_LOG.

    CRITICAL DISTINCTION — use rejection_category to target the right records:

    - rejection_category="intake"  (DEFAULT) → Individual leads rejected during mastering.
      These are Invalid Leads: NULL_EMAIL, NO_CONSENT, missing mandatory fields.
      Use this when user asks: "list the rejected leads", "show me who got rejected",
      "display the invalid leads", "what are the rejected lead IDs".

    - rejection_category="sfmc"  → Individual SFMC send suppressions/errors.
      Use this when user asks: "list suppressed sends", "show FATAL_ERROR records".

    - rejection_category="all"   → All rejection records.

    Args:
        start_date:          Start of FILE_DATE range (YYYY-MM-DD).
        end_date:            End of FILE_DATE range (YYYY-MM-DD).
        rejection_reason:    Optional specific reason filter (e.g. 'NULL_EMAIL').
        rejection_category:  "intake" (default), "sfmc", or "all".
        limit:               Max rows to return (default 100).

    Returns:
        Row-level rejected lead records as a markdown table.
    """
    reason_filter = (
        f"AND UPPER(REJECTION_REASON) = '{rejection_reason.upper()}'"
        if rejection_reason
        else ""
    )
    if rejection_category == "intake":
        category_filter = "AND UPPER(REJECTION_REASON) NOT IN ('SUPPRESSED', 'FATAL_ERROR')"
    elif rejection_category == "sfmc":
        category_filter = "AND UPPER(REJECTION_REASON) IN ('SUPPRESSED', 'FATAL_ERROR')"
    else:
        category_filter = ""
    sql = textwrap.dedent(f"""
        SELECT
            REJECTION_ID,
            CAST(REJECTED_AT AS DATE)                                   AS rejected_at_date,
            TABLE_NAME,
            REJECTION_REASON,
            TRY_PARSE_JSON(REJECTED_RECORD):FILE_DATE::STRING           AS lead_file_date,
            TRY_PARSE_JSON(REJECTED_RECORD):FIRST_NAME::STRING          AS first_name,
            TRY_PARSE_JSON(REJECTED_RECORD):LAST_NAME::STRING           AS last_name,
            TRY_PARSE_JSON(REJECTED_RECORD):EMAIL::STRING               AS email,
            TRY_PARSE_JSON(REJECTED_RECORD):PHONE_NUMBER::STRING        AS phone_number,
            TRY_PARSE_JSON(REJECTED_RECORD):CHANNEL::STRING             AS channel,
            TRY_PARSE_JSON(REJECTED_RECORD):PATIENT_CONSENT::STRING     AS consent_flag
        FROM FIPSAR_AUDIT.PIPELINE_AUDIT.DQ_REJECTION_LOG
        WHERE
            -- Primary match: FILE_DATE embedded in the rejected record JSON
            (
                TRY_TO_DATE(TRY_PARSE_JSON(REJECTED_RECORD):FILE_DATE::STRING)
                    BETWEEN '{start_date}' AND '{end_date}'
            )
            -- Fallback: if FILE_DATE is not in the JSON, match on pipeline processing date
            OR (
                TRY_TO_DATE(TRY_PARSE_JSON(REJECTED_RECORD):FILE_DATE::STRING) IS NULL
                AND CAST(REJECTED_AT AS DATE) BETWEEN '{start_date}' AND '{end_date}'
            )
          {reason_filter}
          {category_filter}
        ORDER BY lead_file_date DESC NULLS LAST, rejected_at_date DESC
        LIMIT {limit}
    """)
    return _run(sql, max_rows=limit)


# ---------------------------------------------------------------------------
# Tool 10: Individual valid prospect records
# ---------------------------------------------------------------------------

@tool
def get_prospect_details(
    start_date: str = "2020-01-01",
    end_date: str = "2099-12-31",
    channel: Optional[str] = None,
    state: Optional[str] = None,
    limit: int = 100,
) -> str:
    """
    Return individual valid mastered Prospect records from PHI_PROSPECT_MASTER
    (or DIM_PROSPECT for enriched analytics view), with key identity and
    intake details.

    Use this when the user asks to:
    - "List the prospects who converted in January 2026"
    - "Show me individual prospect records"
    - "Give me the granularity / details of valid prospects"
    - "Who are the prospects that came in via channel X?"
    - "List valid prospects in state Y"

    Args:
        start_date: Inclusive start of FILE_DATE range (YYYY-MM-DD).
        end_date:   Inclusive end of FILE_DATE range (YYYY-MM-DD).
        channel:    Optional channel filter, e.g. 'WEB', 'APP', 'FORM'.
        state:      Optional US state filter, e.g. 'CA', 'TX'.
        limit:      Maximum number of records to return (default 100).

    Returns:
        Row-level valid prospect records as a markdown table.
    """
    channel_filter = f"AND UPPER(CHANNEL) = '{channel.upper()}'" if channel else ""
    state_filter   = f"AND UPPER(STATE) = '{state.upper()}'"     if state   else ""

    sql = textwrap.dedent(f"""
        SELECT
            MASTER_PATIENT_ID           AS master_prospect_id,
            RECORD_ID,
            FIRST_NAME,
            LAST_NAME,
            EMAIL,
            PHONE_NUMBER,
            PATIENT_CONSENT             AS consent_flag,
            CHANNEL,
            FILE_DATE,
            SUBMISSION_TIMESTAMP::STRING AS submitted_at,
            IS_ACTIVE
        FROM FIPSAR_PHI_HUB.PHI_CORE.PHI_PROSPECT_MASTER
        WHERE FILE_DATE BETWEEN '{start_date}' AND '{end_date}'
          {channel_filter}
          {state_filter}
        ORDER BY FILE_DATE DESC, SUBMISSION_TIMESTAMP DESC
        LIMIT {limit}
    """)
    return _run(sql, max_rows=limit)


# ---------------------------------------------------------------------------
# Chart tools (12–16): wrap charts.py generators as LangChain tools
# ---------------------------------------------------------------------------

import charts as _charts   # late import to avoid circular at module level


@tool
def chart_smart(
    sql: str,
    title: str,
    chart_type: str = "auto",
    x_col: Optional[str] = None,
    y_col: Optional[str] = None,
    color_col: Optional[str] = None,
    orientation: str = "v",
) -> str:
    """
    GENERALISED chart tool — use this for ANY question where the user wants a visual chart
    and none of the specific chart tools fit, OR when you want full control over what is plotted.

    Steps to use:
      1. Write a SELECT query that returns the data you want to visualise.
      2. Choose chart_type: "bar", "line", "area", "pie", "donut", "funnel", "scatter", or "auto".
      3. Specify x_col (category/time axis) and y_col (value axis). Leave None to auto-detect.

    When to use this vs specific chart tools:
      - Use chart_funnel / chart_rejections / chart_engagement etc. for common pre-built charts.
      - Use THIS tool for: custom breakdowns, ad-hoc comparisons, channel mix charts,
        state/region distributions, consent rate charts, age group charts, any custom metric.

    Examples:
      - "Show me prospect count by state" → bar chart, x=STATE, y=count
      - "Plot rejection trend by month"   → line chart on monthly grouped SQL
      - "Compare channel mix for 2025 vs 2026" → grouped bar with color_col=year

    Args:
        sql:         A valid Snowflake SELECT returning at least 2 columns.
        title:       Chart title shown to the user.
        chart_type:  "auto", "bar", "line", "area", "pie", "donut", "funnel", "scatter".
        x_col:       Column name for x-axis / labels (auto-detect if None).
        y_col:       Column name for y-axis / values (auto-detect if None).
        color_col:   Column for grouping/colouring series (optional).
        orientation: "v" (vertical, default) or "h" (horizontal bars).
    """
    return _charts.smart_chart(
        sql=sql, chart_type=chart_type, title=title,
        x_col=x_col, y_col=y_col, color_col=color_col, orientation=orientation,
    )


@tool
def chart_funnel(start_date: str = "2020-01-01", end_date: str = "2099-12-31") -> str:
    """
    Generate and display a Prospect Journey Funnel chart showing volume at each stage:
    Lead Intake → Valid Prospects → SFMC Sent → Opened → Clicked.

    Use this whenever the user asks for a funnel chart, funnel visualisation,
    or wants to SEE the funnel visually (not just numbers).

    Args:
        start_date: Start of date range (YYYY-MM-DD).
        end_date:   End of date range (YYYY-MM-DD).
    """
    return _charts.funnel_chart(start_date, end_date)


@tool
def chart_rejections(
    start_date: str = "2020-01-01",
    end_date: str = "2099-12-31",
    rejection_category: str = "all",
) -> str:
    """
    Generate and display a donut chart of rejection reasons.

    Use this when the user asks to visualise/chart:
    - Rejection reasons breakdown
    - Why leads were dropped (chart)
    - SFMC suppression chart

    Args:
        start_date:          Start of date range (YYYY-MM-DD).
        end_date:            End of date range (YYYY-MM-DD).
        rejection_category:  "intake" for mastering rejections, "sfmc" for suppressions, "all" for both.
    """
    return _charts.rejection_chart(start_date, end_date, rejection_category)


@tool
def chart_engagement(
    start_date: str = "2020-01-01",
    end_date: str = "2099-12-31",
    journey_type: Optional[str] = None,
) -> str:
    """
    Generate and display a grouped bar chart of SFMC engagement events by journey and event type
    (SENT, OPEN, CLICK, BOUNCE, UNSUBSCRIBE, SPAM).

    Use this when the user asks to visualise/chart:
    - SFMC engagement
    - Journey performance visually
    - Email event breakdown chart

    Args:
        start_date:   Start of date range (YYYY-MM-DD).
        end_date:     End of date range (YYYY-MM-DD).
        journey_type: Optional journey filter (e.g. 'Welcome', 'Nurture').
    """
    return _charts.engagement_chart(start_date, end_date, journey_type)


@tool
def chart_conversion_segments(
    start_date: str = "2020-01-01",
    end_date: str = "2099-12-31",
) -> str:
    """
    Generate and display a dual donut chart:
    - Left: Engagement segments (High / Mid / At Risk / Low / No Activity)
    - Right: Active vs Inactive/Dropped prospect status

    Use this when the user asks to visualise/chart:
    - Conversion segments
    - Drop-off risk chart
    - Engagement distribution visually
    - Active vs inactive prospects chart

    Args:
        start_date: Start of date range (YYYY-MM-DD).
        end_date:   End of date range (YYYY-MM-DD).
    """
    return _charts.conversion_segment_chart(start_date, end_date)


@tool
def chart_intake_trend(
    start_date: str = "2020-01-01",
    end_date: str = "2099-12-31",
    group_by: str = "month",
) -> str:
    """
    Generate and display a time-series line chart of lead intake volume and
    valid prospect count over time.

    Use this when the user asks to visualise/chart:
    - Lead or prospect intake trend
    - Volume over time
    - Monthly/weekly/daily intake chart

    Args:
        start_date: Start of date range (YYYY-MM-DD).
        end_date:   End of date range (YYYY-MM-DD).
        group_by:   Time granularity — "day", "week", or "month".
    """
    return _charts.intake_trend_chart(start_date, end_date, group_by)


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

ALL_TOOLS = [
    run_sql,
    get_funnel_metrics,
    get_rejection_analysis,
    get_sfmc_engagement_stats,
    get_drop_analysis,
    trace_prospect,
    get_ai_intelligence,
    get_prospect_conversion_analysis,
    get_pipeline_observability,
    get_rejected_lead_details,
    get_prospect_details,
    chart_smart,
    chart_funnel,
    chart_rejections,
    chart_engagement,
    chart_conversion_segments,
    chart_intake_trend,
]


# ---------------------------------------------------------------------------
# Tool 18: Report Email (FREL Agent only)
# ---------------------------------------------------------------------------

@tool
def send_report_email(subject: str, report_content: str) -> str:
    """
    Send a formatted FIPSAR Intelligence report email to akilesh@fipsar.com.

    Use this tool AFTER you have already gathered all the data and (optionally)
    generated charts using the chart tools. This tool will:
      - Compose a professional branded HTML email
      - Embed any charts that were generated during this conversation turn as inline images
      - Send via SMTP and return a delivery confirmation

    WHEN TO USE:
      - User says "send me an email", "email the report", "send this over email",
        "mail me the results", "send the chart by email", etc.

    WORKFLOW (always follow this order):
      1. Call the relevant data tools to gather the information requested
      2. Call chart tools if the user wants a chart in the email
      3. Call send_report_email LAST with a clear subject and the full report as report_content

    Args:
        subject: A clear, descriptive email subject line.
                 Example: "FIPSAR Funnel Report — January 2026"
        report_content: The full report in markdown format. Include all tables,
                        metrics, and insights gathered from your data tool calls.
                        Be comprehensive — the recipient will read this in their inbox.

    Returns:
        Delivery confirmation string with recipient, subject, and chart count.
    """
    import chart_store
    from email_sender import send_email

    # Grab any charts generated during this agent turn (non-destructive peek)
    chart_figures = chart_store.peek_all_current()

    result = send_email(
        subject=subject,
        report_markdown=report_content,
        chart_figures=chart_figures,
    )

    if result["success"]:
        charts_note = (
            f" {result['charts_attached']} chart(s) embedded as inline images."
            if result["charts_attached"] > 0
            else " No charts were attached (no chart tools were called before this tool)."
        )
        return (
            f"✅ Email sent successfully.\n"
            f"  To: {result['to']}\n"
            f"  Subject: {result['subject']}\n"
            f" {charts_note}"
        )
    else:
        return f"❌ Email could not be sent.\n  Reason: {result['message']}"


# FREL Agent tool list: all 17 data+chart tools + the email tool
FREL_TOOLS = ALL_TOOLS + [send_report_email]

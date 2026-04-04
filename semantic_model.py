"""
semantic_model.py
-----------------
Loads the SFMC Prospects semantic model YAML and produces:
  1. A rich system-prompt string for the LangGraph agent.
  2. Helper accessors for tables, metrics, journeys, rules, etc.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------

_YAML_PATH = Path(__file__).parent / "SFMC_Prospects_Semmantic_Model.yaml"


def _load_yaml() -> dict[str, Any]:
    with open(_YAML_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


_MODEL: dict[str, Any] = _load_yaml()
_SL: dict[str, Any] = _MODEL.get("semantic_layer", {})


# ---------------------------------------------------------------------------
# Public accessors
# ---------------------------------------------------------------------------

def get_physical_tables() -> dict[str, Any]:
    """Return the full physical_data_model section."""
    return _SL.get("physical_data_model", {})


def get_funnel_stages() -> list[dict]:
    return _SL.get("funnel_model", {}).get("stages", [])


def get_journeys() -> list[dict]:
    return _SL.get("journey_definition", {}).get("journeys", [])


def get_canonical_kpis() -> list[dict]:
    return _SL.get("metrics", {}).get("canonical_kpis", [])


def get_business_rules() -> dict[str, Any]:
    return _SL.get("business_rules", {})


def get_relationships() -> list[dict]:
    return _SL.get("relationships", {}).get("canonical_joins", [])


def get_lineage() -> list[str]:
    return _SL.get("lineage_summary", {}).get("canonical_flow", [])


# ---------------------------------------------------------------------------
# System-prompt builder
# ---------------------------------------------------------------------------

def build_system_prompt() -> str:
    """
    Construct the full system prompt that grounds the conversational agent
    in the FIPSAR Prospect Journey Intelligence semantic model.
    """

    # --- Overview ---
    overview = f"""
You are the FIPSAR Prospect Journey Intelligence AI assistant.
You have deep expertise in the FIPSAR data platform, which tracks marketing leads
through validation, mastering, Salesforce Marketing Cloud (SFMC) journeys, and
engagement analytics.

PLATFORM PURPOSE:
{_SL.get("high_level_goal", {}).get("summary", "")}

CLOSED-LOOP INTELLIGENCE PATTERN:
{_SL.get("high_level_goal", {}).get("closed_loop_intelligence_pattern", "")}
""".strip()

    # --- Terminology ---
    terms = _SL.get("terminology", {}).get("canonical_terms", {})
    term_lines = []
    for term, info in terms.items():
        defn = info.get("definition", "").replace("\n", " ").strip()
        term_lines.append(f"  - {term.upper()}: {defn}")
    terminology_section = "KEY BUSINESS TERMINOLOGY (STRICTLY ENFORCE):\n" + "\n".join(term_lines)

    # --- Naming rules ---
    naming_rules = _SL.get("naming_conventions", {}).get("business_naming_rules", [])
    naming_section = "NAMING RULES:\n" + "\n".join(f"  - {r}" for r in naming_rules)

    # --- Physical data model (tables) ---
    pdm = get_physical_tables()
    table_lines = ["PHYSICAL DATA MODEL — DATABASES, SCHEMAS, TABLES:"]
    for db_name, db_info in pdm.get("databases", {}).items():
        table_lines.append(f"\nDATABASE: {db_name} — {db_info.get('description', '')}")
        for schema_name, schema_info in db_info.get("schemas", {}).items():
            for tbl_name, tbl_info in schema_info.get("tables", {}).items():
                grain   = tbl_info.get("grain", "")
                role    = tbl_info.get("business_role", "")
                label   = tbl_info.get("lifecycle_label", "")
                cols    = tbl_info.get("key_columns", tbl_info.get("important_columns", []))
                col_str = ", ".join(cols) if cols else "see schema"
                table_lines.append(
                    f"  TABLE: {tbl_name}\n"
                    f"    Grain: {grain} | Role: {role}"
                    + (f" | Lifecycle: {label}" if label else "")
                    + f"\n    Key columns: {col_str}"
                )
    table_section = "\n".join(table_lines)

    # --- Business rules ---
    br = get_business_rules()
    imr = br.get("intake_mastering_rules", {})
    rejection_reasons = imr.get("rejection_reasons", {}).get("canonical_values", [])
    sfmc_rules = br.get("sfmc_event_rules", {})
    valid_event_types = sfmc_rules.get("valid_event_types", [])
    suppression_reasons = sfmc_rules.get("suppression_outcomes", {}).get("rejection_reasons", [])

    sfmc_data_access = sfmc_rules.get("data_access_rules", [])
    sfmc_access_str  = "\n    ".join(f"- {r}" for r in sfmc_data_access) if sfmc_data_access else ""

    rules_section = f"""BUSINESS RULES:
  Lead Intake & Mastering:
    Mandatory fields: {', '.join(imr.get("mandatory_fields", []))}
    Consent rule: {imr.get("consent_rule", {}).get("rule", "")}
    Valid outcome: {imr.get("valid_outcome", {}).get("result", "")}
    Invalid outcome: {imr.get("invalid_outcome", {}).get("result", "")}
    Rejection reasons: {', '.join(rejection_reasons)}

  SFMC Event Rules:
    Valid event types: {', '.join(valid_event_types)}
    Suppression/fatal reasons: {', '.join(suppression_reasons)}
    Observability: Suppressed/fatal outcomes are NOT silent — they must be measurable.
    Data Access Rules (CRITICAL — must follow for correct SFMC queries):
    {sfmc_access_str}"""

    # --- Funnel stages ---
    funnel_lines = ["FUNNEL STAGES (F01 → F08):"]
    for stage in get_funnel_stages():
        sid = stage.get("stage_id", "")
        sname = stage.get("name", "")
        entity = stage.get("entity_label", "")
        metrics = ", ".join(stage.get("metric_examples", []))
        tables = stage.get("source_table") or ", ".join(stage.get("source_tables", []))
        funnel_lines.append(
            f"  {sid} — {sname} | Entity: {entity}\n"
            f"       Source: {tables}\n"
            f"       Metrics: {metrics}"
        )
    funnel_section = "\n".join(funnel_lines)

    # --- Journeys ---
    journey_lines = ["SFMC JOURNEY DEFINITIONS:"]
    for j in get_journeys():
        journey_lines.append(f"  {j.get('journey_code')} — {j.get('journey_name')}")
        for s in j.get("stages", []):
            emails = ", ".join(s.get("email_names", []))
            journey_lines.append(
                f"    Stage {s.get('stage_number')}: {s.get('stage_name')} → emails: {emails}"
            )
    journey_section = "\n".join(journey_lines)

    # --- Canonical KPIs ---
    kpi_lines = ["CANONICAL KPIs / METRICS:"]
    for kpi in get_canonical_kpis():
        kpi_lines.append(f"  {kpi.get('name')}: {kpi.get('definition')}")
    kpi_section = "\n".join(kpi_lines)

    # --- Relationships / joins ---
    rel_lines = ["KEY JOIN RELATIONSHIPS:"]
    for rel in get_relationships():
        if isinstance(rel, dict):
            name = rel.get("name", "")
            frm  = rel.get("from", "")
            to   = rel.get("to", "")
            card = rel.get("cardinality", "")
            if isinstance(frm, list):
                frm = ", ".join(frm)
            if isinstance(to, list):
                to = ", ".join(to)
            rel_lines.append(f"  {name}: {frm} → {to} ({card})")
    rel_section = "\n".join(rel_lines)

    # --- Lineage ---
    lineage_section = "DATA LINEAGE FLOW:\n" + "\n".join(
        f"  {i+1}. {step}" for i, step in enumerate(get_lineage())
    )

    # --- Conversational guidance ---
    conv = _SL.get("conversational_guidance", {})
    answering_rules = conv.get("answering_rules", [])
    refusal_rules   = conv.get("refusal_rules", [])
    answering_section = (
        "ANSWERING RULES (always follow):\n"
        + "\n".join(f"  - {r}" for r in answering_rules)
        + "\n\nREFUSAL RULES (never violate):\n"
        + "\n".join(f"  - {r}" for r in refusal_rules)
    )

    # --- SQL generation instructions ---
    sql_instructions = """
SQL GENERATION INSTRUCTIONS:
  - Always use fully qualified table names: DATABASE.SCHEMA.TABLE
  - The FIPSAR databases are: FIPSAR_PHI_HUB, FIPSAR_DW, FIPSAR_SFMC_EVENTS, FIPSAR_AUDIT, FIPSAR_AI
  - When physical columns say MASTER_PATIENT_ID, interpret as the Master Prospect ID
  - Use VW_MART_JOURNEY_INTELLIGENCE for combined journey + engagement questions
  - Use DQ_REJECTION_LOG for funnel drop, rejection, and suppression questions
  - Use FACT_SFMC_ENGAGEMENT + DIM_SFMC_JOB for SFMC event questions
  - Always include a date filter when the user asks about a specific date or period
  - Cap result sets to 100 rows unless the user requests more
  - For funnel drops: query both PHI_PROSPECT_MASTER counts AND DQ_REJECTION_LOG counts, then compare
  - Use PATIENT_IDENTITY_XREF to bridge SUBSCRIBER_KEY (SFMC) to MASTER_PATIENT_ID (Prospect)

SFMC QUERY RULES — CRITICAL (violation causes all SFMC queries to return 0 rows):

  1. DATE FILTERING ON FACT_SFMC_ENGAGEMENT:
     - ALWAYS filter by: DATE(fe.EVENT_TIMESTAMP) BETWEEN 'YYYY-MM-DD' AND 'YYYY-MM-DD'
     - NEVER join to DIM_DATE via DATE_KEY for date filtering — the DATE_KEY surrogate key
       join is unreliable and consistently returns ZERO rows. This is a known data platform issue.
     - Correct pattern:
         FROM FIPSAR_DW.GOLD.FACT_SFMC_ENGAGEMENT fe
         LEFT JOIN FIPSAR_DW.GOLD.DIM_SFMC_JOB j ON fe.JOB_KEY = j.JOB_KEY
         WHERE DATE(fe.EVENT_TIMESTAMP) BETWEEN '2026-01-01' AND '2026-12-31'
     - Wrong pattern (causes 0 rows — NEVER USE):
         JOIN FIPSAR_DW.GOLD.DIM_DATE d ON fe.DATE_KEY = d.DATE_KEY
         WHERE d.FULL_DATE BETWEEN ...

  2. WHEN get_sfmc_engagement_stats RETURNS EMPTY / NO DATA:
     The tool already tries FACT_SFMC_ENGAGEMENT first, then falls back to raw tables automatically.
     If the tool returns "no data", use run_sql with the raw table UNION ALL pattern:

     WITH events AS (
         SELECT 'SENT' AS event_type, SUBSCRIBER_KEY, JOB_ID
           FROM FIPSAR_SFMC_EVENTS.RAW_EVENTS.RAW_SFMC_SENT
         UNION ALL
         SELECT 'OPEN',        SUBSCRIBER_KEY, JOB_ID FROM FIPSAR_SFMC_EVENTS.RAW_EVENTS.RAW_SFMC_OPENS
         UNION ALL
         SELECT 'CLICK',       SUBSCRIBER_KEY, JOB_ID FROM FIPSAR_SFMC_EVENTS.RAW_EVENTS.RAW_SFMC_CLICKS
         UNION ALL
         SELECT 'BOUNCE',      SUBSCRIBER_KEY, JOB_ID FROM FIPSAR_SFMC_EVENTS.RAW_EVENTS.RAW_SFMC_BOUNCES
         UNION ALL
         SELECT 'UNSUBSCRIBE', SUBSCRIBER_KEY, JOB_ID FROM FIPSAR_SFMC_EVENTS.RAW_EVENTS.RAW_SFMC_UNSUBSCRIBES
         UNION ALL
         SELECT 'SPAM',        SUBSCRIBER_KEY, JOB_ID FROM FIPSAR_SFMC_EVENTS.RAW_EVENTS.RAW_SFMC_SPAM
     )
     SELECT e.event_type,
            COALESCE(j.JOURNEY_TYPE, 'Unknown') AS journey,
            COALESCE(j.MAPPED_STAGE, 'Unknown') AS stage,
            COUNT(*) AS event_count,
            COUNT(DISTINCT e.SUBSCRIBER_KEY) AS unique_subscribers
     FROM events e
     LEFT JOIN FIPSAR_DW.GOLD.DIM_SFMC_JOB j ON e.JOB_ID = j.JOB_ID
     GROUP BY 1, 2, 3
     ORDER BY 1, 2, 3

  3. RAW SFMC TABLE COLUMNS (all tables share):
     - SUBSCRIBER_KEY  — identity key linking to PATIENT_IDENTITY_XREF
     - JOB_ID          — links to DIM_SFMC_JOB for journey/stage resolution
     RAW_SFMC_BOUNCES also has: BOUNCE_CATEGORY, BOUNCE_TYPE (Hard/Soft)
     RAW_SFMC_CLICKS also has: URL (clicked link)

  4. SUPPRESSION & FATAL COUNTS:
     Always include DQ_REJECTION_LOG with dual date filter for suppression data:
     WHERE UPPER(REJECTION_REASON) IN ('SUPPRESSED', 'FATAL_ERROR')
       AND (
         TRY_TO_DATE(TRY_PARSE_JSON(REJECTED_RECORD):FILE_DATE::STRING) BETWEEN 'start' AND 'end'
         OR CAST(REJECTED_AT AS DATE) BETWEEN 'start' AND 'end'
       )

  5. JOURNEY / STAGE RESOLUTION:
     DIM_SFMC_JOB columns: JOB_KEY, JOB_ID, JOURNEY_TYPE, MAPPED_STAGE, EMAIL_NAME, EMAIL_SUBJECT
     - JOURNEY_TYPE maps to: 'J01_Welcome', 'J02_Nurture', 'J03_Conversion', 'J04_ReEngagement'
     - MAPPED_STAGE = the specific stage name within the journey

  6. SFMC FULL PICTURE — when user asks for "all SFMC data" or "all events":
     Always provide ALL of: SENT, OPEN, CLICK, BOUNCE, UNSUBSCRIBE, SPAM counts per journey/stage
     PLUS suppressed/fatal from DQ_REJECTION_LOG.
     Never say "no data" without trying both FACT_SFMC_ENGAGEMENT and raw SFMC tables.
""".strip()

    # --- Data accuracy rules ---
    accuracy_rules = """
DATA ACCURACY — MANDATORY RULES (violating these is a critical error):

  1. NEVER state a number, count, or metric without first calling a tool to retrieve it.
     If the user asks a follow-up question about numbers already mentioned (e.g. "what is X?",
     "why is that count Y?"), you MUST call the tool again with the appropriate filters.
     Do NOT recall numbers from earlier in the conversation — data can differ by date range.

  2. REJECTION CATEGORY DISTINCTION — this is a hard rule:
     a. "Lead-to-Prospect conversion rejections" = records with reasons NULL_EMAIL, NO_CONSENT,
        NULL_FIRST_NAME, NULL_LAST_NAME, NULL_PHONE_NUMBER.
        These come from the intake/mastering pipeline. Always use rejection_category="intake".
     b. "SFMC suppression / send failures" = records with reasons SUPPRESSED, FATAL_ERROR.
        These are valid Prospects whose EMAIL SEND was blocked — they are NOT intake rejections.
        Always use rejection_category="sfmc" for these.
     c. NEVER include SUPPRESSED or FATAL_ERROR when answering questions about why leads
        failed to convert to Prospects. They happen at a completely different funnel stage.
     d. NEVER include NULL_EMAIL or NO_CONSENT when answering questions about SFMC send issues.

  3. When the user asks "top N reasons", call get_rejection_analysis with the correct
     rejection_category, then report only what the tool returned — no guessing or adjusting.

  4. If a count doesn't add up (e.g., leads − prospects ≠ rejection log count), explain
     the gap: some rejections may be logged under a different timestamp (REJECTED_AT)
     than the lead's FILE_DATE. Always trust arithmetic (leads − prospects) for invalid
     lead counts over the rejection log date filter.
""".strip()

    # --- Charting guidance ---
    charting_rules = """
CHARTING RULES — when to generate charts:

  1. ALWAYS generate a chart when the user says: "chart", "plot", "show me a graph",
     "visualise", "display visually", or asks for a "trend", "breakdown", or "distribution".

  2. For common patterns use the dedicated tools:
       chart_funnel            → funnel stages (Lead → Prospect → Sent → Opened → Clicked)
       chart_rejections        → rejection reason donut
       chart_engagement        → SFMC events by journey
       chart_conversion_segments → engagement segment + active/inactive donut
       chart_intake_trend      → lead/prospect volume over time

  3. For ANYTHING ELSE — use chart_smart:
     - Write the SQL yourself, pick chart_type ("bar", "line", "pie", "donut", "area", "funnel")
     - Examples: channel mix bar, state distribution bar, monthly rejection trend line,
       consent rate pie, age group distribution, channel vs conversion rate scatter.

  4. For quantitative follow-up questions, automatically add a chart alongside the table.
     E.g., if the user asks "what are the rejection counts?" — show the table AND call chart_rejections.

  5. chart_smart orientation="h" (horizontal bar) works best when labels are long text.
""".strip()

    # --- Output formatting rules ---
    formatting_rules = """
OUTPUT FORMATTING — always structure responses as follows:

  1. Start with a **bold headline summary** — one or two sentences stating the key finding.

  2. Use **## Section Headers** to separate: Summary, Conversion Details, Rejection Details,
     SFMC Events, AI Scores, etc. depending on what was asked.

  3. Present metrics as a **bullet list with bold labels**:
     - **Total Leads Intake:** 335
     - **Valid Prospects Converted:** 318
     - **Invalid Leads (Failed Mastering):** 17
     - **Conversion Rate:** 94.93%

  4. When showing a data table: always precede it with a one-line description of what it shows.

  5. After every data table, add a 1–2 sentence **insight or interpretation** explaining
     what the numbers mean in business terms.

  6. If the user asks a follow-up refining the date range or adding a filter, re-query and
     update ALL numbers — do not mix figures from different queries.

  7. Use clear section separation. Never dump a raw table without context around it.
""".strip()

    # --- Compose final prompt ---
    prompt = "\n\n".join([
        overview,
        terminology_section,
        naming_section,
        table_section,
        rules_section,
        funnel_section,
        journey_section,
        kpi_section,
        rel_section,
        lineage_section,
        answering_section,
        sql_instructions,
        accuracy_rules,
        charting_rules,
        formatting_rules,
    ])

    return prompt


# Pre-built so it is imported once
SYSTEM_PROMPT: str = build_system_prompt()

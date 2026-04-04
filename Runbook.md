# FIPSAR Prospect Journey Intelligence — Runbook

---

## Part A: What Was Built (Business + Technical Flow)

### Business Objective

FIPSAR receives marketing campaign leads from multiple channels (App, API, Form, Campaign).
Those leads are validated, mastered into Prospects, enrolled in Salesforce Marketing Cloud (SFMC) journeys,
and tracked through email engagement events.

The goal of this MVP is to give any analyst or business user a **conversational AI interface** that can:

- Answer funnel questions ("How many leads became Prospects in January 2026?")
- Diagnose drop-offs ("Why did we see fewer prospects on a specific date?")
- List and explain rejections ("Who got rejected and why? Show me the individual records.")
- Surface SFMC journey performance ("Which journey stage has the highest bounce rate?")
- Trace individual records ("What happened to email xyz@example.com?")
- Compute conversion and drop-off probabilities ("Which active prospects are at risk of dropping off?")
- Generate interactive charts for any data question ("Plot monthly intake trend for 2026")

All answers are **grounded in live Snowflake data** — no cached snapshots, no hardcoded numbers.

---

### Business Flow (End-to-End)

```
User Question (natural language)
        │
        ▼
Conversational AI (LangGraph ReAct Agent)
  — full semantic model context in system prompt —
  — strict Lead / Prospect / Invalid Lead lifecycle enforcement —
  — knows all FIPSAR tables, business rules, funnel stages, KPIs —
  — charting rules: auto-selects chart tool when visualization is requested —
        │
        ▼ (decides which tool(s) to call — may call multiple in sequence)
┌──────────────────────────────────────────────────────────────────────────────┐
│  Tool Layer — 17 read-only tools across 3 categories                         │
│                                                                              │
│  DATA QUERY TOOLS (1–11)                                                     │
│  1.  run_sql                    Custom SELECT — agent-generated SQL          │
│  2.  get_funnel_metrics         F01–F06 funnel counts for a date range       │
│  3.  get_rejection_analysis     DQ_REJECTION_LOG summary (counts by reason)  │
│  4.  get_sfmc_engagement_stats  Events by journey / stage / event type       │
│  5.  get_drop_analysis          Multi-signal drop diagnosis for a date       │
│  6.  trace_prospect             End-to-end record trace by email or ID       │
│  7.  get_ai_intelligence        AI table schema discovery + sample data      │
│  8.  get_prospect_conversion_analysis  Engagement-derived conversion scores  │
│  9.  get_pipeline_observability Pipeline run log + DQ signal counts          │
│  10. get_rejected_lead_details  Row-level rejected records with parsed fields│
│  11. get_prospect_details       Row-level valid mastered prospect records     │
│                                                                              │
│  CHART TOOLS (12–17)                                                         │
│  12. chart_smart                Generalised — any SQL + any chart type       │
│  13. chart_funnel               Funnel stages bar chart                      │
│  14. chart_rejections           Rejection reasons donut                      │
│  15. chart_engagement           SFMC events grouped bar by journey           │
│  16. chart_conversion_segments  Engagement segment + active/inactive donut   │
│  17. chart_intake_trend         Lead & prospect volume over time             │
└──────────────────────────────────────────────────────────────────────────────┘
        │
        ▼ (SQL executes against Snowflake — read-only)
Snowflake Data Platform
  FIPSAR_PHI_HUB     → Lead intake, mastered Prospects, identity bridge
  FIPSAR_DW          → Bronze / Silver / Gold warehouse, SFMC engagement facts
  FIPSAR_SFMC_EVENTS → Raw SFMC event landing tables
  FIPSAR_AUDIT       → Pipeline run log, DQ rejection log
  FIPSAR_AI          → AI feature tables, semantic scores
        │
        ├── Text results → markdown tables → LLM composes business-language response
        │
        └── Chart results → Plotly figures → chart_store → app.py renders st.plotly_chart()
                │
                ▼
        User sees answer + interactive chart (Streamlit UI)
```

---

### Semantic Model as the "Brain"

`SFMC_Prospects_Semmantic_Model.yaml` is the authoritative knowledge base.
At startup, `semantic_model.py` parses the YAML and compiles a system prompt that teaches the agent:

| YAML Section | What the Agent Learns |
|---|---|
| `terminology` | Lead ≠ Prospect ≠ Invalid Lead — strict lifecycle rules |
| `physical_data_model` | Every table, grain, business role, key columns across all 5 databases |
| `business_rules` | Mandatory fields, consent rule, rejection reasons, SFMC event types |
| `funnel_model` | F01–F08 funnel stages with source tables and metric examples |
| `journey_definition` | J01 Welcome, J02 Nurture, J03 Conversion, J04 Re-engagement with email mappings |
| `metrics` | Canonical KPI definitions (open rate, bounce rate, conversion rate, etc.) |
| `relationships` | All canonical joins between tables |
| `lineage_summary` | End-to-end data flow from intake to AI scores |
| `conversational_guidance` | Answering rules and refusal rules |

Additional runtime rules compiled into the prompt:

| Rule Block | Purpose |
|---|---|
| **Data Accuracy Rules** | Agent must call a tool for every number — never recall from context |
| **Rejection Category Distinction** | Intake rejections (NULL_EMAIL, NO_CONSENT) ≠ SFMC suppressions (SUPPRESSED, FATAL_ERROR) |
| **Charting Rules** | When to auto-generate charts vs. specific chart tools vs. chart_smart |
| **Output Formatting Rules** | Bold headlines, section headers, bullet metrics, insight after every table |

---

### Key Design Decisions and Fixes Applied

| Issue | Root Cause | Fix Applied |
|---|---|---|
| `create_react_agent` crash | LangGraph version used `state_modifier` not `prompt` | Changed to `state_modifier=SYSTEM_PROMPT` |
| Rejection count = 0 for date ranges | `REJECTED_AT` (pipeline time) ≠ `FILE_DATE` (lead time) | Invalid lead count now computed arithmetically (leads − prospects); rejection log filtered by FILE_DATE extracted from JSON |
| AI intelligence SQL error | Hardcoded column names that don't exist in actual tables | `get_ai_intelligence` now uses `INFORMATION_SCHEMA.COLUMNS` to discover real columns before querying |
| Conversion/drop-off returns no data | `FACT_SFMC_ENGAGEMENT` joined via broken `DIM_DATE` key | 3-path fallback: gold table (EVENT_TIMESTAMP) → raw SFMC tables → prospect master signals |
| SUPPRESSED counted as lead rejection | SFMC suppressions mixed with mastering rejections | `rejection_category="intake"/"sfmc"/"all"` parameter added to all rejection tools |
| Intake trend chart crashes | `DATE_TRUNC` on VARCHAR `FILE_DATE` column | All date columns wrapped in `TRY_TO_DATE()` via helper functions |
| Agent hallucinates counts | Recalled numbers from conversation context | System prompt rule: always re-query tools for any number in any follow-up |

---

## Part B: Complete File Reference

```
SFMC_Prospects_MVP01/
│
├── SFMC_Prospects_Semmantic_Model.yaml  ← Authoritative business knowledge base
├── .env                                 ← Credentials (never commit)
│
├── config.py                            ← Env loader (supports 'env' and '.env')
├── snowflake_connector.py               ← Read-only Snowflake query engine
├── semantic_model.py                    ← YAML → agent system prompt compiler
├── tools.py                             ← 17 LangChain tools (data + charts)
├── charts.py                            ← Plotly chart generators (6 functions)
├── chart_store.py                       ← Session-scoped chart queue
├── agent.py                             ← LangGraph ReAct agent + session memory
├── app.py                               ← Streamlit chat UI
│
├── voice_assistant.py                   ← Voice pipeline (Whisper + TTS)
├── email_sender.py                      ← HTML email composer + SMTP sender (FREL)
├── frel_agent.py                        ← FREL LangGraph agent (18 tools + email)
├── requirements.txt                     ← Python dependencies
├── Runbook.md                           ← This file
└── Demo_Book.md                         ← Demo scenarios and question bank
```

---

## Part C: Deployment

### Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.10+ |
| pip | latest |
| Snowflake account | Role with SELECT on all FIPSAR_* databases |
| OpenAI API key | GPT-4o access |

---

### Step 1 — Set Up Credentials

The project includes a file named `env`. Rename it to `.env`:

```bash
# Windows
copy env .env

# Mac / Linux
cp env .env
```

The `.env` file must contain:

```env
SNOWFLAKE_USER="your_user"
SNOWFLAKE_PASSWORD="your_password"
SNOWFLAKE_ACCOUNT="orgname-accountname"
SNOWFLAKE_WAREHOUSE="COMPUTE_WH"
SNOWFLAKE_ROLE="your_role"

OPENAI_API_KEY="sk-..."
OPENAI_MODEL=gpt-4o
AGENT_MAX_ITERATIONS=10
SEARCH_MAX_ROWS=50

# FREL Agent — email settings (required for the 📧 FREL Agent tab)
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USER=your-sender@gmail.com
EMAIL_SMTP_PASSWORD=your_gmail_app_password
EMAIL_FROM_NAME=FIPSAR Intelligence
EMAIL_FROM_ADDRESS=your-sender@gmail.com
EMAIL_TO=akilesh@fipsar.com
```

> For Gmail: enable 2-Factor Authentication, then generate an **App Password** at
> Google Account → Security → 2-Step Verification → App Passwords.
> Use the 16-character app password as `EMAIL_SMTP_PASSWORD` (not your Gmail password).
> For Office 365: set `EMAIL_SMTP_HOST=smtp.office365.com` and `EMAIL_SMTP_PORT=587`.

> `SNOWFLAKE_DATABASE` and `SNOWFLAKE_SCHEMA` are optional — all queries use fully-qualified
> 3-part names (`FIPSAR_DW.GOLD.DIM_PROSPECT`), so the default connection database is irrelevant.

---

### Step 2 — Install Dependencies

..\..\GenAI_venv\Scripts\activate    

```bash

..\..\GenAI_venv\Scripts\activate   
pip install -r ..\..\requirements.txt


```

Key packages installed: `langchain`, `langgraph`, `langchain-openai`, `snowflake-connector-python`,
`streamlit`, `plotly`, `pandas`, `pyyaml`, `tabulate`.

---

### Step 3 — Test Snowflake Connection

```python
from snowflake_connector import test_connection
print(test_connection())   # True = connected
```

Or via the Streamlit sidebar: **Test Snowflake Connection** button.

---

### Step 4 — Test the Agent (CLI smoke test)

```bash
python agent.py
```

Runs 3 built-in questions against live Snowflake data and prints answers.
Confirms both Snowflake and OpenAI are reachable before starting the UI.

---

### Step 5 — Launch the Streamlit UI

```bash
streamlit run app.py
```

Open `http://localhost:8501`. In the sidebar:
1. Click **Test Snowflake Connection** — verify green.
2. Type a question in the chat box, or pick from the sample questions panel.

---

### Architecture Diagram (Component View)

```
┌──────────────────────────────────────────────────────┐
│  Streamlit UI  (app.py)                               │
│  - Chat interface + session controls                  │
│  - Sample question panels (7 categories)              │
│  - st.plotly_chart() renders charts inline            │
└───────────────────┬──────────────────────────────────┘
                    │ chart_store.set_session()
                    │ chat(session_id, message)
                    │ chart_store.pop_all() → render
                    ▼
┌──────────────────────────────────────────────────────┐
│  LangGraph ReAct Agent  (agent.py)                    │
│  - state_modifier: compiled semantic model prompt     │
│  - LLM: GPT-4o, temperature=0                        │
│  - MemorySaver: per-session conversation history      │
└──────────┬───────────────────────────────────────────┘
           │ tool calls (up to AGENT_MAX_ITERATIONS per turn)
           ▼
┌──────────────────────────────────────────────────────┐
│  tools.py — 17 read-only LangChain tools              │
│  Data tools  → execute_query_as_string() → str        │
│  Chart tools → charts.py → chart_store.push(fig)      │
└──────────┬───────────────┬───────────────────────────┘
           │               │
           ▼               ▼
┌──────────────────┐  ┌──────────────────────────────┐
│ snowflake_       │  │ charts.py                     │
│ connector.py     │  │ - 6 chart generator functions │
│ - read-only guard│  │ - TRY_TO_DATE safe date ops   │
│ - pandas → str   │  │ - chart_store.push(fig)       │
└────────┬─────────┘  └──────────────────────────────┘
         │ TLS/JDBC
         ▼
┌──────────────────────────────────────────────────────┐
│  Snowflake                                            │
│  FIPSAR_PHI_HUB · FIPSAR_DW · FIPSAR_SFMC_EVENTS    │
│  FIPSAR_AUDIT · FIPSAR_AI                            │
└──────────────────────────────────────────────────────┘

Supporting modules:
  config.py       — env loader (auto-finds 'env' or '.env')
  semantic_model.py — YAML parser + system prompt builder
  chart_store.py  — session-scoped Plotly figure queue
```

---

### Configuration Reference

| Variable | Purpose | Default |
|---|---|---|
| `SNOWFLAKE_ACCOUNT` | Account identifier (`orgname-accountname`) | required |
| `SNOWFLAKE_USER` | Username | required |
| `SNOWFLAKE_PASSWORD` | Password | required |
| `SNOWFLAKE_WAREHOUSE` | Compute warehouse | `COMPUTE_WH` |
| `SNOWFLAKE_DATABASE` | Default DB for connection (not used in queries) | `FIPSAR_DW` |
| `SNOWFLAKE_SCHEMA` | Default schema for connection (not used in queries) | `GOLD` |
| `SNOWFLAKE_ROLE` | Role with SELECT on all FIPSAR databases | required |
| `OPENAI_API_KEY` | OpenAI API key | required |
| `OPENAI_MODEL` | Model name | `gpt-4o` |
| `AGENT_MAX_ITERATIONS` | Max tool-calling rounds per agent turn | `10` |
| `SEARCH_MAX_ROWS` | Max rows returned per tool query | `50` |

---

### Troubleshooting

| Symptom | Fix |
|---|---|
| `KeyError: SNOWFLAKE_ACCOUNT` | Rename `env` → `.env` in the project folder |
| `OperationalError: Failed to connect` | Verify account format: `orgname-accountname` |
| `Role X does not exist or not authorized` | Update `SNOWFLAKE_ROLE` in `.env` to a valid role |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |
| `AuthenticationError: OpenAI` | Verify `OPENAI_API_KEY` in `.env` |
| `429 Too Many Requests (OpenAI)` | Rate limit — LangChain auto-retries; wait or upgrade API tier |
| `st.audio_input` not found | Upgrade Streamlit: `pip install streamlit>=1.37.0` |
| FREL: email not sent | Add `EMAIL_SMTP_USER` and `EMAIL_SMTP_PASSWORD` to `.env`; sidebar shows config status |
| FREL: Gmail auth error | Use a Gmail **App Password** (16-char), not your account password |
| FREL: charts not in email | Run `pip install kaleido>=0.2.1`; kaleido converts Plotly → PNG for embedding |
| Voice tab: transcription empty | Check microphone permissions in browser; ensure WAV format; verify OpenAI API key |
| Voice tab: TTS fails with model error | `gpt-4o-mini-tts` auto-falls back to `tts-1` — check OpenAI account tier |
| Charts not showing | Ensure `plotly>=5.20.0` is installed; verify `chart_store.set_session()` is called before `chat()` |
| Chart crashes with date error | `FILE_DATE` may be VARCHAR; the `TRY_TO_DATE()` wrapper in `charts.py` handles this |
| Agent returns 0 rejection rows for a date | Pipeline processes asynchronously; agent now uses `FILE_DATE` from REJECTED_RECORD JSON |
| `FACT_SFMC_ENGAGEMENT` returns 0 rows | Table may be empty in your environment; `get_prospect_conversion_analysis` has 3-path fallback |

---

### Security Notes

- All Snowflake queries are **read-only**. The connector blocks INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE, MERGE, REPLACE.
- `.env` is never committed to version control.
- OpenAI API calls transmit only aggregated SQL result rows — not raw PHI. Individual trace queries do send names/emails; scope the Snowflake role appropriately.
- Recommended role: custom role with `GRANT SELECT ON ALL TABLES IN DATABASE FIPSAR_*` only.

---

*FIPSAR Prospect Journey Intelligence MVP — LangChain · LangGraph · Snowflake · Streamlit · Plotly*

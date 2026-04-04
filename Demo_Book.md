# FIPSAR Prospect Journey Intelligence — Demo Book

> **Purpose:** Complete scenario and question bank for live demos, UAT sessions, and stakeholder walkthroughs.
> Each section lists ready-to-use questions with a brief description of the expected response.

---

## How to Use This Book

1. Launch the app: `streamlit run app.py`
2. Verify the **green connection indicator** in the sidebar (Test Snowflake Connection).
3. Pick questions from any section below and type or paste them into the chat.
4. Questions marked **[CHART]** will auto-generate an interactive Plotly chart alongside the text answer.
5. Questions marked **[MULTI-TURN]** are designed to be asked in sequence to demonstrate conversation memory.

---

## Section 1 — Funnel Overview & Conversion Metrics

> Demonstrates: `get_funnel_metrics`, arithmetic invalid-lead count, funnel stage definitions

### 1.1 Full-Period Funnel Summary

```
How many leads came in during January 2026 and how many became valid prospects?
```
*Expected: Lead intake count, valid prospect count, invalid lead count, and conversion rate — all from live Snowflake data. Agent will not guess or recall from context.*

---

```
Give me the complete funnel breakdown for January 2026.
```
*Expected: F01 (Intake) → F02 (Valid Prospects) → F03 (Mastered) → F04 (SFMC Enrolled) stage counts with drop-off between each stage.*

---

```
What was the lead-to-prospect conversion rate in January 2026?
```
*Expected: Percentage computed as (valid prospects / total leads) × 100 with numerator and denominator shown.*

---

### 1.2 Date Range Comparisons

```
Compare funnel metrics for January 2026 vs February 2026.
```
*Expected: Side-by-side table or two result blocks showing intake, prospects, and conversion rates for each month.*

---

```
What is the total intake for the first quarter of 2026?
```
*Expected: Lead and prospect counts across January–March 2026.*

---

```
Show me daily intake volume for the week of January 13–17, 2026.
```
*Expected: Day-by-day breakdown — useful for spotting pipeline gaps or volume spikes.*

---

### 1.3 Chart Requests — Funnel [CHART]

```
Show me a funnel chart for January 2026.
```
*Expected: Interactive Plotly funnel chart with stages Lead → Prospect → Sent → Opened → Clicked.*

---

```
Plot the intake trend for all of 2026.
```
*Expected: Line chart with monthly lead intake and prospect count, rejection gap shaded.*

---

```
Chart the monthly intake trend for January through March 2026.
```
*Expected: Line chart over 3-month window.*

---

## Section 2 — Rejection & Data Quality Analysis

> Demonstrates: `get_rejection_analysis`, `get_rejected_lead_details`, intake vs. SFMC category distinction

### 2.1 Aggregate Rejection Counts

```
Why did some leads fail to convert to prospects in January 2026?
```
*Expected: Rejection reasons from the intake/mastering pipeline (NULL_EMAIL, NO_CONSENT, NULL_FIRST_NAME, etc.) with counts per reason. Agent will use rejection_category="intake" — SUPPRESSED and FATAL_ERROR will NOT appear here.*

---

```
What are the top rejection reasons for January 2026?
```
*Expected: Ranked list of intake rejection reasons with counts. Agent re-queries even if it saw this data earlier in the session.*

---

```
How many leads were rejected due to missing email addresses in January 2026?
```
*Expected: Count of NULL_EMAIL rejections specifically, from DQ_REJECTION_LOG filtered by FILE_DATE.*

---

```
How many leads failed consent validation in January 2026?
```
*Expected: Count of NO_CONSENT rejections.*

---

### 2.2 Row-Level Rejected Records

```
Show me the individual records that were rejected in January 2026.
```
*Expected: Table with REJECTION_ID, EMAIL (masked or partial), REJECTION_REASON, FILE_DATE, and parsed fields from the REJECTED_RECORD JSON. Up to 50 rows.*

---

```
List all leads rejected for NULL_EMAIL in January 2026 — show me the individual records.
```
*Expected: Filtered row-level view of NULL_EMAIL rejections.*

---

```
Who got rejected due to missing consent in January 2026? Show individual records.
```
*Expected: Row-level detail for NO_CONSENT rejections.*

---

### 2.3 SFMC Suppression vs. Intake Rejection (Key Distinction)

```
How many valid prospects were suppressed by SFMC in January 2026?
```
*Expected: SUPPRESSED and FATAL_ERROR counts from DQ_REJECTION_LOG using rejection_category="sfmc". Agent clarifies these are valid Prospects whose email SEND was blocked — not failed lead conversions.*

---

```
What is the difference between a rejected lead and a suppressed prospect?
```
*Expected: Clear business explanation: rejected leads failed intake mastering (never became Prospects); suppressed prospects are valid Prospects blocked at the SFMC email-send stage — completely different funnel stages.*

---

```
Show me all SFMC send failures — suppressed or fatal error — for January 2026.
```
*Expected: Row-level SFMC suppression records with reason, email, and date.*

---

### 2.4 Chart Requests — Rejections [CHART]

```
Show me a chart of rejection reasons for January 2026.
```
*Expected: Donut chart with each intake rejection reason coloured distinctly — counts and percentages shown.*

---

```
Plot the rejection breakdown as a donut chart.
```
*Expected: Calls chart_rejections with intake category.*

---

## Section 3 — SFMC Journey Performance & Engagement

> Demonstrates: `get_sfmc_engagement_stats`, journey definitions J01–J04, event type breakdown

### 3.1 Journey-Level Metrics

```
How is the J01 Welcome Journey performing? Show open and click rates.
```
*Expected: Sent, opened, clicked, bounced counts for J01. Open rate = (opened/sent)×100, click rate = (clicked/sent)×100.*

---

```
Which SFMC journey has the highest open rate?
```
*Expected: Comparison across J01 Welcome, J02 Nurture, J03 Conversion, J04 Re-engagement.*

---

```
Which journey stage has the highest bounce rate?
```
*Expected: Bounce counts and rates by journey, ranked highest to lowest.*

---

```
How many emails were sent across all journeys in January 2026?
```
*Expected: Total sent count across all journey codes.*

---

```
What is the unsubscribe rate for the J02 Nurture Journey?
```
*Expected: Unsubscribes / sent × 100 for J02 specifically.*

---

### 3.2 Stage-Level Engagement

```
Show me engagement stats broken down by event type for each journey.
```
*Expected: Table with JOURNEY_CODE, EVENT_TYPE (Sent/Open/Click/Bounce/Unsub), and counts.*

---

```
How many prospects clicked at least one email in J03 Conversion Journey?
```
*Expected: Click count for J03.*

---

```
How many prospects bounced in the Welcome journey?
```
*Expected: Bounce count for J01.*

---

### 3.3 Chart Requests — Engagement [CHART]

```
Show me a chart of SFMC engagement by journey.
```
*Expected: Grouped bar chart — X axis = journey code, grouped bars = event types (Sent/Open/Click/Bounce/Unsub).*

---

```
Plot email engagement for all journeys.
```
*Expected: Same grouped bar chart.*

---

## Section 4 — Drop-Off Diagnosis

> Demonstrates: `get_drop_analysis`, multi-signal diagnosis, date-specific investigation

### 4.1 Single-Date Drop Investigation

```
Why did we see fewer prospects on January 15, 2026?
```
*Expected: Multi-signal analysis — lead intake count, rejection count, pipeline run status for that date. Agent identifies whether the drop was due to low intake, high rejections, or a pipeline issue.*

---

```
Was there a data quality issue on January 8, 2026?
```
*Expected: DQ signal count and rejection reasons for that specific date.*

---

```
Investigate the drop on January 20, 2026.
```
*Expected: Full drop analysis: intake volume, rejection breakdown, pipeline status, SFMC send volume.*

---

### 4.2 Trend-Based Drop Questions

```
On which dates in January 2026 did we see the largest drop from leads to prospects?
```
*Expected: Agent queries daily funnel counts and identifies dates where invalid lead percentage was highest.*

---

```
Were there any days in January 2026 with zero prospect intake?
```
*Expected: Dates where prospect count was 0 or near-zero, flagged as pipeline or data gaps.*

---

## Section 5 — Individual Prospect Tracing

> Demonstrates: `trace_prospect`, end-to-end record trace from intake through SFMC events

### 5.1 Trace by Email

```
What happened to the lead with email test@example.com?
```
*Expected: End-to-end trace — was the lead found in STG_PROSPECT_INTAKE? Did it pass or get rejected? Is it in PHI_PROSPECT_MASTER? Was it enrolled in SFMC? Which emails did it receive and what were the engagement events?*

---

```
Trace the prospect journey for john.doe@fipsar.com.
```
*Expected: Full lifecycle trace from intake → mastering → SFMC enrollment → email events.*

---

### 5.2 Trace by Prospect ID

```
Can you trace prospect ID 1001 and show me their full journey?
```
*Expected: Trace using MASTER_PATIENT_ID = 1001 — intake record, mastered record, SFMC events.*

---

```
What emails did prospect 2045 receive and did they engage with any of them?
```
*Expected: SFMC event table for that prospect — sent emails, opens, clicks.*

---

### 5.3 Valid Prospect Details

```
Show me all valid prospects who came in on January 10, 2026.
```
*Expected: Row-level PHI_PROSPECT_MASTER records for that FILE_DATE — name (if not PHI-sensitive), email, intake channel, and consent flag.*

---

```
List all prospects enrolled in the J01 Welcome Journey.
```
*Expected: Prospect records linked to J01 enrollment.*

---

## Section 6 — Conversion & Drop-Off Probability (AI Scores)

> Demonstrates: `get_prospect_conversion_analysis`, engagement-derived segmentation, 3-path fallback

### 6.1 Engagement Segments

```
Which active prospects are at risk of dropping off?
```
*Expected: Prospects with low or zero engagement signals (no opens, no clicks) despite being enrolled — scored as "at risk". Agent uses engagement activity from SFMC events.*

---

```
Show me the conversion probability breakdown for all prospects.
```
*Expected: Segment counts — High Engagement (clicked), Medium Engagement (opened not clicked), Low Engagement (sent not opened), No Activity (enrolled, zero events). Active vs. inactive split.*

---

```
How many prospects have high conversion probability?
```
*Expected: Count of prospects in the "High Engagement" segment.*

---

```
Which prospects have never opened any email?
```
*Expected: Prospects who received at least one Sent event but have zero Open events — re-engagement candidates.*

---

### 6.2 Chart Requests — Conversion Segments [CHART]

```
Show me a chart of engagement segments and drop-off risk.
```
*Expected: Dual donut chart — Left: High/Medium/Low/No Activity segments. Right: Active vs. Inactive prospects.*

---

```
Visualise conversion probability distribution.
```
*Expected: Same dual donut via chart_conversion_segments.*

---

## Section 7 — AI Intelligence & Scoring Tables

> Demonstrates: `get_ai_intelligence`, INFORMATION_SCHEMA column discovery, FIPSAR_AI database

### 7.1 AI Table Exploration

```
What AI tables are available in the FIPSAR_AI database?
```
*Expected: Table list with schema discovery — column names and sample rows from whatever AI tables exist in the FIPSAR_AI database.*

---

```
Show me the AI feature scores for prospects.
```
*Expected: INFORMATION_SCHEMA-discovered columns and sample data from FIPSAR_AI tables.*

---

```
What engagement score metrics does the AI compute for each prospect?
```
*Expected: Column-level breakdown of whatever scoring/feature columns exist in FIPSAR_AI — no hardcoded assumptions.*

---

## Section 8 — Pipeline Observability

> Demonstrates: `get_pipeline_observability`, pipeline run log, DQ signal counts

### 8.1 Pipeline Health

```
What is the current status of the data pipeline?
```
*Expected: Latest pipeline run log — RUN_DATE, STATUS, records processed, DQ signal counts.*

---

```
Were there any pipeline failures in January 2026?
```
*Expected: Pipeline run log filtered to January — any FAILED or WARNING status rows flagged.*

---

```
How many DQ signals were raised in the pipeline for January 2026?
```
*Expected: DQ rejection counts by signal type from the pipeline observability table.*

---

```
Show me the pipeline run log for the last 7 days.
```
*Expected: Recent run log rows with status and record counts.*

---

## Section 9 — Custom SQL & Ad-Hoc Analysis

> Demonstrates: `run_sql` — agent writes and executes any SELECT

### 9.1 Custom Queries

```
Run a query to show me the top 5 intake channels by lead volume in January 2026.
```
*Expected: Agent generates a SQL GROUP BY on the intake channel column, orders by count DESC, limits to 5.*

---

```
What is the distribution of prospects by state for January 2026?
```
*Expected: COUNT by state field from PHI_PROSPECT_MASTER.*

---

```
How many unique email addresses are in the prospect master table?
```
*Expected: COUNT(DISTINCT EMAIL_ADDRESS) from PHI_PROSPECT_MASTER.*

---

```
Show me prospects who consented via the App channel in January 2026.
```
*Expected: Filtered query on intake channel = 'App' and consent flag = true.*

---

## Section 10 — Chart Gallery (Ad-Hoc / chart_smart) [CHART]

> Demonstrates: `chart_smart` — generalized chart engine for any SQL + chart type

### 10.1 Distribution Charts

```
Show me a bar chart of leads by intake channel for January 2026.
```
*Expected: Horizontal or vertical bar chart — X = channel name, Y = lead count.*

---

```
Plot the distribution of rejection reasons as a bar chart for January 2026.
```
*Expected: Bar chart via chart_smart with rejection reasons on X axis and counts on Y.*

---

```
Chart the state distribution of prospects in January 2026.
```
*Expected: Horizontal bar chart — states on Y axis, count on X.*

---

### 10.2 Trend Charts

```
Plot the daily lead intake for January 2026 as a line chart.
```
*Expected: Line chart with dates on X axis and daily lead count on Y.*

---

```
Show me a trend line of rejection counts by day for January 2026.
```
*Expected: Line chart with daily rejection count from DQ_REJECTION_LOG.*

---

### 10.3 Proportion Charts

```
Show me a pie chart of lead sources (intake channels) for January 2026.
```
*Expected: Pie/donut chart — each slice = one channel.*

---

```
Plot consent rate by intake channel as a bar chart.
```
*Expected: Bar chart — X = channel, Y = % of leads with consent = true.*

---

## Section 11 — Multi-Turn Conversations [MULTI-TURN]

> Demonstrates: LangGraph MemorySaver — the agent remembers all prior turns in the session

### 11.1 Funnel Deep-Dive Sequence

Ask these in order without resetting the session:

```
Q1: How many leads came in during January 2026?
```
```
Q2: How many of those became valid prospects?
```
```
Q3: What happened to the ones that didn't become prospects?
```
```
Q4: Show me the individual records for the leads that were rejected.
```
```
Q5: Plot those rejection reasons as a donut chart.
```

*Expected: Agent maintains context across all 5 turns. Q2 correctly uses January 2026 from Q1. Q3 explains rejection reasons. Q4 shows row-level detail. Q5 generates a chart.*

---

### 11.2 Journey Investigation Sequence

```
Q1: Which SFMC journey has the lowest open rate?
```
```
Q2: How many prospects are enrolled in that journey?
```
```
Q3: Show me the prospects in that journey who have never opened an email.
```
```
Q4: Are any of those prospects at risk of dropping off?
```

*Expected: Agent correctly carries forward the journey code identified in Q1 through subsequent turns.*

---

### 11.3 Prospect Trace + Follow-Up

```
Q1: Trace the prospect with email [any email from your data].
```
```
Q2: Which SFMC journey are they enrolled in?
```
```
Q3: Have they opened any emails?
```
```
Q4: What is their engagement segment?
```

*Expected: Agent recalls the prospect record from Q1 and uses it as context for Q2–Q4 without re-tracing.*

---

### 11.4 Date Filter Refinement

```
Q1: What is the funnel conversion rate for January 2026?
```
```
Q2: What about for just the first two weeks — January 1–15?
```
```
Q3: And for January 16–31?
```
```
Q4: Which half of January had a better conversion rate?
```

*Expected: Agent re-queries for each date window (never recalls from context). Q4 compares the two figures retrieved in Q2 and Q3.*

---

## Section 12 — Edge Cases & Robustness

> Demonstrates: graceful fallback, refusal rules, clarifying responses

### 12.1 Questions the Agent Handles Gracefully

```
Why did conversion drop so much on January 15?
```
*Expected: `get_drop_analysis` for that date — may return low intake, high rejections, or pipeline gap; agent explains the signal mix.*

---

```
Are there any anomalies in the pipeline this month?
```
*Expected: Pipeline observability query — flags any failed runs, high DQ rejection counts, or zero-record days.*

---

```
How many prospects are in the FIPSAR system in total?
```
*Expected: COUNT(*) from PHI_PROSPECT_MASTER — total, no date filter.*

---

### 12.2 Refusal Scenarios

```
Delete all records from the rejection log.
```
*Expected: Agent refuses — write operations are blocked at the connector level and the agent is instructed to refuse all non-SELECT requests.*

---

```
Update the consent flag for prospect 1001.
```
*Expected: Agent explains it is a read-only analytics assistant and cannot modify data.*

---

```
What will the lead intake be next month?
```
*Expected: Agent explains it cannot forecast — it can only answer questions grounded in actual Snowflake data.*

---

## Quick Reference — Sample Question Cheat Sheet

| Category | Quick Question |
|---|---|
| Funnel | "How many leads became prospects in January 2026?" |
| Rejection | "Top rejection reasons for January 2026?" |
| SFMC Journey | "Which journey has the highest open rate?" |
| Drop Analysis | "Why did intake drop on January 15?" |
| Prospect Trace | "Trace prospect ID 1001" |
| Conversion AI | "Which prospects are at risk of dropping off?" |
| Pipeline | "Were there pipeline failures in January 2026?" |
| Chart | "Plot monthly intake trend for 2026" |
| Chart | "Show rejection reasons as a donut chart" |
| Chart | "Bar chart of leads by intake channel" |
| Custom SQL | "Top 5 intake channels by lead volume" |
| Multi-turn | "How many leads in Jan 2026?" → "And how many became prospects?" |

---

*FIPSAR Prospect Journey Intelligence MVP — Demo Book*
*LangChain · LangGraph · Snowflake · Streamlit · Plotly*

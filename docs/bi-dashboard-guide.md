# Building the dashboard in Tableau Public

Synthetic data, fictional company. This page names a real product because it is a build
guide for it. The data is generated; nothing in it belongs to a real customer.

In the real job the dashboard reads the gold tables in the warehouse. Tableau Public is
free but cannot reach a local warehouse, and everything published to it is public. So
the tables are written to files first. The definitions stay in dbt, where they are
tested; the dashboard only draws.

**Before you publish:** the workbook and its data become public. That is fine here
because the data is synthetic. Put "Synthetic data, fictional company" in the dashboard
title so nobody mistakes it for real results.

## 1. Write the extracts

```
uv run python run.py experiments
uv run python run.py extracts
```

This writes eight files to `exports/bi/`:

| File | One row per | Used for |
|---|---|---|
| `accounts.csv` | Account, today | Health, scores, filters |
| `health_daily.csv` | Day, coverage tier, health band, lifecycle stage | Trends |
| `signals_today.csv` | Account and signal firing today | What needs attention |
| `play_outcomes.csv` | Enrolment (treatment and holdout) | Cohorts, drill-down |
| `play_results.csv` | Play | Lift with its interval, verdict |
| `handoffs.csv` | Task handed to a person | Queues, SLA |
| `agent_conversations.csv` | Agent conversation | Handoff rate and reasons |
| `data_quality.csv` | Data-quality measure | What the pipeline caught |

## 2. Connect

1. Open Tableau Public (the free desktop app) and choose **Connect > Text file**.
2. Pick `accounts.csv`. Drag `signals_today.csv`, `play_outcomes.csv`, `handoffs.csv` and
   `agent_conversations.csv` onto the canvas and relate each to `accounts` on **account_id**.
3. Add `health_daily.csv`, `play_results.csv` and `data_quality.csv` as separate data
   sources (**Data > New data source**). They are already aggregated and join to nothing.

## 3. Five sheets

**Health by coverage tier** (source: accounts). Columns: `coverage_tier`. Rows:
`CNT(account_id)`. Colour: `health_band`. Set the colours to green, amber and red, and
sort the bands in that order. Add `coverage_tier` and `lifecycle_stage` as filters.

**Health over time** (source: health_daily). Columns: `snapshot_date` (exact date,
continuous). Rows: `SUM(accounts)`. Colour: `health_band`. Area chart, stacked. Filter:
`coverage_tier = uncovered`. This shows the pilot segment moving.

**Signals firing today** (source: accounts with signals_today). Rows: `signal_id`.
Columns: `CNT(account_id)`. Sort descending. Filter: `coverage_tier`.

**Play results** (source: play_results). Rows: `play_name`. Columns: `lift` as a circle
mark. Add `ci_low` and `ci_high` as a Gantt bar behind it (Columns: `ci_low`; Size: a
calculated field `[ci_high] - [ci_low]`). Add a constant reference line at 0. Tooltip:
`verdict`, `n_treatment`, `n_holdout`, `p_value`. A bar that crosses zero is not proven.

**Handoffs** (source: accounts with handoffs). Rows: `queue`. Columns: `CNT(cta_id)`.
Colour: a calculated field `IF [status] = "resolved" THEN "closed" ELSE "open" END`.
Second view on the same sheet or a new one: `reason_code` by count.

## 4. The dashboard

One dashboard, 1200 by 800. Title: "Digital Success pilot. Synthetic data, fictional
company." Top row: three numbers (accounts in the pilot, ARR in the pilot, tasks open),
each a sheet with a single `SUM` or `CNT` as text. Middle: health by tier, health over
time. Bottom: signals, play results, handoffs. Make `coverage_tier` a filter that applies
to all sheets using the accounts source.

## 5. Publish

**File > Save to Tableau Public**. Sign in when asked. In the workbook's settings online,
turn off "Allow access" to the underlying data if you do not want the files downloadable.
Put the link in the README's tool-mapping section.

## What to say about it

"In this demo the app is Streamlit because it also has to write: a person resolves a task
in it. A dashboard only reads. The interface between the two worlds is the gold tables:
the same eight tables feed the app and this workbook, and no metric is defined in the
dashboard."
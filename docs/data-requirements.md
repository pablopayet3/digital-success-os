# Data requirements: six data areas, written backwards from the plays

Synthetic data, fictional company. This is the document handed to Data Engineering and
Revenue Operations. It starts from what the plays need to decide, and works back to the
fields. Nothing is asked for "because it might be useful".

**The join key for everything is `account_id`.** Contacts also carry `contact_id`, and a
`product_user_id` that ties a contact to their activity in the product.

This document says what is needed and why. What was built, column by column, is in
`docs/data-dictionary.md`.

In the last column, **Exists** means the source system already has it; **Build** means
it is requested from the team named.

## What each play needs to decide

| Play | Needs to know | Data areas |
|---|---|---|
| Onboarding rescue | Which setup steps are done; how old the account is; who the admin is and whether we may email them | Product, Account, Contact, Lifecycle |
| Usage recovery | Active users now against the previous 30 days; whether sentiment is already negative | Product, Health, Engagement |
| Detractor save | The NPS score and comment; open tickets; who answered | Engagement, Health, Contact |
| Find the admin | Whether any admin has a working address and consent | Contact |
| Edition upgrade | Usage against the limits of the edition | Product, Account |
| Seat expansion | Seats assigned against licensed, and the trend; renewal date; open opportunities | Account, Product, Lifecycle |
| Cross-product (Docs) | Document-style boards created; whether the account owns Docs | Product, Account |
| Every play | Coverage tier, lifecycle stage, renewal in negotiation, consent, recent touches | Account, Lifecycle, Contact, Engagement |

## 1. Account

**Purpose:** who the customer is commercially, and who covers them. **Grain:** one row
per account. **Table:** `gold.dim_account`. **Owner:** Revenue Operations.
**Freshness:** daily.

| Field | Definition | Source | Status |
|---|---|---|---|
| `account_id` | The one id that joins everything | CRM | Exists |
| `segment` | smb, mid or enterprise, by seats | CRM | Exists |
| `coverage_tier` | high_touch, pooled or uncovered: who looks after the account | CRM | **Build (RevOps):** today coverage is implied by the CSM field; it must be an explicit field |
| `edition`, `products` | What they bought | CRM | Exists |
| `seats_licensed`, `arr` | Size of the contract | CRM | Exists |
| `contract_start`, `renewal_date` | When it started and when it renews | CRM | Exists |
| `account_owner`, `csm` | The seller and, if any, the success manager | CRM | Exists |
| `status`, `churned_at` | Active or churned, and when | CRM | Exists |
| `renewal_in_negotiation` | An open renewal opportunity is in negotiation | CRM opportunities | **Build (DE):** derived |

Quality rules: `account_id` unique and never null; `coverage_tier` one of three values;
`seats_licensed` above zero; `renewal_date` after `contract_start`.

## 2. Contact

**Purpose:** who we may talk to, and about what. **Grain:** one row per contact.
**Table:** `gold.dim_contact`. **Owner:** Revenue Operations; consent is accountable to
Privacy. **Freshness:** daily, and same-day for opt-outs.

| Field | Definition | Source | Status |
|---|---|---|---|
| `contact_id`, `account_id` | Identity and the account they belong to | CRM | Exists |
| `email`, `email_valid` | Address, and whether it is usable (format, no hard bounce) | CRM, email platform | **Build (DE):** validity derived from bounces |
| `role` | admin, member or billing | CRM | Exists, incomplete |
| `persona` | Standardised job tag (admin, champion, executive, user) | CRM | **Build (RevOps):** free text today, 446 values normalised in this demo |
| `consent_status` | opted_in, opted_out or unknown | CRM, email platform, mailbox | **Build (RevOps, Privacy):** one field, one owner |
| `product_user_id` | The contact's user id in the product | Product | **Build (DE):** join on email |
| `can_email` | Valid address and not opted out | Derived | Build (DE) |
| `is_valid_admin` | An admin we may email | Derived | Build (DE) |

Quality rules: one row per email per account (57 duplicates removed in this demo);
every contact belongs to a real account; `consent_status` never null.

## 3. Product (telemetry)

**Purpose:** what the account does in the product. **Grain:** one row per event; rolled
up to one row per account per day. **Tables:** `silver.stg_events`,
`gold.fct_usage_daily`. **Owner:** Data Engineering, with Product Engineering as the
source. **Freshness:** events within 36 hours (warn), 96 hours (error).

| Field | Definition | Source | Status |
|---|---|---|---|
| `event_id` | Unique id of the event | Product | Exists |
| `occurred_at` | When it happened (the client's clock) | Product | Exists |
| `account_id`, `user_id` | Who | Product | **Build (Product Eng):** about 1% of events arrive without an account id and are rejected |
| `event_name` | One of an agreed list (user_active, board_created, doc_published, automation_rule_created, integration_connected, assist_invoked, ...) | Product | **Build:** an agreed event dictionary; unknown names are rejected |
| `properties` | Details of the event | Product | Exists |
| Daily roll-up: active users, MAU, boards, document-style boards, docs, rules, integrations, Assist credits | Counts per account per day | Derived | Build (DE) |
| Setup steps: first board, five users, integration, single sign-on | The four prerequisites | Derived from events | Build (DE) |

Quality rules: schema validated at ingest, rejects kept with a reason; duplicates removed
on `event_id`; events dated in the future removed; late events (up to a few days) kept.

## 4. Engagement

**Purpose:** how the account responds to us. **Grain:** one row per email sent, per reply,
per NPS response, per ticket. **Tables:** `silver.stg_email_engagement`,
`silver.stg_mailbox`, `silver.stg_nps`, `silver.stg_tickets`. **Owner:** CS Operations
(email, mailbox, NPS), Support Operations (tickets). **Freshness:** daily.

| Field | Definition | Source | Status |
|---|---|---|---|
| Email sends: campaign, contact, sent, delivered, bounced, opened, clicked, unsubscribed | One row per send | Email platform | Exists |
| Mailbox replies: sender, the email it answers, subject, body | Replies to journey emails in the shared mailbox | Shared mailbox | **Build (CSOps, DE):** nobody exports this today |
| Reply intent, sentiment, confidence | What the reply wants | Mailbox triage agent | Build (this programme) |
| NPS: score, comment, contact, date | One row per response | Survey tool | Exists |
| Tickets: priority, category, subject, body, status, dates | One row per ticket | Support tool | Exists |
| Touches: every email, in-app prompt and agent conversation a play delivered | For the frequency cap and for analysis | Operational store | Build (this programme) |

Quality rules: every send and reply resolves to a contact and an account; a reply is
linked to the email it answers.

## 5. Lifecycle

**Purpose:** where the account is in its life, so the right play applies.
**Grain:** one row per account per day. **Table:** `gold.account_daily`
(`lifecycle_stage`). **Owner:** Digital Success Portfolio Lead. **Freshness:** daily.

| Field | Definition | Source | Status |
|---|---|---|---|
| `account_age_days` | Days since the contract started | Account | Build (DE) |
| `days_to_renewal` | Days until the renewal date | Account | Build (DE) |
| `prerequisite_closure_pct` | Share of the four setup steps done | Product | Build (DE) |
| `lifecycle_stage` | onboarding, adopting, mature, expansion, renewal or at_risk. One stage per account per day, by the precedence in `docs/metrics.md` | Derived | **Build:** the rules are agreed in `docs/metrics.md`; no system holds them today |

Quality rules: exactly one stage per account per day; only the six agreed values.

## 6. Health

**Purpose:** one explainable number per account, and what drives it. **Grain:** one row
per account per day. **Table:** `gold.account_daily`. **Owner:** Digital Success
Portfolio Lead (definition), Data Science (model scores). **Freshness:** daily.

| Field | Definition | Source | Status |
|---|---|---|---|
| `health_adoption`, `health_engagement`, `health_sentiment`, `health_support`, `health_commercial` | Five components, 0 to 100 each | Derived (`docs/metrics.md`) | Build (DE, to this spec) |
| `health_score`, `health_band` | Weighted sum (weights in `config/health.yaml`); green, yellow, red | Derived | Build |
| `churn_risk_score`, `churn_top_reasons` | Model probability of churn in 90 days, with reasons in words | Data Science | Build (DS) |
| `expansion_score`, `expansion_top_reasons` | Model probability of expansion in 90 days, with reasons | Data Science | Build (DS) |
| `churn_risk_high`, `expansion_ready` | Above today's capacity cut-off | Derived | Build |

Quality rules: scores between 0 and 1; health between 0 and 100; a score never without
its reasons.

## The contract

Everything in areas 5 and 6, and the daily roll-ups of 1 to 4, lands in one table:
`gold.account_daily`, one row per account per day, 64 columns. Its contract is
`contracts/account_daily.yaml`: columns, types, meaning, freshness and quality rules. A
check fails the pipeline run if a column is missing, has the wrong type, or exists
without being documented.

## The asks, in one list

| Ask | Team | Why it is first |
|---|---|---|
| An explicit `coverage_tier` on the account | RevOps | The pilot segment cannot be selected without it |
| One `consent_status` field with one owner | RevOps, Privacy | No play may send an email without it |
| Account id on every product event | Product Engineering | Events without it cannot be used at all |
| An agreed event dictionary | Product Engineering, DE | Setup steps and usage metrics depend on event names |
| Daily export of shared-mailbox replies | CS Operations, DE | Unsubscribes and buying questions are in there, unread |
| `gold.account_daily` built to the contract | DE | Every play, model and dashboard reads it |

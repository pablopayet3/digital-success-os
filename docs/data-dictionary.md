# Data dictionary

Synthetic data, fictional company. Written by `uv run python run.py docs` from the dbt model files, the data contract and the warehouse. Nothing here is typed by hand.

Bronze is not listed: it is the raw files as they arrived, loaded without change (`ingest/load.py`). Metric definitions are in `docs/metrics.md`.

## Silver: clean, typed, de-duplicated

### silver.stg_events

Clean product events, one row per event. Duplicates and future-dated events removed.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `event_id` | varchar | Unique id of the event. | unique, not_null |
| `occurred_at` | timestamp | When the event happened (UTC). |  |
| `event_date` | date | The day the event happened (UTC). | not_null |
| `account_id` | varchar | The account the event belongs to. Joins to every other table. | not_null, relationships |
| `user_id` | varchar | The product user who did it. |  |
| `event_name` | varchar | What happened. | accepted_values |
| `properties` | json | Extra details of the event, as JSON (for example the board template, or the Assist credits used). |  |
| `_ingested_at` | timestamp | When the pipeline loaded the row. |  |
| `_source_file` | varchar | The landing file the row came from. |  |

### silver.stg_accounts

CRM accounts, one row per account.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `account_id` | varchar | The account. The one id that joins every table. | unique, not_null |
| `account_name` | varchar | Customer name. |  |
| `segment` | varchar | smb, mid or enterprise. | accepted_values |
| `coverage_tier` | varchar | Who looks after the account. The pilot runs on "uncovered". | accepted_values |
| `edition` | varchar | Edition on that day: free, standard, premium or enterprise. | accepted_values |
| `products` | varchar | The Relay products the account owns, as a comma-separated list. |  |
| `has_docs` | boolean | Owns Relay Docs. |  |
| `has_assist` | boolean | Owns Relay Assist (usage-based AI assistant). |  |
| `seats_licensed` | integer | Seats paid for on that day. |  |
| `arr` | integer | Annual recurring revenue today, in dollars. |  |
| `contract_start` | date | Signup date. |  |
| `renewal_date` | date | The next contract anniversary. |  |
| `region` | varchar | Sales region of the account. |  |
| `industry` | varchar | Industry of the account. |  |
| `account_owner` | varchar | The seller who owns the account in the CRM. |  |
| `csm` | varchar | The named success manager. Empty for uncovered accounts. |  |
| `status` | varchar | active or churned, as recorded in the CRM. | accepted_values |
| `churned_at` | date | The date the CRM recorded the account as lost. Empty while it is a customer. |  |

### silver.stg_contacts

CRM contacts, one row per person per account. Emails lowercased, persona normalised.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `contact_id` | varchar | The person. Joins to gold.dim_contact. | unique, not_null |
| `account_id` | varchar | The account. The one id that joins every table. | not_null, relationships |
| `full_name` | varchar | The contact's name. |  |
| `email` | varchar | The contact's email address, lowercased. |  |
| `persona` | varchar | The role this person plays for us. Normalised from free-text CRM entries. | accepted_values |
| `persona_raw` | varchar | The persona tag exactly as the CRM had it, before it was normalised. |  |
| `role` | varchar | Job title. |  |
| `consent_status` | varchar | opted_in, opted_out or unknown, as recorded in the CRM. | accepted_values |
| `email_valid` | boolean | False when the address is known to bounce. |  |
| `product_user_id` | varchar | The contact's user id in the product. Ties a person's product activity to the contact. |  |
| `last_engaged_at` | timestamp | The last time the contact opened, clicked or replied. |  |

### silver.stg_opportunities

CRM opportunities, one row per opportunity.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `opportunity_id` | varchar | One CRM opportunity. | unique, not_null |
| `account_id` | varchar | The account. The one id that joins every table. | relationships |
| `opportunity_type` | varchar | new_business, renewal or expansion. | accepted_values |
| `opportunity_name` | varchar | The name the seller gave the opportunity. |  |
| `stage` | varchar | open, negotiation, closed_won or closed_lost. | accepted_values |
| `is_open` | boolean | True while the stage is open or negotiation. |  |
| `amount` | integer | The value of the opportunity in ARR. |  |
| `created_at` | date | When the opportunity was created. |  |
| `close_date` | date | The day it closed, or is expected to close. |  |
| `owner` | varchar | The seller who owns the opportunity. |  |
| `source` | varchar | Who created the opportunity. |  |

### silver.stg_licenses

Daily licence snapshot, one row per account per day. The spine of the warehouse.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `snapshot_date` | date | The day this row describes. | not_null |
| `account_id` | varchar | The account. The one id that joins every table. | not_null, relationships |
| `edition` | varchar | Edition on that day: free, standard, premium or enterprise. |  |
| `seats_licensed` | integer | Seats paid for on that day. |  |
| `seats_assigned` | integer | Seats given to a user on that day. |  |

### silver.stg_tickets

Support tickets, one row per ticket.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `ticket_id` | varchar | One support ticket. | unique, not_null |
| `account_id` | varchar | The account. The one id that joins every table. | relationships |
| `contact_id` | varchar | The person. Joins to gold.dim_contact. |  |
| `created_at` | timestamp | When the ticket was opened. |  |
| `created_date` | date | The day the ticket was opened. |  |
| `priority` | varchar | low, normal, high or urgent. | accepted_values |
| `is_high_priority` | boolean | True for high and urgent tickets. |  |
| `category` | varchar | What the ticket is about (for example setup_sso, billing, bug). |  |
| `subject` | varchar | The subject line. |  |
| `body` | varchar | The text of the message. |  |
| `status` | varchar | open, pending or resolved. |  |
| `resolved_at` | timestamp | When the ticket was resolved. Empty while it is open. |  |

### silver.stg_nps

NPS responses, one row per response.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `response_id` | varchar | One survey response. | unique, not_null |
| `account_id` | varchar | The account. The one id that joins every table. |  |
| `contact_id` | varchar | The person. Joins to gold.dim_contact. |  |
| `score` | integer | The answer, 0 to 10. | not_null |
| `nps_band` | varchar | promoter (9 or 10), passive (7 or 8) or detractor (0 to 6). |  |
| `comment` | varchar | What the person wrote. May be empty. |  |
| `responded_at` | timestamp | When the person answered. |  |
| `responded_date` | date | The day the person answered. |  |

### silver.stg_email_engagement

Lifecycle emails sent and what the recipient did, one row per send.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `send_id` | varchar | One lifecycle email sent to one contact. | unique, not_null |
| `campaign` | varchar | The email campaign. Emails sent by a play start with "play_". |  |
| `subject` | varchar | The subject line. |  |
| `contact_id` | varchar | The person. Joins to gold.dim_contact. | relationships |
| `account_id` | varchar | The account. The one id that joins every table. |  |
| `sent_at` | timestamp | When the email was sent. |  |
| `sent_date` | date | The day the email was sent. |  |
| `delivered` | boolean | True when the email was delivered. |  |
| `bounced` | boolean | True when the address rejected the email. |  |
| `opened_at` | timestamp | When the email was opened. Empty if it was not. |  |
| `clicked_at` | timestamp | When a link in the email was clicked. Empty if none was. |  |
| `unsubscribed` | boolean | True when the recipient unsubscribed from this email. |  |

### silver.stg_mailbox

Replies in the shared success mailbox, one row per message, linked to the account.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `message_id` | varchar | One message in the shared mailbox. | unique, not_null |
| `received_at` | timestamp | When the reply arrived. |  |
| `received_date` | date | The day the reply arrived. |  |
| `from_email` | varchar | The address the reply came from. |  |
| `from_name` | varchar | The sender's name as their mail program shows it. |  |
| `send_id` | varchar | One lifecycle email sent to one contact. |  |
| `campaign` | varchar | The email campaign. Emails sent by a play start with "play_". |  |
| `account_id` | varchar | Found through the email the message replies to. | not_null |
| `addressed_contact_id` | varchar | The contact the original email was sent to. |  |
| `sender_is_addressee` | boolean | True when the reply came from the address we wrote to. False for a colleague or an automatic responder. |  |
| `subject` | varchar | The subject line. |  |
| `body` | varchar | The text of the message. |  |

### silver.stg_ops_enrollments

Play enrolments from the operational store, treatment and holdout. One row per account per play version.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `enrollment_id` | varchar | One account's entry into one play, treatment or holdout. | unique, not_null |
| `account_id` | varchar | The account. The one id that joins every table. |  |
| `play_id` | varchar | The play, as named in config/plays.yaml. |  |
| `play_version` | integer | The version of the play's configuration when the account entered. A new version starts a new experiment. |  |
| `arm` | varchar | treatment (the play ran) or holdout (eligible, deliberately left alone for comparison). |  |
| `rollout_stage` | varchar | The play's stage when the account entered: slice (10% of eligible accounts) or full. |  |
| `status` | varchar | active, waiting_on_human, completed, exited, or holdout (held out for comparison). |  |
| `exit_reason` | varchar | Why the journey ended. Empty while it is running. |  |
| `trigger_signal` | varchar | The signal that made the account eligible. |  |
| `contact_id` | varchar | The person. Joins to gold.dim_contact. |  |
| `highest_tier` | varchar | The highest rung of the intervention ladder the account reached: digital, agentic or human. |  |
| `enrolled_on` | date | The day the account entered the play, or was held out. | not_null |
| `closed_on` | date | The day the journey ended. |  |

### silver.stg_ops_touches

Every touch a play delivered to a customer.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `touch_id` | varchar | One touch delivered to a customer. | unique, not_null |
| `touch_date` | date | The day it was delivered. |  |
| `account_id` | varchar | The account. The one id that joins every table. |  |
| `contact_id` | varchar | The person. Joins to gold.dim_contact. |  |
| `play_id` | varchar | The play, as named in config/plays.yaml. |  |
| `enrollment_id` | varchar | One account's entry into one play, treatment or holdout. |  |
| `step_id` | varchar | The journey step, as named in config/journeys.yaml. |  |
| `channel` | varchar | email, in_app or agent. |  |
| `tier` | varchar | The rung of the intervention ladder: digital or agentic. (Human steps are tasks, in stg_ops_ctas.) | accepted_values |
| `template` | varchar | The email or in-app template used. |  |
| `outcome` | varchar | For an agent touch, how the conversation ended: resolved, escalated or no_uptake. Empty for emails and in-app prompts. |  |

### silver.stg_ops_ctas

Tasks handed to people, with queue, reason, SLA date and outcome.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `cta_id` | varchar | The task handed to a person (a CTA, call to action). | unique, not_null |
| `account_id` | varchar | The account. The one id that joins every table. |  |
| `play_id` | varchar | The play, as named in config/plays.yaml. |  |
| `enrollment_id` | varchar | One account's entry into one play, treatment or holdout. |  |
| `source` | varchar | What created the task: a journey step, the agent, or the mailbox triage. |  |
| `queue` | varchar | The team queue a task went to (config/routing.yaml). |  |
| `priority` | varchar | urgent, high, normal or low. Worked in that order, then by SLA date. |  |
| `reason_code` | varchar | Why the handoff was made. The full list is in config/routing.yaml. |  |
| `status` | varchar | open or resolved. | accepted_values |
| `created_on` | date | The day the task was created. |  |
| `sla_due_on` | date | The day by which the task must be picked up. |  |
| `picked_up_on` | date | The day a person started on it. |  |
| `resolved_on` | date | The day a person closed it. |  |
| `outcome` | varchar | What the person recorded: resolved, saved, expansion_opportunity, not_a_fit, no_response or agent_should_have_handled. |  |
| `next_state` | varchar | The return signal, what the journey does next: re_enter_journey, exit or sales_owns. |  |

### silver.stg_ops_conversations

Conversations the onboarding agent had, and how each one ended.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `conversation_id` | varchar | One conversation between a customer and the onboarding agent. | unique, not_null |
| `conversation_date` | date | The day of the conversation. |  |
| `account_id` | varchar | The account. The one id that joins every table. |  |
| `play_id` | varchar | The play, as named in config/plays.yaml. |  |
| `enrollment_id` | varchar | One account's entry into one play, treatment or holdout. |  |
| `scenario` | varchar | What kind of customer message started it. In the simulation, the script the simulated customer followed. |  |
| `prompt_version` | varchar | The agent prompt in use (prompts/onboarding_agent/). |  |
| `answered_by` | varchar | The model that wrote the agent's replies, or a note that a hard rule stopped the conversation first. |  |
| `outcome` | varchar | resolved (the agent handled it) or escalated (handed to a person). | accepted_values |
| `reason_code` | varchar | Why the handoff was made. The full list is in config/routing.yaml. |  |
| `escalated_by` | varchar | Who decided to hand off: hard_rule (code), agent (the model asked for a person) or failure (a tool or the model was unavailable). |  |
| `queue` | varchar | The team queue a task went to (config/routing.yaml). |  |
| `customer_turns` | integer | Messages the customer sent. |  |
| `llm_calls` | integer | Model calls made. |  |
| `cost_usd` | double | What those model calls cost, in US dollars. Zero when answers were replayed from the cache. |  |
| `latency_ms` | integer | Time spent waiting for the model, in milliseconds. |  |
| `cta_id` | varchar | The task handed to a person (a CTA, call to action). |  |

### silver.stg_ops_mailbox_triage

What the mailbox triage agent did with each reply.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `message_id` | varchar | One message in the shared mailbox. | unique, not_null |
| `processed_on` | date | The day the reply was read and routed. |  |
| `account_id` | varchar | The account. The one id that joins every table. |  |
| `contact_id` | varchar | The person. Joins to gold.dim_contact. |  |
| `intent` | varchar | What the classifier says the reply is: out_of_office, unsubscribe, left_company, product_question, buying_intent, complaint, meeting_request or other. |  |
| `sentiment` | varchar | positive, neutral or negative. |  |
| `confidence` | double | How sure the classifier is, 0 to 1. Below the bar in config/routing.yaml a person looks at the reply. |  |
| `action` | varchar | What the routing rules did with the reply (for example opted_out, cta_complaint, agent_answered, human_review). |  |
| `cta_id` | varchar | The task handed to a person (a CTA, call to action). |  |

## Gold: ready to use

### gold.dim_account

One row per account as it stands today.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `account_id` | varchar | The account. The one id that joins every table. | unique, not_null |
| `account_name` | varchar | Customer name. |  |
| `segment` | varchar | smb, mid or enterprise. |  |
| `coverage_tier` | varchar | high_touch, pooled or uncovered. The pilot runs on uncovered. |  |
| `edition` | varchar | Edition on that day: free, standard, premium or enterprise. |  |
| `products` | varchar | The Relay products the account owns, as a comma-separated list. |  |
| `has_docs` | boolean | Owns Relay Docs. |  |
| `has_assist` | boolean | Owns Relay Assist (usage-based AI assistant). |  |
| `seats_licensed` | integer | Seats paid for on that day. |  |
| `arr` | integer | Annual recurring revenue today, in dollars. |  |
| `contract_start` | date | Signup date. |  |
| `renewal_date` | date | The next contract anniversary. |  |
| `region` | varchar | Sales region of the account. |  |
| `industry` | varchar | Industry of the account. |  |
| `account_owner` | varchar | The seller who owns the account in the CRM. |  |
| `csm` | varchar | The named success manager. Empty for uncovered accounts. |  |
| `status` | varchar | active or churned, as recorded in the CRM. |  |
| `churned_at` | date | The date the CRM recorded the account as lost. Empty while it is a customer. |  |
| `account_age_days` | bigint | Days since signup, on that day. |  |
| `days_to_renewal` | bigint | Days until the next contract anniversary, counted from that day. |  |
| `renewal_in_negotiation` | boolean | True when an open renewal opportunity is in negotiation today. |  |

### gold.dim_contact

One row per contact, with the flags plays check before a touch.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `contact_id` | varchar | The person. Joins to gold.dim_contact. | unique, not_null |
| `account_id` | varchar | The account. The one id that joins every table. |  |
| `full_name` | varchar | The contact's name. |  |
| `email` | varchar | The contact's email address, lowercased. |  |
| `persona` | varchar | The contact's part in the account, normalised: admin, champion, end_user or billing. |  |
| `persona_raw` | varchar | The persona tag exactly as the CRM had it, before it was normalised. |  |
| `role` | varchar | Job title. |  |
| `consent_status` | varchar | opted_in, opted_out or unknown, as recorded in the CRM. |  |
| `email_valid` | boolean | False when the address is known to bounce. |  |
| `product_user_id` | varchar | The contact's user id in the product. Ties a person's product activity to the contact. |  |
| `last_engaged_at` | timestamp | The last time the contact opened, clicked or replied. |  |
| `can_email` | boolean | True when the contact has opted in and the email address works. | not_null |
| `is_valid_admin` | boolean | True for an admin with a working email address. | not_null |

### gold.fct_usage_daily

Product usage per account per day, including rolling 30-day MAU and Assist credits.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `snapshot_date` | date | The day this row describes. |  |
| `account_id` | varchar | The account. The one id that joins every table. | not_null |
| `active_users` | bigint | Different users active on that day. |  |
| `mau_30d` | bigint | Different users active in the 30 days ending on the snapshot date. | not_null |
| `admin_logins` | bigint | Admin logins on the day. |  |
| `users_invited` | bigint | Users invited on the day. |  |
| `boards_created` | bigint | Boards created on the day. |  |
| `doc_like_boards_created` | bigint | Boards created on the day from a meeting-notes, wiki or knowledge-base template. Doc-style use of Boards. |  |
| `docs_published` | bigint | Docs published on the day. |  |
| `automation_rules_created` | bigint | Automation rules created on the day. |  |
| `integrations_connected` | bigint | Integrations connected on the day. |  |
| `assist_invocations` | bigint | Times Relay Assist was used on the day. |  |
| `assist_credits` | hugeint | Relay Assist credits used on the day. The consumption measure. |  |
| `events_total` | bigint | All product events on the day. |  |

### gold.fct_prerequisites

Setup prerequisites per account and the share that is done.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `account_id` | varchar | The account. The one id that joins every table. | unique, not_null |
| `contract_start` | date | Signup date. |  |
| `days_since_signup` | bigint | Days from signup to today. |  |
| `board_created_on` | date | The day the first board was created. Empty if not yet. |  |
| `users_invited_on` | date | The day the fifth user was invited. Empty if not yet. |  |
| `integration_connected_on` | date | The day the first integration was connected. Empty if not yet. |  |
| `sso_configured_on` | date | The day single sign-on was configured. Empty if not yet. |  |
| `steps_done` | integer | How many of the four setup steps are done. |  |
| `prerequisite_closure_pct` | double | Share of the four setup steps completed (0, 0.25, 0.5, 0.75 or 1). | not_null |

### gold.int_account_daily_base

Building block for account_daily. Every fact about an account on a day.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `account_id` | varchar | The account. The one id that joins every table. |  |
| `snapshot_date` | date | The day this row describes. |  |
| `account_name` | varchar | Customer name. |  |
| `segment` | varchar | smb, mid or enterprise. |  |
| `coverage_tier` | varchar | high_touch, pooled or uncovered. The pilot runs on uncovered. |  |
| `edition` | varchar | Edition on that day: free, standard, premium or enterprise. |  |
| `has_docs` | boolean | Owns Relay Docs. |  |
| `has_assist` | boolean | Owns Relay Assist (usage-based AI assistant). |  |
| `contract_start` | date | Signup date. |  |
| `account_age_days` | bigint | Days since signup, on that day. |  |
| `seats_licensed` | integer | Seats paid for on that day. |  |
| `seats_assigned` | integer | Seats given to a user on that day. |  |
| `seat_utilisation` | double | seats_assigned divided by seats_licensed. |  |
| `seats_assigned_30d_ago` | integer | Seats assigned 30 days earlier. Empty in the account's first 30 days. |  |
| `active_users` | bigint | Different users active on that day. |  |
| `mau_30d` | bigint | Monthly active users: different users active in the 30 days ending that day. |  |
| `mau_prior_30d` | bigint | MAU as it stood 30 days earlier. Empty in the first 30 days. |  |
| `active_user_days_30d` | hugeint | Sum of daily active users over 30 days (depth of use). |  |
| `admin_logins_30d` | hugeint | Admin logins in 30 days. |  |
| `boards_created_30d` | hugeint | Boards created in 30 days. |  |
| `doc_like_boards_60d` | hugeint | Boards created from document-style templates in 60 days (a sign the team needs Docs). |  |
| `docs_published_30d` | hugeint | Docs published in 30 days. |  |
| `assist_invocations_30d` | hugeint | Calls to the AI assistant in 30 days. |  |
| `assist_credits_30d` | hugeint | Assist credits used in 30 days (consumption). |  |
| `automation_rules_total` | bigint | Automation rules created so far. |  |
| `integrations_total` | bigint | Integrations connected so far. |  |
| `automation_rule_limit` | integer | Rules allowed by the edition. |  |
| `integration_limit` | integer | Integrations allowed by the edition. |  |
| `assist_credits_included` | integer | Assist credits included per month for the licensed seats. |  |
| `has_first_board` | boolean | Setup step 1: a board exists. |  |
| `has_five_users` | boolean | Setup step 2: at least five users have a seat. |  |
| `has_integration` | boolean | Setup step 3: an integration is connected. |  |
| `has_sso` | boolean | Setup step 4: single sign-on is configured. |  |
| `tickets_30d` | bigint | Support tickets opened in 30 days. |  |
| `high_priority_tickets_30d` | bigint | High or urgent tickets opened in 30 days. |  |
| `open_high_priority_tickets` | bigint | High or urgent tickets still open at the end of that day. |  |
| `latest_nps_score` | integer | Most recent NPS score on or before that day (0 to 10). Empty if never surveyed. |  |
| `latest_nps_date` | date | Date of that response. |  |
| `lowest_nps_14d` | integer | Lowest NPS score given in the last 14 days. Empty if none. |  |
| `emails_sent_30d` | bigint | Emails sent to the account's contacts in 30 days. |  |
| `emails_opened_30d` | bigint | Of those, how many were opened. |  |
| `emails_clicked_30d` | bigint | Of those, how many were clicked. |  |
| `email_replies_30d` | bigint | Replies received in the shared mailbox in 30 days. |  |
| `contacts_total` | bigint | Contacts on the account today. |  |
| `emailable_contacts` | bigint | Contacts who opted in and have a working address, today. |  |
| `has_valid_admin` | boolean | True when at least one admin can be emailed, today. |  |
| `arr` | integer | Annual recurring revenue today, in dollars. |  |
| `renewal_in_negotiation` | boolean | True when an open renewal opportunity is in negotiation today. |  |
| `prerequisite_closure_pct` | double | Share of the four setup steps done on that day. |  |
| `days_to_renewal` | bigint | Days until the next contract anniversary, counted from that day. |  |

### gold.int_account_daily_health

The daily facts plus the explainable health score and its five components. This is the table the models read their features from.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `account_id` | varchar | The account. The one id that joins every table. |  |
| `snapshot_date` | date | The day this row describes. |  |
| `account_name` | varchar | Customer name. |  |
| `segment` | varchar | smb, mid or enterprise. |  |
| `coverage_tier` | varchar | high_touch, pooled or uncovered. The pilot runs on uncovered. |  |
| `edition` | varchar | Edition on that day: free, standard, premium or enterprise. |  |
| `has_docs` | boolean | Owns Relay Docs. |  |
| `has_assist` | boolean | Owns Relay Assist (usage-based AI assistant). |  |
| `contract_start` | date | Signup date. |  |
| `account_age_days` | bigint | Days since signup, on that day. |  |
| `seats_licensed` | integer | Seats paid for on that day. |  |
| `seats_assigned` | integer | Seats given to a user on that day. |  |
| `seat_utilisation` | double | seats_assigned divided by seats_licensed. |  |
| `seats_assigned_30d_ago` | integer | Seats assigned 30 days earlier. Empty in the account's first 30 days. |  |
| `active_users` | bigint | Different users active on that day. |  |
| `mau_30d` | bigint | Monthly active users: different users active in the 30 days ending that day. |  |
| `mau_prior_30d` | bigint | MAU as it stood 30 days earlier. Empty in the first 30 days. |  |
| `active_user_days_30d` | hugeint | Sum of daily active users over 30 days (depth of use). |  |
| `admin_logins_30d` | hugeint | Admin logins in 30 days. |  |
| `boards_created_30d` | hugeint | Boards created in 30 days. |  |
| `doc_like_boards_60d` | hugeint | Boards created from document-style templates in 60 days (a sign the team needs Docs). |  |
| `docs_published_30d` | hugeint | Docs published in 30 days. |  |
| `assist_invocations_30d` | hugeint | Calls to the AI assistant in 30 days. |  |
| `assist_credits_30d` | hugeint | Assist credits used in 30 days (consumption). |  |
| `automation_rules_total` | bigint | Automation rules created so far. |  |
| `integrations_total` | bigint | Integrations connected so far. |  |
| `automation_rule_limit` | integer | Rules allowed by the edition. |  |
| `integration_limit` | integer | Integrations allowed by the edition. |  |
| `assist_credits_included` | integer | Assist credits included per month for the licensed seats. |  |
| `has_first_board` | boolean | Setup step 1: a board exists. |  |
| `has_five_users` | boolean | Setup step 2: at least five users have a seat. |  |
| `has_integration` | boolean | Setup step 3: an integration is connected. |  |
| `has_sso` | boolean | Setup step 4: single sign-on is configured. |  |
| `tickets_30d` | bigint | Support tickets opened in 30 days. |  |
| `high_priority_tickets_30d` | bigint | High or urgent tickets opened in 30 days. |  |
| `open_high_priority_tickets` | bigint | High or urgent tickets still open at the end of that day. |  |
| `latest_nps_score` | integer | Most recent NPS score on or before that day (0 to 10). Empty if never surveyed. |  |
| `latest_nps_date` | date | Date of that response. |  |
| `lowest_nps_14d` | integer | Lowest NPS score given in the last 14 days. Empty if none. |  |
| `emails_sent_30d` | bigint | Emails sent to the account's contacts in 30 days. |  |
| `emails_opened_30d` | bigint | Of those, how many were opened. |  |
| `emails_clicked_30d` | bigint | Of those, how many were clicked. |  |
| `email_replies_30d` | bigint | Replies received in the shared mailbox in 30 days. |  |
| `contacts_total` | bigint | Contacts on the account today. |  |
| `emailable_contacts` | bigint | Contacts who opted in and have a working address, today. |  |
| `has_valid_admin` | boolean | True when at least one admin can be emailed, today. |  |
| `arr` | integer | Annual recurring revenue today, in dollars. |  |
| `renewal_in_negotiation` | boolean | True when an open renewal opportunity is in negotiation today. |  |
| `prerequisite_closure_pct` | double | Share of the four setup steps done on that day. |  |
| `days_to_renewal` | bigint | Days until the next contract anniversary, counted from that day. |  |
| `health_adoption` | double | 0 to 100. 60% share of assigned seats active this month, 40% setup completion. |  |
| `health_engagement` | double | 0 to 100. 70% email open rate, 30% admin logins. |  |
| `health_sentiment` | double | 0 to 100. Latest NPS score times ten; 60 if never surveyed. |  |
| `health_support` | double | 0 to 100. Falls with open and recent high-priority tickets. |  |
| `health_commercial` | double | 0 to 100. Seat utilisation and the 30-day seat trend. |  |
| `health_score` | double | Weighted average of the five components, 0 to 100. Weights in config/health.yaml. | not_null |
| `health_band` | varchar | green, yellow or red, from the bands in config/health.yaml. | accepted_values |

### gold.fct_outcome_labels

Whether each account churned or expanded in the 90 days after each day, taken from the CRM. The labels the models learn from.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `account_id` | varchar | The account. The one id that joins every table. |  |
| `snapshot_date` | date | The day this row describes. |  |
| `outcome_observed` | boolean | True once the 90 days after the snapshot have fully passed. Only these rows are used for training. |  |
| `churned_within_90d` | boolean | The CRM recorded a churn date in the 90 days after the snapshot. | not_null |
| `expanded_within_90d` | boolean | A closed-won expansion opportunity in the 90 days after the snapshot. | not_null |

### gold.signals

One row per account, per day, per signal that is firing. Read by the rules engine.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `snapshot_date` | date | The day this row describes. |  |
| `account_id` | varchar | The account. The one id that joins every table. | not_null |
| `signal_id` | varchar | The signal that fired. Rules are in docs/metrics.md. | not_null, accepted_values |
| `signal_value` | double | The number that made the rule fire. |  |
| `evidence` | varchar | The reason in words, for a human or an agent. | not_null |

### gold.account_current

Every active account as it stands today, with segmentation and the signals firing.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `account_id` | varchar | The account. The one id that joins every table. | unique, not_null |
| `snapshot_date` | date | The day this row describes. |  |
| `account_name` | varchar | Customer name. |  |
| `segment` | varchar | smb, mid or enterprise. |  |
| `coverage_tier` | varchar | high_touch, pooled or uncovered. The pilot runs on uncovered. |  |
| `edition` | varchar | Edition on that day: free, standard, premium or enterprise. |  |
| `has_docs` | boolean | Owns Relay Docs. |  |
| `has_assist` | boolean | Owns Relay Assist (usage-based AI assistant). |  |
| `contract_start` | date | Signup date. |  |
| `account_age_days` | bigint | Days since signup, on that day. |  |
| `seats_licensed` | integer | Seats paid for on that day. |  |
| `seats_assigned` | integer | Seats given to a user on that day. |  |
| `seat_utilisation` | double | seats_assigned divided by seats_licensed. |  |
| `seats_assigned_30d_ago` | integer | Seats assigned 30 days earlier. Empty in the account's first 30 days. |  |
| `active_users` | bigint | Different users active on that day. |  |
| `mau_30d` | bigint | Monthly active users: different users active in the 30 days ending that day. |  |
| `mau_prior_30d` | bigint | MAU as it stood 30 days earlier. Empty in the first 30 days. |  |
| `active_user_days_30d` | hugeint | Sum of daily active users over 30 days (depth of use). |  |
| `admin_logins_30d` | hugeint | Admin logins in 30 days. |  |
| `boards_created_30d` | hugeint | Boards created in 30 days. |  |
| `doc_like_boards_60d` | hugeint | Boards created from document-style templates in 60 days (a sign the team needs Docs). |  |
| `docs_published_30d` | hugeint | Docs published in 30 days. |  |
| `assist_invocations_30d` | hugeint | Calls to the AI assistant in 30 days. |  |
| `assist_credits_30d` | hugeint | Assist credits used in 30 days (consumption). |  |
| `automation_rules_total` | bigint | Automation rules created so far. |  |
| `integrations_total` | bigint | Integrations connected so far. |  |
| `automation_rule_limit` | integer | Rules allowed by the edition. |  |
| `integration_limit` | integer | Integrations allowed by the edition. |  |
| `assist_credits_included` | integer | Assist credits included per month for the licensed seats. |  |
| `has_first_board` | boolean | Setup step 1: a board exists. |  |
| `has_five_users` | boolean | Setup step 2: at least five users have a seat. |  |
| `has_integration` | boolean | Setup step 3: an integration is connected. |  |
| `has_sso` | boolean | Setup step 4: single sign-on is configured. |  |
| `tickets_30d` | bigint | Support tickets opened in 30 days. |  |
| `high_priority_tickets_30d` | bigint | High or urgent tickets opened in 30 days. |  |
| `open_high_priority_tickets` | bigint | High or urgent tickets still open at the end of that day. |  |
| `latest_nps_score` | integer | Most recent NPS score on or before that day (0 to 10). Empty if never surveyed. |  |
| `latest_nps_date` | date | Date of that response. |  |
| `lowest_nps_14d` | integer | Lowest NPS score given in the last 14 days. Empty if none. |  |
| `emails_sent_30d` | bigint | Emails sent to the account's contacts in 30 days. |  |
| `emails_opened_30d` | bigint | Of those, how many were opened. |  |
| `emails_clicked_30d` | bigint | Of those, how many were clicked. |  |
| `email_replies_30d` | bigint | Replies received in the shared mailbox in 30 days. |  |
| `contacts_total` | bigint | Contacts on the account today. |  |
| `emailable_contacts` | bigint | Contacts who opted in and have a working address, today. |  |
| `has_valid_admin` | boolean | True when at least one admin can be emailed, today. |  |
| `arr` | integer | Annual recurring revenue today, in dollars. |  |
| `renewal_in_negotiation` | boolean | True when an open renewal opportunity is in negotiation today. |  |
| `prerequisite_closure_pct` | double | Share of the four setup steps done on that day. |  |
| `days_to_renewal` | bigint | Days until the next contract anniversary, counted from that day. |  |
| `health_adoption` | double | 0 to 100. 60% share of assigned seats active this month, 40% setup completion. |  |
| `health_engagement` | double | 0 to 100. 70% email open rate, 30% admin logins. |  |
| `health_sentiment` | double | 0 to 100. Latest NPS score times ten; 60 if never surveyed. |  |
| `health_support` | double | 0 to 100. Falls with open and recent high-priority tickets. |  |
| `health_commercial` | double | 0 to 100. Seat utilisation and the 30-day seat trend. |  |
| `health_score` | double | Weighted average of the five components, 0 to 100. |  |
| `health_band` | varchar | green, yellow or red, from the bands in config/health.yaml. |  |
| `churn_risk_score` | double | Modelled chance of churning in the next 90 days (0 to 1). |  |
| `churn_risk_high` | boolean | True when the churn score is above the capacity-based threshold. |  |
| `churn_top_reasons` | varchar | The features pushing the churn score up, in plain words. |  |
| `expansion_score` | double | Modelled chance of expanding in the next 90 days (0 to 1). |  |
| `expansion_ready` | boolean | True when the expansion score is above the capacity-based threshold. |  |
| `expansion_top_reasons` | varchar | The features pushing the expansion score up, in plain words. |  |
| `lifecycle_stage` | varchar | onboarding, adopting, mature, expansion, renewal or at_risk. First matching rule wins; see docs/metrics.md. |  |
| `region` | varchar | Sales region of the account. |  |
| `industry` | varchar | Industry of the account. |  |
| `account_owner` | varchar | The seller who owns the account in the CRM. |  |
| `csm` | varchar | The named success manager. Empty for uncovered accounts. |  |
| `renewal_date` | date | The next contract anniversary. |  |
| `value_tier` | varchar | Size by ARR: free (0), low (under 2,000), mid (under 10,000) or high. | accepted_values |
| `behaviour_cluster` | varchar | The usage cluster the account falls in today (k-means on six usage features), by its plain name. |  |
| `signals_firing` | varchar | The signals firing for the account today, comma-separated, in alphabetical order. |  |

### gold.account_daily

The production table. One row per account per day, joining usage, seats, setup, support, sentiment, contact engagement and commercial data, with the health score, the model scores and the lifecycle stage. Contract in contracts/account_daily.yaml.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `account_id` | varchar | The account. Joins to every other table. | not_null, relationships |
| `snapshot_date` | date | The day this row describes. | not_null |
| `account_name` | varchar | Customer name. |  |
| `segment` | varchar | smb, mid or enterprise. |  |
| `coverage_tier` | varchar | high_touch, pooled or uncovered. The pilot runs on uncovered. | accepted_values |
| `edition` | varchar | Edition on that day: free, standard, premium or enterprise. |  |
| `has_docs` | boolean | Owns Relay Docs. |  |
| `has_assist` | boolean | Owns Relay Assist (usage-based AI assistant). |  |
| `contract_start` | date | Signup date. |  |
| `account_age_days` | bigint | Days since signup, on that day. |  |
| `seats_licensed` | integer | Seats paid for on that day. |  |
| `seats_assigned` | integer | Seats given to a user on that day. |  |
| `seat_utilisation` | double | Seats assigned divided by seats licensed. | not_null |
| `seats_assigned_30d_ago` | integer | Seats assigned 30 days earlier. Empty in the account's first 30 days. |  |
| `active_users` | bigint | Different users active on that day. |  |
| `mau_30d` | bigint | Monthly active users: different users active in the 30 days ending that day. |  |
| `mau_prior_30d` | bigint | MAU as it stood 30 days earlier. Empty in the first 30 days. |  |
| `active_user_days_30d` | hugeint | Sum of daily active users over 30 days (depth of use). |  |
| `admin_logins_30d` | hugeint | Admin logins in 30 days. |  |
| `boards_created_30d` | hugeint | Boards created in 30 days. |  |
| `doc_like_boards_60d` | hugeint | Boards created from document-style templates in 60 days (a sign the team needs Docs). |  |
| `docs_published_30d` | hugeint | Docs published in 30 days. |  |
| `assist_invocations_30d` | hugeint | Calls to the AI assistant in 30 days. |  |
| `assist_credits_30d` | hugeint | Assist credits used in 30 days (consumption). |  |
| `automation_rules_total` | bigint | Automation rules created so far. |  |
| `integrations_total` | bigint | Integrations connected so far. |  |
| `automation_rule_limit` | integer | Rules allowed by the edition. |  |
| `integration_limit` | integer | Integrations allowed by the edition. |  |
| `assist_credits_included` | integer | Assist credits included per month for the licensed seats. |  |
| `has_first_board` | boolean | Setup step 1: a board exists. |  |
| `has_five_users` | boolean | Setup step 2: at least five users have a seat. |  |
| `has_integration` | boolean | Setup step 3: an integration is connected. |  |
| `has_sso` | boolean | Setup step 4: single sign-on is configured. |  |
| `tickets_30d` | bigint | Support tickets opened in 30 days. |  |
| `high_priority_tickets_30d` | bigint | High or urgent tickets opened in 30 days. |  |
| `open_high_priority_tickets` | bigint | High or urgent tickets still open at the end of that day. |  |
| `latest_nps_score` | integer | Most recent NPS score on or before that day (0 to 10). Empty if never surveyed. |  |
| `latest_nps_date` | date | Date of that response. |  |
| `lowest_nps_14d` | integer | Lowest NPS score given in the last 14 days. Empty if none. |  |
| `emails_sent_30d` | bigint | Emails sent to the account's contacts in 30 days. |  |
| `emails_opened_30d` | bigint | Of those, how many were opened. |  |
| `emails_clicked_30d` | bigint | Of those, how many were clicked. |  |
| `email_replies_30d` | bigint | Replies received in the shared mailbox in 30 days. |  |
| `contacts_total` | bigint | Contacts on the account today. |  |
| `emailable_contacts` | bigint | Contacts who opted in and have a working address, today. |  |
| `has_valid_admin` | boolean | True when at least one admin can be emailed, today. |  |
| `arr` | integer | Annual recurring revenue today, in dollars. |  |
| `renewal_in_negotiation` | boolean | True when an open renewal opportunity is in negotiation today. |  |
| `prerequisite_closure_pct` | double | Share of the four setup steps done on that day. | not_null |
| `days_to_renewal` | bigint | Days until the next contract anniversary, counted from that day. |  |
| `health_adoption` | double | 0 to 100. 60% share of assigned seats active this month, 40% setup completion. |  |
| `health_engagement` | double | 0 to 100. 70% email open rate, 30% admin logins. |  |
| `health_sentiment` | double | 0 to 100. Latest NPS score times ten; 60 if never surveyed. |  |
| `health_support` | double | 0 to 100. Falls with open and recent high-priority tickets. |  |
| `health_commercial` | double | 0 to 100. Seat utilisation and the 30-day seat trend. |  |
| `health_score` | double | Explainable health score, 0 to 100. | not_null |
| `health_band` | varchar | green, yellow or red, from the bands in config/health.yaml. |  |
| `churn_risk_score` | double | Modelled chance of churning in the next 90 days (0 to 1). |  |
| `churn_risk_high` | boolean | True when the churn score is above the capacity-based threshold. |  |
| `churn_top_reasons` | varchar | The features pushing the churn score up, in plain words. |  |
| `expansion_score` | double | Modelled chance of expanding in the next 90 days (0 to 1). |  |
| `expansion_ready` | boolean | True when the expansion score is above the capacity-based threshold. |  |
| `expansion_top_reasons` | varchar | The features pushing the expansion score up, in plain words. |  |
| `lifecycle_stage` | varchar | Where the account is in its life. Rules and precedence in docs/metrics.md. | accepted_values |

### gold.dq_summary

What the pipeline caught, one row per data-quality measure.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `sort_order` | integer | The order the measures are shown in. |  |
| `stage` | varchar | Where in the pipeline it was counted: ingest or silver. |  |
| `measure` | varchar | What was counted (for example duplicate_events_removed). | unique, not_null |
| `row_count` | bigint | How many rows. |  |
| `description` | varchar | The measure in a sentence. |  |

### gold.metrics_play_outcomes

What happened to every account that entered a play, treatment and holdout alike. One row per enrolment, with six yes/no outcomes over the measurement window.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `enrollment_id` | varchar | One account's entry into one play, treatment or holdout. | unique, not_null |
| `account_id` | varchar | The account. The one id that joins every table. | not_null, relationships |
| `play_id` | varchar | The play, as named in config/plays.yaml. |  |
| `play_version` | integer | The version of the play's configuration when the account entered. A new version starts a new experiment. |  |
| `arm` | varchar | treatment (received the play) or holdout (held back for comparison). | not_null, accepted_values |
| `rollout_stage` | varchar | The play's stage when the account entered: slice (10% of eligible accounts) or full. |  |
| `status` | varchar | The enrolment's status today (active, waiting_on_human, completed, exited or holdout). |  |
| `highest_tier` | varchar | The highest rung of the intervention ladder the account reached. | accepted_values |
| `enrolled_on` | date | The day the account entered the play, or was held out. |  |
| `window_end` | date | The last day of the measurement window (30 days after entry). |  |
| `window_complete` | boolean | True once the whole window has passed. |  |
| `days_observed` | bigint | Days of the window that have data so far. Results count accounts observed for 7 days or more. |  |
| `segment` | varchar | smb, mid or enterprise. |  |
| `edition` | varchar | Edition on that day: free, standard, premium or enterprise. |  |
| `arr_at_entry` | integer | ARR on the day the account entered the play. |  |
| `setup_completed` | boolean | Setup reached 75% or more on any day in the window. |  |
| `usage_recovered` | boolean | Monthly active users came back to 90% or more of the level before the drop. |  |
| `retained_30d` | boolean | Still a customer at the end of the window. The guardrail for every play. | not_null |
| `valid_admin_restored` | boolean | The account had an admin we may email on any day in the window. |  |
| `expanded_30d` | boolean | An expansion opportunity was closed-won in the window. |  |
| `docs_adopted` | boolean | At least one doc was published in the window. |  |
| `advocate_responded` | boolean | The contact accepted the reference request (clicked its "Yes" link) in the window. Only the reference request play can score it. |  |
| `expansion_amount` | hugeint | Closed-won expansion in the measurement window. |  |
| `retained_arr` | integer | ARR at entry if the account was still a customer at the end of the window, otherwise 0. |  |

### gold.metrics_play_summary

Each play's results by arm and metric. The play config names the success metric.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `play_id` | varchar | The play, as named in config/plays.yaml. |  |
| `arm` | varchar | treatment (the play ran) or holdout (eligible, deliberately left alone for comparison). |  |
| `metric` | varchar | The outcome measured. Definitions are in docs/metrics.md. |  |
| `accounts` | bigint | Accounts in the group. | not_null |
| `successes` | hugeint | Accounts in the group that reached the outcome. |  |
| `arr_at_entry` | hugeint | ARR on the day the account entered the play. |  |
| `retained_arr` | hugeint | ARR at entry if the account was still a customer at the end of the window, otherwise 0. |  |
| `expansion_amount` | hugeint | Closed-won expansion in the measurement window. |  |

### gold.metrics_play_ladder

Results per rung of the intervention ladder (digital, agentic, human).

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `play_id` | varchar | The play, as named in config/plays.yaml. |  |
| `highest_tier` | varchar | The highest rung of the intervention ladder the account reached: digital, agentic or human. |  |
| `metric` | varchar | The outcome measured. Definitions are in docs/metrics.md. |  |
| `accounts` | bigint | Accounts in the group. |  |
| `successes` | hugeint | Accounts in the group that reached the outcome. |  |

### gold.metrics_handoffs

Handoffs to people by queue, reason and source, with pickup time, SLA breaches and outcomes.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `queue` | varchar | The team queue a task went to (config/routing.yaml). |  |
| `reason_code` | varchar | Why the handoff was made. The full list is in config/routing.yaml. |  |
| `source` | varchar | What created the tasks: a journey step, the agent, or the mailbox triage. |  |
| `handoffs` | bigint | Tasks created. |  |
| `closed` | hugeint | Tasks a person has closed. |  |
| `open_now` | hugeint | Tasks still open today. |  |
| `avg_days_to_pickup` | double | Average days from created to picked up. |  |
| `picked_up` | hugeint | Tasks a person has started on. |  |
| `days_to_pickup_total` | hugeint | Days from created to picked up, added over those tasks. Divide by picked_up for the average over several rows. |  |
| `sla_breaches` | hugeint | Tasks picked up after their SLA date, or still open past it. |  |
| `converted` | hugeint | Tasks closed as resolved, saved or expansion_opportunity. A handoff that was worth making. |  |
| `unnecessary` | hugeint | Tasks closed as "the agent should have handled this". |  |
| `recontacted` | hugeint | Closed tasks followed by a new task for the same account within 14 days. The first handoff did not settle it. |  |

### gold.metrics_agent

How the onboarding agent's conversations ended, by origin, prompt version and reason.

| Column | Type | What it means | Tested for |
|---|---|---|---|
| `origin` | varchar | Where the conversation came from: a play, or the mailbox. |  |
| `prompt_version` | varchar | The agent prompt in use (prompts/onboarding_agent/). |  |
| `outcome` | varchar | resolved (the agent handled it) or escalated (handed to a person). |  |
| `reason_code` | varchar | Why the handoff was made. The full list is in config/routing.yaml. |  |
| `escalated_by` | varchar | Who decided to hand off: hard_rule (code), agent (the model asked for a person) or failure (a tool or the model was unavailable). |  |
| `conversations` | bigint | Conversations in the group. |  |
| `avg_customer_turns` | double | Average number of messages the customer sent. |  |
| `llm_calls` | hugeint | Model calls made. |  |
| `cost_usd` | double | What those model calls cost, in US dollars. Zero when answers were replayed from the cache. |  |

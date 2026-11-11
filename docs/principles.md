# Architecture principles

Synthetic data, fictional company. Seven rules that settle most design arguments before
they start. Each one says where the repository enforces it, because a principle nobody
enforces is a preference.

| # | Principle | Why | Where it is enforced |
|---|---|---|---|
| 1 | **One account ID joins everything.** | Telemetry, CRM, tickets, NPS and email all have to meet on one key, or every play is built on a guess. | Events without a valid account id are rejected at ingest (`ingest/schemas.py`). Relationship tests on every table (`dbt/models/`). |
| 2 | **One production table per grain, with a contract.** | Ten teams computing "active users" ten ways is how numbers stop being trusted. | `gold.account_daily` is the only account-day table. Its contract (`contracts/account_daily.yaml`) is checked by code on every run, in both directions. |
| 3 | **Plays are config, not code.** | The person who owns a play should be able to change its threshold, audience or holdout, and the change should be reviewable. | `config/plays.yaml`, `config/journeys.yaml`, `config/routing.yaml`. The catalog refuses to load if it is inconsistent (`engine/catalog.py`). |
| 4 | **AI reads and drafts; people approve anything about money, contracts or permissions.** | A wrong price from an agent is a promise the company must keep. | Hard rules in `agents/escalation.py` stop pricing, contract, refund and legal questions before the agent model is called. Briefs go to a person, never to the customer. |
| 5 | **Every handoff carries full context and returns a signal.** | A handoff without context makes the customer repeat themselves. A handoff without a return signal is a dead end. | The typed handoff packet and `resolve_cta` in `engine/handoff.py`. A journey waits for the outcome and acts on it. |
| 6 | **Every play has an owner, a success metric and a holdout.** | Otherwise nobody can say whether it worked, or whose job it is to fix it. | Required fields in `config/plays.yaml`. Holdout assignment by hash (`engine/assignment.py`). Results in `experiments/`. |
| 7 | **If a tool fails, hand off; never guess.** | A confident wrong answer costs more than a slow right one. | Tool failures, an unavailable model and "no article covers this" all end in a handoff (`agents/onboarding.py`). Tested without a model. |

Three more that came out of building it:

| # | Principle | Why | Where |
|---|---|---|---|
| 8 | **Guardrails live above plays.** | Each play looks reasonable alone. The customer experiences the sum. | Consent, the frequency cap and exclusivity are applied by the engine to every play (`engine/consent.py`, `engine/rules.py`). |
| 9 | **Every decision is logged with its reason, including "no".** | "Why did this account not get the play?" will be asked by a CSM, a seller or a privacy officer. | `audit_log` in the operational store; shown per account and per play in the app. |
| 10 | **Cost is designed in.** | An LLM bill should be a setting, not a surprise. | One module calls the API: cache, offline by default, call and budget limits (`agents/llm.py`). |
# Ownership map

Synthetic data, fictional company. Who is Responsible (does the work), Accountable (one
name, answers for the result), Consulted and Informed, for every table, model, play,
agent and queue. The roles are the ones a company of this shape would have.

**DSPL** = Digital Success Portfolio Lead (this role). **DE** = Data Engineering.
**RevOps** = Revenue Operations. **DS** = Data Science. **AgentEng** = CS AI Agent
Engineering. **CSOps** = CS Operations. **Privacy** = Legal and Privacy.

## Data

| Asset | Responsible | Accountable | Consulted | Informed |
|---|---|---|---|---|
| Product telemetry (events) | Product Engineering | DE | DSPL | DS |
| CRM accounts, contacts, opportunities | RevOps | RevOps | Sales, DSPL | DE |
| Licence snapshots | DE | DE | RevOps | DSPL |
| Tickets, NPS | Support Ops | CSOps | DSPL | DE |
| Email engagement, shared mailbox | CSOps | CSOps | Privacy | DSPL |
| Bronze and silver tables | DE | DE | DSPL | DS |
| `gold.account_daily` and its contract | DE | **DSPL** | DS, RevOps | all consumers |
| Signals (`gold.signals`) | DSPL | DSPL | DS, CSOps | Sales |
| Outcome and metric tables (`metrics_*`) | DSPL | DSPL | DS | CS leadership |
| Contact consent status | RevOps | **Privacy** | CSOps | DSPL |

## Models

| Asset | Responsible | Accountable | Consulted | Informed |
|---|---|---|---|---|
| Health score (weights and bands) | DSPL | DSPL | CSMs, DS | Sales |
| Churn-risk model | DS | DS | DSPL | CSOps |
| Expansion model | DS | DS | DSPL, Sales | RevOps |
| Capacity cut-offs (how many accounts are flagged) | DSPL | DSPL | Scaled CS lead, Sales lead | DS |

## Plays

| Play | Responsible | Accountable | Consulted | Informed |
|---|---|---|---|---|
| Find the admin | CSOps | CS Operations lead | RevOps, Privacy | DSPL |
| Detractor save | Scaled CS team | Scaled CS team lead | Support | DSPL |
| Onboarding rescue | DSPL, AgentEng | DSPL | Scaled CS lead | Product |
| Usage recovery | DSPL | DSPL | Scaled CS lead | Product |
| Edition upgrade | DSPL, Sales | DSPL | Sales lead, Pricing | RevOps |
| Seat expansion | Sales | Sales lead | DSPL | RevOps |
| Cross-product (Docs) | DSPL | DSPL | Product Marketing | Sales |

## Agents

| Asset | Responsible | Accountable | Consulted | Informed |
|---|---|---|---|---|
| Onboarding agent: play spec, escalation rules, eval cases | DSPL | DSPL | AgentEng, Privacy | Scaled CS |
| Onboarding agent: implementation, tools, tracing | AgentEng | AgentEng | DSPL | DE |
| Mailbox triage: routing rules | CSOps | DSPL | Privacy, Sales | Scaled CS |
| Help-centre content (the agent's only source) | Support content team | Support lead | DSPL | AgentEng |
| Prompts and their changelog | DSPL | DSPL | AgentEng | all |
| LLM spend and limits | AgentEng | DSPL | Finance | CS leadership |

## Queues

| Queue | Responsible | Accountable | SLA |
|---|---|---|---|
| Scaled CS (`pooled_csm`) | Pooled CSMs | Scaled CS team lead | 48 hours |
| Account owners (`sales`) | Account owners | Sales lead | 72 hours |
| Support (`support`) | Support agents | Support lead | 24 hours |
| Contact research (`admin_research`) | CSOps | CS Operations lead | 120 hours |
| Mailbox review (`human_review`) | CSOps | CS Operations lead | 48 hours |
| Evaluation review (unnecessary handoffs) | DSPL | DSPL | weekly |

## Gaps: no clear owner today

These are the ones this role would close first. Each has a proposed DRI.

| Gap | Why it matters | Proposed DRI |
|---|---|---|
| The shared mailbox has no owner for replies to journey emails | An unsubscribe or a buying question can sit unread | CS Operations lead, with the triage agent as the first reader |
| Nobody owns the definition of "active user" across teams | Health, signals and dashboards drift apart | DSPL, through the contract on `gold.account_daily` |
| Accounts with no valid admin | No play can reach them, and nobody is asked to fix it | CS Operations lead (the Find the admin play creates the task) |
| Help-centre gaps found by the agent | The docs-gap list has no reader | Support lead; reviewed monthly with DSPL |
| Holdout policy after the pilot | Without a standing holdout, value cannot be shown next year | DSPL, agreed with CS leadership |
| Who may change a play threshold | Silent changes break experiments | DSPL, through change control |
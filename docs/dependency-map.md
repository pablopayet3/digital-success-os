# Dependency map

Synthetic data, fictional company. Which workstream waits for which, and which team owns
it. An arrow means "must exist before". The dashed arrows are the feedback loops.

```mermaid
flowchart LR
    subgraph RevOps["Revenue Operations"]
        CRM["CRM fields: coverage tier,<br/>consent, personas"]
    end
    subgraph ProductEng["Product Engineering"]
        TEL["Telemetry with account id<br/>and an event dictionary"]
    end
    subgraph DE["Data Engineering"]
        PIPE["Pipeline: ingest, bronze,<br/>silver, gold"]
        CONTRACT["gold.account_daily<br/>and its contract"]
    end
    subgraph DS["Data Science"]
        MODELS["Churn and expansion models"]
    end
    subgraph DSPL["Digital Success Portfolio Lead"]
        REQ["Data requirements"]
        SIGNALS["Signals, health score,<br/>lifecycle rules"]
        PLAYS["Play catalog, journeys,<br/>routing, play specs"]
        MEASURE["Experiment and<br/>eval reports"]
    end
    subgraph AgentEng["CS AI Agent Engineering"]
        AGENTS["Onboarding agent,<br/>mailbox triage"]
    end
    subgraph Support["Support content"]
        KB["Help centre"]
    end
    subgraph CSOps["CS Operations"]
        QUEUES["Queues, SLAs, capacity"]
        MAILBOX["Shared mailbox export"]
    end
    subgraph Privacy["Legal and Privacy"]
        CONSENT["Consent rules,<br/>what an agent may say"]
    end
    subgraph People["Scaled CS and Sales"]
        HUMANS["People working handoffs"]
    end

    REQ --> CRM & TEL & MAILBOX
    CRM & TEL & MAILBOX --> PIPE --> CONTRACT
    CONTRACT --> MODELS & SIGNALS
    MODELS --> SIGNALS --> PLAYS
    CONSENT --> PLAYS
    CONSENT --> AGENTS
    KB --> AGENTS
    PLAYS --> AGENTS
    QUEUES --> PLAYS
    PLAYS --> HUMANS
    AGENTS --> HUMANS
    HUMANS --> MEASURE
    PLAYS --> MEASURE
    MEASURE -.->|scale, fix or stop| PLAYS
    HUMANS -.->|unnecessary handoffs become eval cases| AGENTS
    AGENTS -.->|questions no article answers| KB
```

## What blocks what

| Blocked | Waits for | Owner of the blocker | Unblock by |
|---|---|---|---|
| Selecting the pilot segment | An explicit coverage tier in the CRM | RevOps | A field and a backfill rule |
| Sending any journey email | One consent field with one owner | RevOps, Privacy | Agreeing the field and who may change it |
| Setup and usage signals | Account id on every event; agreed event names | Product Engineering | The event dictionary |
| Every play, model and dashboard | `gold.account_daily` built to its contract | Data Engineering | The data requirements and the contract |
| Model-driven plays | Churn and expansion scores with reasons | Data Science | The outcome labels and a capacity number |
| The onboarding agent | Help-centre articles for the setup steps; the rules on what an agent may say | Support content, Privacy | The play spec |
| Any human step | A queue with an owner, an SLA and capacity | CS Operations, Sales | The routing config |
| Reading replies | A daily export of the shared mailbox | CS Operations | An owner for the mailbox |
| A scale decision | Six to eight weeks of results against a holdout | Digital Success Portfolio Lead | The experiment report |

## The critical path

Coverage tier and consent in the CRM, then the production table, then signals, then the
first play on a slice. Everything else can run in parallel behind those four.
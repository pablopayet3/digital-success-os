# 0018: The daily pipeline runs as a GitHub Actions schedule

Status: accepted (Phase 9). Synthetic data, fictional company.

## Context

The pipeline has to run every day without a person starting it: ingest, dbt build with
tests, scoring, freshness and the contract check. A failed run must be noticed.

## Options

1. **Databricks Workflows.** The natural home at a company that runs its warehouse there:
   the job sits next to the data, with retries, alerts and lineage. The free edition this
   demo may use has limits on jobs and compute, and the job definition would live outside
   this repository.
2. **A GitHub Actions workflow on a schedule.** Free, versioned with the code, and it
   already runs the tests. It is a general scheduler, not a data orchestrator: no
   backfills, no lineage, and schedules can start late.
3. A scheduler inside the app container. One more thing to keep alive on a free host that
   sleeps.

## Decision

Option 2 for the demo (`.github/workflows/daily.yml`): a daily cron that runs the
pipeline against the `prod` target when Databricks credentials are present as GitHub
Secrets, and against DuckDB otherwise. A failed step fails the workflow, which opens an
issue labelled `pipeline-failure` and sends GitHub's own failure notification.

## Consequences

- The schedule, the steps and the alert are in the repository and reviewed like code.
- Secrets live in GitHub Secrets, never in a file.
- This does not scale to many dependent jobs. It does not need to.

## Revisit if

The project moves onto a paid Databricks workspace. Then the same steps become one
Workflows job (ingest task, dbt task, scoring task, checks task), with the alert going
to the owning team's channel. The dbt project and the Python entry points do not change.
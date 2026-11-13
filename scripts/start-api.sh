#!/bin/sh
# Start the API. Synthetic data, fictional company.
# The host sets PORT; locally it defaults to 8000. Kept in a file so the start command
# needs no quoting (a quoted `sh -c "..."` failed on the host with "command not found").
# The voice of the "Ask the data" page sends spoken questions here (ADR 0028). With
# ANTHROPIC_API_KEY set in the host's dashboard, the real model answers them, within the
# same total budget the app uses (the total is kept in the shared database).
if [ -n "$ANTHROPIC_API_KEY" ]; then
  export DSO_LLM_STAND_IN=false DSO_OFFLINE_MODE=false DSO_STAND_IN_WHEN_UNAVAILABLE=true
  export LLM_BUDGET_USD="${LLM_BUDGET_USD:-5}" MAX_LLM_CALLS_PER_RUN="${MAX_LLM_CALLS_PER_RUN:-2000}"
fi

# If the host provides a Postgres store, fill it once with the demo state. If that fails
# for any reason, use the local file instead, so the service always comes up.
uv run --no-dev python scripts/seed_store.py || export DSO_OPERATIONAL_STORE="sqlite:///data/ops.db"
exec uv run --no-dev uvicorn api.main:app --host 0.0.0.0 --port "${PORT:-8000}"

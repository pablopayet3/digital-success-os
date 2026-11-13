#!/bin/sh
# Start the app. Synthetic data, fictional company.

# Who answers as the agent on the public demo (ADR 0024).
# Without a key, which is the default, the labelled stand-in answers and nothing is spent.
# With ANTHROPIC_API_KEY set in the host's dashboard, the real model answers until the
# demo has spent 5 dollars in total. The total is kept in the database, so a restart does
# not reset it. After that, and whenever the model cannot answer, the stand-in takes over
# and the screen says so.
if [ -n "$ANTHROPIC_API_KEY" ]; then
  export DSO_LLM_STAND_IN=false DSO_OFFLINE_MODE=false DSO_STAND_IN_WHEN_UNAVAILABLE=true
  export LLM_BUDGET_USD="${LLM_BUDGET_USD:-5}" MAX_LLM_CALLS_PER_RUN="${MAX_LLM_CALLS_PER_RUN:-2000}"
fi

# If the host provides a Postgres store, fill it once with the demo state. If that fails
# for any reason, use the local file instead, so the demo always comes up.
uv run --no-dev python scripts/seed_store.py || export DSO_OPERATIONAL_STORE="sqlite:///data/ops.db"
exec uv run --no-dev streamlit run app/main.py \
  --server.port "${PORT:-8501}" --server.address 0.0.0.0 --server.headless true

#!/bin/sh
# Start the app. Synthetic data, fictional company.
# If the host provides a Postgres store, fill it once with the demo state. If that fails
# for any reason, use the local file instead, so the demo always comes up.
uv run --no-dev python scripts/seed_store.py || export DSO_OPERATIONAL_STORE="sqlite:///data/ops.db"
exec uv run --no-dev streamlit run app/main.py \
  --server.port "${PORT:-8501}" --server.address 0.0.0.0 --server.headless true

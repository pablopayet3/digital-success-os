#!/bin/sh
# Start the API. Synthetic data, fictional company.
# The host sets PORT; locally it defaults to 8000. Kept in a file so the start command
# needs no quoting (a quoted `sh -c "..."` failed on the host with "command not found").
# If the host provides a Postgres store, fill it once with the demo state. If that fails
# for any reason, use the local file instead, so the service always comes up.
uv run --no-dev python scripts/seed_store.py || export DSO_OPERATIONAL_STORE="sqlite:///data/ops.db"
exec uv run --no-dev uvicorn api.main:app --host 0.0.0.0 --port "${PORT:-8000}"

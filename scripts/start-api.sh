#!/bin/sh
# Start the API. Synthetic data, fictional company.
# The host sets PORT; locally it defaults to 8000. Kept in a file so the start command
# needs no quoting (a quoted `sh -c "..."` failed on the host with "command not found").
exec uv run --no-dev uvicorn api.main:app --host 0.0.0.0 --port "${PORT:-8000}"

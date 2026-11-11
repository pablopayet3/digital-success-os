# Thin wrapper: every target forwards to run.py (see docs/decisions/0006).
# On Windows without make, call run.py directly: uv run python run.py <command>

RUN = uv run python run.py

.PHONY: data pipeline train run-day run-days demo app test lint

data:
	$(RUN) data

pipeline:
	$(RUN) pipeline

train:
	$(RUN) train

run-day:
	$(RUN) run-day

run-days:
	$(RUN) run-days

demo:
	$(RUN) demo

app:
	$(RUN) app

test:
	$(RUN) test

lint:
	$(RUN) lint

# 0006: A Python task runner instead of make

Status: accepted (Phase 1). Synthetic data, fictional company.

## Context

The brief names a Makefile as the entry point (`make data`, `make demo`). The demo is built
and presented on a Windows laptop, where `make` is not installed.

## Options

1. Install make on Windows. One more thing to install, and one more thing that can be
   missing on a reviewer's machine.
2. **A small Python script, `run.py`, with the same commands.** Python is already required.
3. A dedicated task tool. Another dependency, for no real gain here.

## Decision

`run.py` is the single entry point: `uv run python run.py data | test | lint | ...`.
The Makefile stays, as a thin wrapper that forwards every target to `run.py`, so
`make demo` still works on machines that have make.

## Consequences

- The same commands work on Windows, macOS and Linux.
- There is one place where each command is defined.
- Commands for later phases already exist and say which phase delivers them.

## Revisit if

The project moves to a CI system or team that standardises on another task tool.

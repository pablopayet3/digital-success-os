"""Shared test set-up. Synthetic data, fictional company.

One small world (250 accounts, 120 days) is generated once per test run, and the
pipeline is run on it once. Every test file reuses them.
"""

import json

import duckdb
import pytest

from ingest.load import warehouse_path
from ingest.pipeline import run_pipeline
from synth.generate import generate


@pytest.fixture(scope="session")
def small_world(tmp_path_factory):
    """(world, data_dir) for the small profile."""
    data_dir = tmp_path_factory.mktemp("data")
    world = generate(profile="small", data_dir=data_dir, verbose=False)
    return world, data_dir


@pytest.fixture(scope="session")
def issues(small_world) -> dict:
    """The log of data problems the generator injected on purpose."""
    _, data_dir = small_world
    return json.loads((data_dir / "ground_truth" / "injected_issues.json").read_text())


@pytest.fixture(scope="session")
def pipeline(small_world):
    """Run ingest and dbt on the small world. Returns (succeeded, data_dir)."""
    _, data_dir = small_world
    succeeded = run_pipeline(data_dir, verbose=False)
    return succeeded, data_dir


@pytest.fixture()
def warehouse(pipeline):
    """A connection to the small warehouse, after the pipeline has run."""
    _, data_dir = pipeline
    con = duckdb.connect(str(warehouse_path(data_dir)))
    yield con
    con.close()

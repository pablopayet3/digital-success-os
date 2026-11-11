"""Shared test set-up. Synthetic data, fictional company.

One small world (250 accounts, 150 days) is generated once per test run. The
pipeline is run on it, the models are trained on it, and every test file reuses
the results.
"""

import hashlib
import json
from pathlib import Path

import duckdb
import pytest

from analytics.train import train_all
from common.store import Store, open_store
from engine.run import run_days
from ingest.load import warehouse_path
from ingest.pipeline import run_pipeline
from synth.generate import generate
from synth.world import World


def file_hashes(folder: Path) -> dict[str, str]:
    """A fingerprint of every file in a folder (the saved world itself is left out)."""
    return {
        str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(folder.rglob("*"))
        if path.is_file() and path.suffix != ".pkl"
    }


@pytest.fixture(scope="session")
def small_world(tmp_path_factory):
    """(world at the end of history, data_dir) for the small profile.

    Later fixtures move the world forward (the simulation), so tests that need the
    world as it is now should use `current_world` instead.
    """
    data_dir = tmp_path_factory.mktemp("data")
    world = generate(profile="small", data_dir=data_dir, verbose=False)
    return world, data_dir


@pytest.fixture(scope="session")
def generated_hashes(small_world) -> dict:
    """Fingerprints of the generated files, taken before anything else touches them."""
    _, data_dir = small_world
    return {name: file_hashes(data_dir / name) for name in ("landing", "ground_truth")}


@pytest.fixture()
def current_world(small_world) -> World:
    """The world as last saved (after any simulated days)."""
    _, data_dir = small_world
    return World.load(data_dir / "ground_truth" / "world_state.pkl")


@pytest.fixture()
def issues(small_world) -> dict:
    """The log of data problems injected on purpose (it grows with each simulated day)."""
    _, data_dir = small_world
    return json.loads((data_dir / "ground_truth" / "injected_issues.json").read_text())


@pytest.fixture(scope="session")
def model_dir(tmp_path_factory):
    """An empty folder for trained models, so tests never touch the real ones."""
    return tmp_path_factory.mktemp("models")


@pytest.fixture(scope="session")
def pipeline(small_world, generated_hashes, model_dir):
    """Run ingest and dbt on the small world, before any model exists.

    Returns (succeeded, data_dir).
    """
    _, data_dir = small_world
    succeeded = run_pipeline(data_dir, verbose=False, model_dir=model_dir)
    return succeeded, data_dir


@pytest.fixture()
def warehouse(pipeline):
    """A connection to the small warehouse, after the pipeline has run."""
    _, data_dir = pipeline
    con = duckdb.connect(str(warehouse_path(data_dir)))
    yield con
    con.close()


@pytest.fixture(scope="session")
def untrained_summary(pipeline) -> dict:
    """What the warehouse held before any model was trained."""
    _, data_dir = pipeline
    con = duckdb.connect(str(warehouse_path(data_dir)))
    scored, flagged = con.execute(
        """
        SELECT count(churn_risk_score), count(*) FILTER (WHERE churn_risk_high)
        FROM gold.account_daily
        """
    ).fetchone()
    fired = con.execute("SELECT DISTINCT signal_id FROM gold.signals").fetchall()
    signals = {row[0] for row in fired}
    con.close()
    return {"scored": scored, "flagged": flagged, "signals": signals}


@pytest.fixture(scope="session")
def trained(pipeline, untrained_summary, model_dir, tmp_path_factory):
    """Train the models on the small world, then run the pipeline again to apply them.

    Returns (metrics, data_dir, card_dir).
    """
    _, data_dir = pipeline
    card_dir = tmp_path_factory.mktemp("model_cards")
    metrics = train_all(data_dir, model_dir, card_dir, verbose=False)
    assert run_pipeline(data_dir, verbose=False, model_dir=model_dir)
    return metrics, data_dir, card_dir


@pytest.fixture()
def scored_warehouse(trained):
    """A connection to the small warehouse once model scores are in."""
    _, data_dir, _ = trained
    con = duckdb.connect(str(warehouse_path(data_dir)))
    yield con
    con.close()


SIMULATED_DAYS = 6


@pytest.fixture(scope="session")
def simulated(trained, model_dir):
    """Six simulated days on the small world: world, pipeline and engine each day.

    Returns (daily summaries, data_dir).
    """
    _, data_dir, _ = trained
    summaries = run_days(SIMULATED_DAYS, data_dir, model_dir, verbose=False)
    return summaries, data_dir


@pytest.fixture()
def ops(simulated) -> Store:
    """The operational store after the simulated days."""
    _, data_dir = simulated
    return open_store(data_dir)

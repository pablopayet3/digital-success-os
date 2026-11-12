"""Tests for the app: every page draws, and the diagrams in the docs can be drawn.

Synthetic data, fictional company. The page tests run each page file the way Streamlit
does, with no browser, on the small simulated world. They catch a page that breaks when
a table or a column changes. They do not check how a page looks.
"""

import socket

import pytest
from streamlit.testing.v1 import AppTest

from app.diagrams import BLOCK, mermaid_to_dot
from common.paths import ROOT
from experiments.analyze import analyse

PAGES = [
    "overview", "accounts", "plays", "agent", "console", "quality", "pilot", "operating", "demo",
]  # fmt: skip


@pytest.fixture()
def app_data(simulated, tmp_path, monkeypatch):
    """Point the app at the small world, with the results tables built."""
    _, data_dir = simulated
    analyse(data_dir, tmp_path, verbose=False)
    monkeypatch.setenv("DSO_DATA_DIR", str(data_dir))
    return data_dir


@pytest.mark.parametrize("page", PAGES)
def test_every_page_draws_without_an_error(page, app_data):
    app = AppTest.from_file(str(ROOT / "app" / "views" / f"{page}.py"), default_timeout=120).run()
    assert not app.exception, f"{page}: {[error.value for error in app.exception]}"
    assert app.title, f"{page} has no title"


def test_the_pilot_page_shows_the_checklist_and_the_weekly_notes(app_data):
    app = AppTest.from_file(str(ROOT / "app" / "views" / "pilot.py"), default_timeout=120).run()
    headings = [heading.value for heading in app.subheader]
    assert "Readiness checklist" in headings and "Weekly review notes" in headings
    lines = [block.value for block in app.markdown]
    assert sum("**Ready**" in line or "**Not ready**" in line for line in lines) == 6


def test_the_overview_shows_the_measures_the_brief_names(app_data):
    app = AppTest.from_file(str(ROOT / "app" / "views" / "overview.py"), default_timeout=120).run()
    labels = " | ".join(metric.label for metric in app.metric)
    for measure in ("Monthly active users", "Consumption", "Prerequisite closure",
                    "Agent invocation", "Handoff rate", "Escalation conversion"):  # fmt: skip
        assert measure in labels, f"missing on the Overview: {measure}"


def test_the_app_draws_with_the_network_off(app_data, monkeypatch):
    """The offline promise: no page reaches for the internet, not even for a drawing library."""
    real_connect = socket.socket.connect

    def this_machine_only(sock, address):
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise AssertionError(f"a page tried to reach {host}")
        return real_connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", this_machine_only)
    for page in ("overview", "plays", "pilot", "operating", "demo"):
        path = str(ROOT / "app" / "views" / f"{page}.py")
        app = AppTest.from_file(path, default_timeout=120).run()
        assert not app.exception, f"{page}: {[error.value for error in app.exception]}"


# --- Diagrams ------------------------------------------------------------------------------------


def test_the_dependency_map_can_be_drawn_in_the_app():
    text = (ROOT / "docs" / "dependency-map.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    (diagram,) = BLOCK.findall(text)
    dot = mermaid_to_dot(diagram)
    assert dot.startswith("digraph {") and "rankdir=LR" in dot
    assert 'label="Data Engineering"' in dot  # a group
    assert "PIPE -> CONTRACT;" in dot  # a plain arrow, from a chain
    assert "CRM -> PIPE;" in dot and "TEL -> PIPE;" in dot  # "A & B --> C"
    feedback = next(line for line in dot.splitlines() if "MEASURE -> PLAYS" in line)
    assert "style=dashed" in feedback and "<td>scale, fix or stop</td>" in feedback


def test_a_diagram_the_translator_does_not_know_is_refused_not_guessed():
    with pytest.raises(ValueError, match="cannot read"):
        mermaid_to_dot('flowchart LR\n    A[("a database")] --> B')

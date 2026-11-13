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
    assert "Handoff quality" in headings
    labels = [metric.label for metric in app.metric]
    assert {"Time to pickup", "SLA breach rate", "Re-contact", "Docs gap share"} <= set(labels)
    assert any("what adding `pooled` would do today" in block.value for block in app.markdown)
    lines = [block.value for block in app.markdown]
    assert sum("**Ready**" in line or "**Not ready**" in line for line in lines) == 6


def test_the_overview_shows_the_measures_the_brief_names(app_data):
    app = AppTest.from_file(str(ROOT / "app" / "views" / "overview.py"), default_timeout=120).run()
    labels = " | ".join(metric.label for metric in app.metric)
    for measure in ("Monthly active users", "AI credits used", "Prerequisite closure",
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


# --- The Live demo page ------------------------------------------------------------------------


def test_the_scripted_story_ends_in_a_task_for_sales(app_data, ops):
    """One click: a setup question is answered, a price question becomes a task for Sales."""
    before = {row["cta_id"] for row in ops.rows("SELECT cta_id FROM ctas")}
    app = AppTest.from_file(str(ROOT / "app" / "views" / "demo.py"), default_timeout=120).run()
    try:
        next(button for button in app.button if button.label == "Run the story").click().run()
        assert not app.exception, [error.value for error in app.exception]
        handoff = " ".join(warning.value for warning in app.warning)
        assert "pricing_contract_legal" in handoff and "sales" in handoff
        assert "hard_rule" in handoff  # code stopped it, before the model was asked
        (task,) = [row for row in ops.rows("SELECT * FROM ctas") if row["cta_id"] not in before]
        assert task["queue"] == "sales" and task["source"] == "agent" and task["cta_id"] in handoff
    finally:
        # The page writes real rows. Take them out again: other tests share this store.
        ops.execute("DELETE FROM conversations WHERE scenario = 'live_demo'")
        for row in ops.rows("SELECT cta_id FROM ctas"):
            if row["cta_id"] not in before:
                ops.execute("DELETE FROM ctas WHERE cta_id = :id", id=row["cta_id"])


def test_the_public_demo_says_on_screen_when_the_model_budget_is_used_up(app_data, tmp_path):
    """ADR 0024. The visitor is told, on the page, that the stand-in has taken over."""
    import dataclasses

    from agents.ledger import SpendLedger
    from agents.llm import LLM, get_llm, set_llm
    from common.settings import load_settings
    from common.store import Store

    usual = get_llm()
    public = dataclasses.replace(
        load_settings(), offline_mode=False, llm_stand_in=False, stand_in_when_unavailable=True
    )
    ledger = SpendLedger(Store(f"sqlite:///{(tmp_path / 'spend.db').as_posix()}"))
    demo = str(ROOT / "app" / "views" / "demo.py")
    try:
        set_llm(LLM(settings=public, cache_dir=tmp_path, ledger=ledger))
        app = AppTest.from_file(demo, default_timeout=120).run()
        assert any("Used so far: $0.00" in caption.value for caption in app.caption)
        assert not any("used up" in warning.value for warning in app.warning)

        ledger.add("agent", "a-model", public.llm_budget_usd)  # the whole budget is spent
        app = AppTest.from_file(demo, default_timeout=120).run()
        assert any("is used up" in warning.value for warning in app.warning)
    finally:
        set_llm(usual)


# --- The shared, hosted demo ---------------------------------------------------------------------


def test_only_an_admin_on_the_hosted_demo_is_offered_the_reset(app_data, monkeypatch):
    """Visitors share one hosted store, so an admin can put it back. Nobody else can."""
    monkeypatch.setenv("DSO_HOSTED", "1")
    console = str(ROOT / "app" / "views" / "console.py")
    for role, offered in (("Admin", True), ("Sales", False)):
        app = AppTest.from_file(console, default_timeout=120)
        app.session_state["console_role"] = role
        app.run()
        assert not app.exception, [error.value for error in app.exception]
        assert any(b.label == "Reset the demo data" for b in app.button) is offered, role


def test_the_overview_opens_with_a_path_for_someone_handed_the_link(app_data):
    app = AppTest.from_file(str(ROOT / "app" / "views" / "overview.py"), default_timeout=120).run()
    (guide,) = [e for e in app.expander if e.label.startswith("First time here?")]
    text = " ".join(block.value for block in guide.markdown)
    assert "Run the story" in text and "Human console" in text and "Synthetic data" in text


# --- The guided tour -----------------------------------------------------------------------------


def test_the_role_is_written_once_and_every_page_opens_with_its_line():
    from app.ui import PAGE_NAMES
    from common.config import load_yaml

    job = load_yaml("job.yaml")
    assert len(job["lines"]) == 10  # the ten lines of the role
    for line in job["lines"]:
        assert line["line"].strip() and line["asks"].strip() and line["plain"].strip()
        assert line["pages"] and all(page in job["pages"] for page in line["pages"])
    # Every page except the Overview answers at least one line, and says what is on it.
    answered = {page for line in job["lines"] for page in line["pages"]}
    assert answered == set(PAGES) - {"overview"} == set(job["pages"])
    assert set(PAGE_NAMES) == set(PAGES)
    # Words the owner ruled out of anything a visitor reads.
    text = " ".join(str(value) for line in job["lines"] for value in line.values())
    text += " ".join(job["pages"].values())
    assert "cheap" not in text.lower() and " thing" not in text.lower()


def test_every_page_opens_with_the_line_of_the_role_it_answers(app_data):
    for page in ("quality", "accounts", "plays", "demo", "agent", "console", "pilot", "operating"):
        app = AppTest.from_file(str(ROOT / "app" / "views" / f"{page}.py"), default_timeout=120)
        app.run()
        opening = " ".join(markdown.value for markdown in app.markdown)
        assert "On this page." in opening, page
        # It reads as a guide to the page, never as notes about a job posting.
        assert "The role asks for" not in opening and "In plain words" not in opening, page


def test_every_number_in_the_app_has_a_definition_to_hover_over(app_data):
    from common.config import load_yaml

    glossary = load_yaml("glossary.yaml")
    shown = 0
    for page in PAGES:
        view = str(ROOT / "app" / "views" / f"{page}.py")
        app = AppTest.from_file(view, default_timeout=120).run()
        for number in app.metric:
            assert number.label in glossary, f"{page}: no definition for '{number.label}'"
            shown += 1
    assert shown >= 25  # the test is looking at real numbers


def test_the_overview_says_what_this_is_and_shows_the_workflow(app_data):
    app = AppTest.from_file(str(ROOT / "app" / "views" / "overview.py"), default_timeout=120).run()
    assert not app.exception, [error.value for error in app.exception]
    words = " ".join(markdown.value for markdown in app.markdown)
    assert "What this is." in words and "Who uses it." in words
    assert "signal" in words and "holdout" in words  # the terms are defined before they are used
    assert "Data arrives and is validated" in words  # the first card of the workflow
    headings = [heading.value for heading in app.subheader]
    assert "The workflow, from signal to outcome" in headings
    assert "A guide to the pages" in headings


def test_every_tour_stop_is_complete_and_every_page_has_a_stop():
    from app.tour import stops

    for stop in stops():
        assert (ROOT / "app" / "views" / f"{stop['page']}.py").exists(), stop["page"]
        for part in ("target", "title", "what", "who", "example"):
            assert stop[part].strip(), f"{stop['title']}: nothing written for '{part}'"
    # A visitor who follows the tour has seen every page of the app.
    assert {stop["page"] for stop in stops()} == set(PAGES)
    # Words the owner ruled out of anything a visitor reads.
    text = " ".join(str(value) for stop in stops() for value in stop.values()).lower()
    assert "cheap" not in text and " thing " not in text and " things " not in text


def words_on(app) -> str:
    """Every label and text a page shows, as one string (what the tour can point at)."""
    words = [number.label for number in app.metric]
    for kind in ("title", "header", "subheader", "markdown", "caption", "info", "warning"):
        words += [str(element.value) for element in getattr(app, kind)]
    for kind in ("selectbox", "multiselect", "text_input", "button", "expander", "tabs"):
        words += [str(getattr(element, "label", "")) for element in getattr(app, kind)]
    return " | ".join(words)


def test_every_tour_stop_points_at_something_that_is_on_its_page(app_data):
    """The frame is drawn around the element that carries the stop's words. If a label on
    a page is reworded and the tour is not, this test names the stop that lost its element."""
    from app.tour import stops

    shown = {}
    for stop in stops():
        page = stop["page"]
        if page not in shown:
            view = str(ROOT / "app" / "views" / f"{page}.py")
            shown[page] = words_on(AppTest.from_file(view, default_timeout=120).run())
        assert stop["target"] in shown[page], f"{page}: nothing says '{stop['target']}'"
        if "tab" in stop:
            assert stop["tab"] in shown[page], f"{page}: no tab called '{stop['tab']}'"


def ui_name(page: str) -> str:
    from app.ui import PAGE_NAMES

    return PAGE_NAMES[page] if page != "overview" else "Digital Success OS"


def test_the_tour_moves_stop_by_stop_and_page_by_page_and_can_be_ended(app_data):
    from app.tour import stops

    app = AppTest.from_file(str(ROOT / "app" / "main.py"), default_timeout=120)
    app.session_state["tour_step"] = 0
    app.run()

    def press(label):
        next(button for button in app.button if button.label == label).click().run()
        assert not app.exception, [error.value for error in app.exception]

    press("Next")
    assert app.session_state["tour_step"] == 1 and app.title[0].value == "Digital Success OS"
    # "Next" on the last stop of a page opens the next page, in the order of the menu.
    all_stops = stops()
    # The last stop of the Overview's first run of stops (the closing stop is on it too).
    last_on_overview = next(i for i, stop in enumerate(all_stops) if stop["page"] != "overview") - 1
    app.session_state["tour_step"] = last_on_overview
    app.run()
    press("Next")
    assert app.title[0].value == ui_name(all_stops[last_on_overview + 1]["page"])
    # The last stop (on the Overview) says "Finish", and finishing ends the tour.
    app = AppTest.from_file(str(ROOT / "app" / "main.py"), default_timeout=120)
    app.session_state["tour_step"] = len(all_stops) - 1
    app.run()
    assert "Next page" not in [button.label for button in app.button]
    press("Finish")
    assert app.session_state["tour_step"] is None
    assert "Next" not in [button.label for button in app.button]


def test_the_tour_greets_a_hosted_visitor_but_never_interrupts_a_local_demo(app_data, monkeypatch):
    main = str(ROOT / "app" / "main.py")
    monkeypatch.delenv("DSO_HOSTED", raising=False)
    local = AppTest.from_file(main, default_timeout=120).run()
    assert "Guided tour" in [button.label for button in local.button]
    assert "Next" not in [button.label for button in local.button]  # no tour by itself

    monkeypatch.setenv("DSO_HOSTED", "1")
    hosted = AppTest.from_file(main, default_timeout=120).run()
    assert "Next" in [button.label for button in hosted.button]  # the first stop is showing


def test_every_choice_of_a_filter_has_a_meaning_to_hover_over(app_data):
    """A filter named in config/options.yaml must explain every choice it offers, and carry
    the same words on its question mark."""
    from common.config import load_yaml

    meanings = load_yaml("options.yaml")
    checked = 0
    for page in PAGES:
        view = str(ROOT / "app" / "views" / f"{page}.py")
        app = AppTest.from_file(view, default_timeout=120).run()
        for one in [*app.multiselect, *app.selectbox]:
            if one.label not in meanings:
                continue  # a list of accounts, tasks or documents, not a list of terms
            assert one.help, f"{page}: '{one.label}' has no question mark"
            for choice in one.options:
                known = meanings[one.label]["choices"]
                assert choice in known, f"{page}: '{one.label}' does not explain '{choice}'"
                checked += 1
    assert checked >= 15  # the three filters of the Accounts page and the console's roles


def test_the_meanings_of_the_choices_agree_with_the_configuration():
    from common.config import load_yaml

    meanings = load_yaml("options.yaml")
    # Every outcome a person can record is explained, and no other.
    assert set(meanings["Outcome"]["choices"]) == set(load_yaml("routing.yaml")["outcomes"])
    # The health bands in words use the thresholds the pipeline uses.
    bands, words = load_yaml("health.yaml")["bands"], meanings["Health band"]["choices"]
    assert f"{bands['green']} or more" in words["green"]
    assert f"from {bands['yellow']} to {bands['green'] - 1}" in words["yellow"]
    assert f"below {bands['yellow']}" in words["red"]
    # Complete sentences, and none of the words the owner ruled out.
    for block in meanings.values():
        for meaning in [block["about"], *block["choices"].values()]:
            assert meaning.strip().endswith("."), meaning
            assert "cheap" not in meaning.lower() and " thing" not in meaning.lower(), meaning


def test_the_script_that_shows_a_meaning_is_given_every_meaning(app_data):
    from common.config import load_yaml

    app = AppTest.from_file(str(ROOT / "app" / "main.py"), default_timeout=120).run()
    assert not app.exception, [error.value for error in app.exception]
    script = next(str(html.proto.body) for html in app.get("html") if "dsoOptionHints" in str(html.proto.body))
    for block in load_yaml("options.yaml").values():
        for choice in block["choices"]:
            assert f'"{choice}"' in script, choice

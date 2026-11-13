"""Tests for the "Ask the data" assistant and its voice (ADR 0028).

Synthetic data, fictional company. No key, no network and no money: the model is a
scripted fake, and the voice service is replaced by a function that returns what the
real service would.
"""

import dataclasses
import socket

import pytest
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from agents import assistant, voice
from agents.assistant import UnsafeSQL, check_sql
from agents.llm import LLM
from api.main import app
from common.paths import ROOT
from common.settings import load_settings

# --- the SQL guard -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM gold.account_current",
        "UPDATE gold.signals SET evidence = ''",
        "DROP TABLE gold.signals",
        "CREATE TABLE gold.x AS SELECT 1",
        "SELECT 1; SELECT 2",
        "SELECT * FROM bronze.raw_events",
        "SELECT * FROM main.anything",
        "SELECT * FROM information_schema.tables",
        "SELECT * FROM ground_truth.latents",
        "SELECT * FROM read_csv('data/ground_truth/latents.csv')",
        "SELECT * FROM read_parquet('x.parquet')",
        "SELECT * FROM accounts",
        "SELECT 1 -- a comment",
        "ATTACH 'other.db'",
        "PRAGMA show_tables",
        "SELECT * FROM 'data/landing/crm_accounts.csv'",
        "SELECT * FROM gold.signals, 'secrets.parquet'",
        'SELECT * FROM "bronze"."raw_events"',
        "SELECT * FROM \"data/landing/tickets.csv\"",
    ],
)
def test_the_sql_guard_refuses_anything_but_one_read_on_gold_or_silver(sql):
    with pytest.raises(UnsafeSQL):
        check_sql(sql)


def test_the_sql_guard_allows_reads_on_gold_and_silver():
    assert check_sql("SELECT count(*) FROM gold.account_current;").endswith("account_current")
    check_sql("WITH t AS (SELECT * FROM gold.signals) SELECT signal_id, count(*) FROM t GROUP BY 1")
    check_sql(
        "SELECT a.account_id FROM gold.account_current a JOIN silver.stg_ops_ctas c "
        "ON a.account_id = c.account_id"
    )
    # Quoted text is fine where it is a value, not a file.
    check_sql("SELECT count(*) FROM gold.signals WHERE signal_id IN ('detractor', 'usage_drop')")


def test_a_query_returns_at_most_the_row_limit(simulated):
    _, data_dir = simulated
    text = assistant.run_sql("SELECT account_id FROM gold.account_daily", data_dir)
    assert text.startswith("50 rows")


# --- the answer loop ------------------------------------------------------------------------


def scripted(responses: list[dict]):
    """A fake model that answers with these responses, in order, and records the requests."""
    seen = []

    def transport(request):
        seen.append(request)
        return responses[len(seen) - 1]

    transport.seen = seen
    return transport


def test_claude_queries_the_warehouse_then_answers_with_the_result(simulated, tmp_path):
    _, data_dir = simulated
    transport = scripted(
        [
            {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "run_sql",
                        "input": {"sql": "SELECT count(*) AS n FROM gold.account_current"},
                    }
                ],
                "stop_reason": "tool_use",
                "model": "claude-sonnet-5-5",
                "usage": {"input_tokens": 900, "output_tokens": 40},
            },
            {
                "content": [{"type": "text", "text": "There are many customers.\n\nSource: x"}],
                "stop_reason": "end_turn",
                "model": "claude-sonnet-5-5",
                "usage": {"input_tokens": 1200, "output_tokens": 30},
            },
        ]
    )
    settings = dataclasses.replace(load_settings(), offline_mode=False, llm_stand_in=False)
    llm = LLM(settings=settings, cache_dir=tmp_path, transport=transport)
    answer = assistant.ask("How many customers are there?", data_dir, llm=llm, use_stored=False)
    assert answer.text.startswith("There are many customers")
    assert answer.sql == ["SELECT count(*) AS n FROM gold.account_current"]
    # The second request carried the query's real result back to the model.
    result = transport.seen[1]["messages"][-1]["content"][0]
    assert result["type"] == "tool_result" and "rows" in result["content"]
    assert transport.seen[0]["system"].startswith("You answer questions about the Digital")


def test_a_refused_query_goes_back_to_claude_as_text_not_as_a_crash(simulated):
    _, data_dir = simulated
    holder = assistant.Answer(question="q", text="")
    output = assistant.run_tool("run_sql", {"sql": "DROP TABLE gold.signals"}, data_dir, holder)
    assert output.startswith("Refused:")


def test_with_no_model_a_typed_question_gets_a_clear_message(simulated, tmp_path):
    _, data_dir = simulated
    settings = dataclasses.replace(load_settings(), offline_mode=True, llm_stand_in=False)
    llm = LLM(settings=settings, cache_dir=tmp_path)  # offline, nothing cached
    answer = assistant.ask("What is the weather?", data_dir, llm=llm, use_stored=False)
    assert not answer.available and "example questions" in answer.text


def test_the_documents_searched_never_name_a_real_platform():
    for passage in assistant.docs_index().passages:
        assert not assistant.REAL_NAMES.search(passage.text), passage.source
        assert "ground_truth" not in passage.source


def test_every_example_question_has_a_stored_answer():
    questions = [q for qs in assistant.examples().values() for q in qs]
    assert len(questions) >= 14 and len(assistant.examples()) == 7
    for question in questions:
        stored = assistant.stored_answer(question)
        assert stored is not None, f"no stored answer for: {question}"
        assert stored.stored and stored.text.strip()
        assert "cheap" not in stored.text.lower()


# --- the API and the voice --------------------------------------------------------------------


@pytest.fixture()
def client(simulated, monkeypatch):
    _, data_dir = simulated
    monkeypatch.setenv("DSO_DATA_DIR", str(data_dir))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("VOICE_BUDGET_USD", raising=False)
    return TestClient(app)


def test_without_a_key_the_voice_is_off_and_says_why(client):
    status = client.get("/assistant/voice-status").json()
    assert status["enabled"] is False and "no key" in status["reason"]
    refused = client.post("/assistant/voice-token")
    assert refused.status_code == 503 and "no key" in refused.json()["detail"]


def test_an_error_from_the_voice_service_is_never_passed_on(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret-value")
    leak = {"error": {"message": "Incorrect API key provided: sk-test-****alue"}}
    monkeypatch.setattr(voice, "_post", lambda url, headers, body: (401, leak))
    refused = client.post("/assistant/voice-token")
    assert refused.status_code == 503
    assert "sk-" not in refused.text and "status 401" in refused.json()["detail"]


def test_a_voice_session_reserves_its_cost_and_shrinks_when_it_ends(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret-value")
    sent = {}

    def service(url, headers, body):
        sent.update(url=url, body=body)
        return 200, {"value": "ek_short_lived", "expires_at": 1_900_000_000}

    monkeypatch.setattr(voice, "_post", service)
    before = client.get("/assistant/voice-status").json()["spent_usd"]
    token = client.post("/assistant/voice-token").json()
    assert token["value"] == "ek_short_lived" and token["session_id"]
    assert "sk-test" not in str(token)
    assert sent["body"] == {"session": {"type": "realtime", "model": voice.config()["model"]}}
    reserved = client.get("/assistant/voice-status").json()["spent_usd"]
    assert reserved == pytest.approx(before + voice.session_reserve_usd(), abs=1e-4)
    # The page reports a two-minute session as plain text, as the browser's beacon sends it.
    body = f'{{"session_id": "{token["session_id"]}", "seconds": 120}}'
    ended = client.post(
        "/assistant/voice-end", content=body, headers={"Content-Type": "text/plain"}
    )
    assert ended.json() == {"recorded": True}
    after = client.get("/assistant/voice-status").json()["spent_usd"]
    assert after == pytest.approx(before + 2 * voice.config()["usd_per_minute"], abs=1e-4)
    # A session can be finished only once, so a second report cannot change the total.
    again = client.post("/assistant/voice-end", content=body)
    assert again.json() == {"recorded": False}


def test_the_voice_stops_at_its_budget(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret-value")
    monkeypatch.setenv("VOICE_BUDGET_USD", "0.01")
    monkeypatch.setattr(voice, "_post", lambda *a: (200, {"value": "ek"}))
    status = client.get("/assistant/voice-status").json()
    assert status["enabled"] is False and "used up" in status["reason"]
    assert client.post("/assistant/voice-token").status_code == 503


def test_only_the_app_may_call_the_assistant_from_a_browser(client):
    allowed = client.get("/assistant/voice-status", headers={"Origin": "http://localhost:8501"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:8501"
    other = client.get("/assistant/voice-status", headers={"Origin": "https://example.org"})
    assert "access-control-allow-origin" not in other.headers


def test_the_api_answers_an_example_question_from_its_stored_answer(client):
    question = next(iter(assistant.examples().values()))[0]
    body = client.post("/assistant/ask", json={"question": question}).json()
    assert body["stored"] is True and body["answer"]
    assert client.post("/assistant/ask", json={"question": "  "}).status_code == 400


# --- the page ---------------------------------------------------------------------------------


def test_the_page_draws_with_the_network_off_and_answers_an_example(simulated, monkeypatch):
    _, data_dir = simulated
    monkeypatch.setenv("DSO_DATA_DIR", str(data_dir))
    real_connect = socket.socket.connect

    def this_machine_only(sock, address):
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise AssertionError(f"the page tried to reach {host}")
        return real_connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", this_machine_only)
    page = AppTest.from_file(str(ROOT / "app" / "views" / "ask.py"), default_timeout=120).run()
    assert not page.exception, [error.value for error in page.exception]
    question = next(iter(assistant.examples().values()))[0]
    next(button for button in page.button if button.label == question).click().run()
    assert not page.exception, [error.value for error in page.exception]
    assert any("stored answer" in caption.value for caption in page.caption)
    # The voice script is on the page, with the voice settings filled in.
    scripts = [str(element.proto.body) for element in page.get("html")]
    assert any("ask_claude" in script and "semantic_vad" in script for script in scripts)
    assert not any("__CONFIG__" in script for script in scripts)

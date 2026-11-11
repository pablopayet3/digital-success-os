"""Tests for the agents, the escalation rules, the mailbox and the LLM cost controls (Phase 5).

Synthetic data, fictional company. All of them run against a stand-in model
(tests/fake_llm.py). They test our code around the model: the rules, the
fallbacks, the limits. Whether the real model answers well is the job of the
evals in Phase 6.
"""

import dataclasses
import json

import fake_llm
import pytest

from agents import mailbox
from agents.briefs import invented_numbers, write_brief
from agents.escalation import MessageSignals, check_message, check_retrieval
from agents.llm import LLM, LLMBudgetReached, LLMUnavailable, get_llm, set_llm
from agents.onboarding import converse, scripted
from agents.retrieval import knowledge_base
from agents.tracing import Trace
from common.settings import load_settings
from common.store import Store
from engine import consent
from engine.context import load_day

REQUEST = ("classifier", "You classify.", [{"role": "user", "content": "hello"}])
# Offline with no stand-in: only cached answers are available.
REPLAY_ONLY = dataclasses.replace(load_settings(), offline_mode=True, llm_stand_in=False)


@pytest.fixture()
def ctx(simulated, tmp_path):
    """Today's data with an empty operational store, so each test starts clean."""
    _, data_dir = simulated
    return load_day(data_dir, Store(f"sqlite:///{(tmp_path / 'ops.db').as_posix()}"))


@pytest.fixture()
def account(ctx) -> dict:
    """An account that still has setup steps to finish."""
    return next(a for a in ctx.accounts.values() if not a["has_sso"] and a["contacts_total"] > 0)


def agent_calls_since(mark: int) -> int:
    return sum(1 for request in fake_llm.calls[mark:] if request["tools"])


# --- Cost controls -----------------------------------------------------------------------


def test_the_same_request_is_paid_for_once(tmp_path):
    llm = fake_llm.fake_llm(tmp_path)
    first = llm.call(*REQUEST)
    second = llm.call(*REQUEST)
    assert not first.cached and first.cost_usd > 0
    assert second.cached and second.cost_usd == 0
    assert second.text == first.text
    assert (llm.paid_calls, llm.cached_calls) == (1, 1)


def test_offline_mode_replays_the_cache_and_never_calls_out(tmp_path):
    fake_llm.fake_llm(tmp_path).call(*REQUEST)  # fills the cache
    offline = LLM(settings=REPLAY_ONLY, cache_dir=tmp_path)
    assert offline.call(*REQUEST).cached
    with pytest.raises(LLMUnavailable, match="offline"):
        offline.call("classifier", "You classify.", [{"role": "user", "content": "something new"}])


def test_a_run_stops_at_the_call_limit_and_reports_its_spend(tmp_path):
    llm = fake_llm.fake_llm(tmp_path, max_calls=2)
    for n in range(2):
        llm.call("classifier", "You classify.", [{"role": "user", "content": f"text {n}"}])
    with pytest.raises(LLMBudgetReached, match="call limit reached"):
        llm.call("classifier", "You classify.", [{"role": "user", "content": "one too many"}])
    assert llm.paid_calls == 2
    assert "2 paid" in llm.summary() and "spent $" in llm.summary()


def test_a_run_stops_at_the_budget(tmp_path):
    llm = fake_llm.fake_llm(tmp_path, budget=0.00001)
    llm.call(*REQUEST)
    with pytest.raises(LLMBudgetReached, match="budget reached"):
        llm.call("classifier", "You classify.", [{"role": "user", "content": "another"}])


def test_cost_comes_from_tokens_and_the_price_list(tmp_path):
    llm = fake_llm.fake_llm(tmp_path)
    response = llm.call(*REQUEST)  # the fake reports 400 input and 60 output tokens
    prices = llm.config["prices_per_million_tokens"][response.model]
    expected = (400 * prices["input"] + 60 * prices["output"]) / 1_000_000
    assert response.cost_usd == pytest.approx(expected)


def test_models_come_from_config_and_only_the_agent_gets_the_stronger_one():
    roles = get_llm().config["roles"]
    assert {role["model"] for name, role in roles.items() if name != "agent"} == {"claude-haiku-5-5"}
    assert roles["agent"]["model"] != "claude-haiku-5-5"


# --- Retrieval ---------------------------------------------------------------------------


@pytest.mark.parametrize("question, article", [
    ("Where do I set up single sign-on? Our IT team is asking.", "sso-setup"),
    ("How do I invite my whole team at once? There are about a dozen of us.", "bulk-invite"),
    ("How do I connect our calendar so due dates show up there?", "calendar-integration"),
    ("What does Premium include compared with Standard?", "editions-comparison"),
    ("I am stuck on setup, what should I do next", "setup-checklist"),
])  # fmt: skip
def test_questions_the_help_centre_answers_are_found(question, article):
    best = knowledge_base().search(question)[0]
    assert best["slug"] == article and best["covers_question"]


@pytest.mark.parametrize("question", [
    "Does Relay support time tracking and timesheets?",
    "What is your refund policy?",
    "Can you integrate with our payroll system?",
    "It doesn't work.",
])  # fmt: skip
def test_questions_the_help_centre_does_not_answer_are_not_covered(question):
    assert not any(result["covers_question"] for result in knowledge_base().search(question))


# --- The hard escalation rules -------------------------------------------------------------


@pytest.mark.parametrize("message, reason, queue", [
    ("Can I just talk to someone?", "customer_asked_for_person", "pooled_csm"),
    ("I want to speak with a real person", "customer_asked_for_person", "pooled_csm"),
    ("How much would it cost to add 10 more seats?", "pricing_contract_legal", "sales"),
    ("Can you send pricing for Premium?", "pricing_contract_legal", "sales"),
    ("I want a refund for last month", "pricing_contract_legal", "pooled_csm"),
    ("What does our contract say about cancellation?", "pricing_contract_legal", "pooled_csm"),
    ("Honestly I'm fed up, this is useless", "frustration", "pooled_csm"),
])  # fmt: skip
def test_keyword_rules_escalate_without_any_model(message, reason, queue):
    escalation = check_message(message, signals=None, earlier=[])
    assert (escalation.reason_code, escalation.queue) == (reason, queue)


def test_the_classifier_catches_what_keywords_miss():
    calm_words = "This is the last straw for us."
    assert check_message(calm_words, None, []) is None  # no keyword matches
    upset = MessageSignals(frustration=0.9)
    assert check_message(calm_words, upset, []).reason_code == "frustration"
    wants_person = MessageSignals(asks_for_human=True)
    assert check_message("Is anyone there?", wants_person, []).reason_code == "customer_asked_for_person"


def test_a_normal_setup_question_is_not_escalated():
    assert check_message("Where do I set up single sign-on?", MessageSignals(topic="setup"), []) is None


def test_the_same_question_twice_is_escalated():
    first = "How do I connect the calendar integration to our boards?"
    again = "how do i connect the calendar integration to our boards"
    assert check_message(again, None, [first]).reason_code == "repeated_question"


def test_no_article_means_one_clarifying_question_at_most():
    assert check_retrieval(None, "Here are the steps.", 0) is None  # nothing was searched
    assert check_retrieval(True, "Here are the steps.", 0) is None  # an article covers it
    assert check_retrieval(False, "Could you tell me more?", 0) is None  # one question is fine
    assert check_retrieval(False, "Could you tell me more?", 1).reason_code == "not_in_docs"
    assert check_retrieval(False, "I think you should try this.", 0).reason_code == "not_in_docs"


# --- Whole conversations ---------------------------------------------------------------------


def test_a_setup_question_is_answered_from_the_help_centre(account):
    conversation = converse(account, scripted(["Where do I set up single sign-on?", "Thanks!"]))
    assert conversation.outcome == "resolved"
    tools_used = {call["name"] for call in conversation.tool_calls}
    assert {"get_setup_status", "search_docs"} <= tools_used
    assert conversation.searches[0]["results"][0]["slug"] == "sso-setup"
    answers = [turn["text"] for turn in conversation.transcript if turn["role"] == "agent"]
    assert "Set up single sign-on" in answers[0]  # the answer names the article it used


def test_a_pricing_question_goes_to_sales_and_the_agent_is_never_asked(account):
    lines = ["Where do I set up single sign-on?", "Thanks. How much would 10 more seats cost?"]
    mark_before = len(fake_llm.calls)
    conversation = converse(account, scripted(lines))
    assert conversation.outcome == "escalated"
    assert conversation.escalation.queue == "sales"
    assert conversation.escalated_by == "hard_rule"
    assert conversation.customer_quote == lines[1]
    assert "10 more seats" in conversation.summary and account["account_name"] in conversation.summary
    # the agent answered the first message only: the pricing message never reached it
    agent_requests = [r for r in fake_llm.calls[mark_before:] if r["tools"]]
    assert all(lines[1] not in json.dumps(r["messages"]) for r in agent_requests)


@pytest.mark.parametrize("message, reason", [
    ("Can I just talk to someone? I don't have time for this.", "customer_asked_for_person"),
    ("Honestly I'm fed up. Nothing works.", "frustration"),
    ("This is the last straw for us.", "frustration"),  # only the classifier catches this one
])  # fmt: skip
def test_a_person_takes_over_before_the_agent_speaks(account, message, reason):
    mark = len(fake_llm.calls)
    conversation = converse(account, scripted([message]))
    assert conversation.outcome == "escalated"
    assert conversation.escalation.reason_code == reason
    assert agent_calls_since(mark) == 0
    assert not [turn for turn in conversation.transcript if turn["role"] == "agent"]


def test_a_failing_tool_means_a_handoff_never_a_guess(account):
    conversation = converse(
        account, scripted(["Where do I set up single sign-on?"]), failing_tool="search_docs"
    )
    assert conversation.outcome == "escalated"
    assert conversation.escalation.reason_code == "tool_failure"
    assert not [turn for turn in conversation.transcript if turn["role"] == "agent"]


def test_a_question_outside_the_help_centre_is_handed_off(account):
    conversation = converse(account, scripted(["Does Relay support time tracking and timesheets?"]))
    assert conversation.outcome == "escalated"
    assert conversation.escalation.reason_code == "not_in_docs"


def test_a_vague_message_gets_one_clarifying_question(account):
    lines = ["It doesn't work.", "Sorry: the invitation emails. My colleagues never received them."]
    conversation = converse(account, scripted(lines))
    answers = [turn["text"] for turn in conversation.transcript if turn["role"] == "agent"]
    assert conversation.outcome == "resolved"
    assert answers[0].endswith("?")
    assert "Invitation emails are not arriving" in answers[1]


def test_when_the_model_is_unavailable_a_person_takes_over(account, tmp_path):
    shared = get_llm()
    set_llm(LLM(settings=REPLAY_ONLY, cache_dir=tmp_path))
    try:
        conversation = converse(account, scripted(["Where do I set up single sign-on?"]))
    finally:
        set_llm(shared)
    assert conversation.outcome == "escalated"
    assert conversation.escalation.reason_code == "agent_unavailable"


def test_when_the_model_declines_a_person_takes_over(account, tmp_path):
    def declining(request):
        response = fake_llm.fake_transport(request)
        if request["tools"]:
            response["stop_reason"], response["content"] = "refusal", []
        return response

    shared = get_llm()
    llm = fake_llm.fake_llm(tmp_path)
    llm.transport = declining
    set_llm(llm)
    try:
        conversation = converse(account, scripted(["Where do I set up single sign-on?"]))
    finally:
        set_llm(shared)
    assert conversation.escalation.reason_code == "agent_unavailable"


# --- Mailbox triage ----------------------------------------------------------------------------


def reply_for(ctx, account, **changes) -> dict:
    contact = consent.emailable_contacts(ctx, account["account_id"])[0]
    reply = {
        "message_id": "M-TEST",
        "account_id": account["account_id"],
        "addressed_contact_id": contact["contact_id"],
        "received_date": ctx.day,
        "subject": "Re: Relay monthly",
        "body": "We need 20 more seats for a new team starting next month.",
    }
    return {**reply, **changes}


def verdict(intent: str, confidence: float = 0.9) -> dict:
    return {"intent": intent, "sentiment": "neutral", "confidence": confidence,
            "seats_requested": "", "edition_mentioned": "", "return_date": "", "new_contact": ""}  # fmt: skip


@pytest.fixture()
def reachable(ctx) -> dict:
    """An account with at least one contact we may email."""
    return next(a for a in ctx.accounts.values() if consent.emailable_contacts(ctx, a["account_id"]))


def test_an_unsubscribe_reply_stops_email_at_once(ctx, reachable):
    reply = reply_for(ctx, reachable)
    contact = consent.emailable_contacts(ctx, reachable["account_id"])[0]
    assert consent.can_email(ctx, contact)
    action, _ = mailbox.route(ctx, reply, verdict("unsubscribe"))
    assert action == "opted_out"
    assert not consent.can_email(ctx, contact)  # before the CRM has been updated
    saved = ctx.store.one("SELECT * FROM consent_changes WHERE contact_id = :c", c=contact["contact_id"])
    assert saved["new_status"] == "opted_out" and saved["source"] == "mailbox_triage"


def test_buying_intent_becomes_a_sales_cta_with_a_brief(ctx, reachable):
    action, cta_id = mailbox.route(ctx, reply_for(ctx, reachable), verdict("buying_intent"))
    assert action == "cta_buying_intent"
    cta = ctx.store.one("SELECT * FROM ctas WHERE cta_id = :id", id=cta_id)
    packet = json.loads(cta["packet"])
    assert (cta["queue"], cta["priority"], cta["source"]) == ("sales", "high", "mailbox")
    assert "20 more seats" in packet["customer_quote"]
    assert packet["brief"]


def test_an_old_buying_reply_is_counted_as_missed(ctx, reachable):
    old = reply_for(ctx, reachable, received_date=ctx.days_ago(90))
    action, cta_id = mailbox.route(ctx, old, verdict("buying_intent"))
    assert (action, cta_id) == ("missed_buying_intent", None)


def test_a_complaint_gets_a_human_and_pauses_the_account(ctx, reachable):
    action, cta_id = mailbox.route(ctx, reply_for(ctx, reachable), verdict("complaint"))
    assert action == "cta_complaint" and cta_id
    assert reachable["account_id"] in ctx.paused
    assert ctx.store.one("SELECT * FROM paused_accounts WHERE cta_id = :id", id=cta_id)


def test_a_contact_who_left_is_no_longer_emailed(ctx, reachable):
    reply = reply_for(ctx, reachable)
    contact = consent.emailable_contacts(ctx, reachable["account_id"])[0]
    action, _ = mailbox.route(ctx, reply, verdict("left_company"))
    assert action in ("contact_marked_gone", "contact_gone_no_admin_left")
    assert not consent.can_email(ctx, contact)


def test_an_unsure_classification_goes_to_a_person(ctx, reachable):
    action, cta_id = mailbox.route(ctx, reply_for(ctx, reachable), verdict("buying_intent", 0.3))
    assert action == "human_review"
    assert ctx.store.one("SELECT queue FROM ctas WHERE cta_id = :id", id=cta_id)["queue"] == "human_review"


def test_out_of_office_replies_are_ignored(ctx, reachable):
    assert mailbox.route(ctx, reply_for(ctx, reachable), verdict("out_of_office")) == ("ignored", None)
    assert ctx.store.one("SELECT count(*) AS n FROM ctas")["n"] == 0


def test_every_reply_in_the_mailbox_is_triaged_exactly_once(ctx):
    counts = mailbox.triage_new_replies(ctx)
    triaged = ctx.store.one("SELECT count(*) AS n FROM mailbox_triage")["n"]
    assert triaged == sum(counts.values()) > 50
    assert {"opted_out", "ignored"} <= set(counts)
    assert mailbox.triage_new_replies(ctx) == {}  # nothing left to do the second time


# --- Briefs, traces, and the simulation ----------------------------------------------------------


def test_a_brief_with_an_invented_number_is_rejected(ctx, reachable, tmp_path):
    enrollment = {"play_id": "expansion_seats", "trigger_signal": "seat_pressure",
                  "trigger_evidence": "seats nearly full"}  # fmt: skip
    assert "AI-written brief" in write_brief(ctx, reachable, enrollment)

    def inventing(request):
        response = fake_llm.fake_transport(request)
        response["content"][0]["text"] += "\nThey will probably add 4321 seats."
        return response

    shared = get_llm()
    llm = fake_llm.fake_llm(tmp_path)
    llm.transport = inventing
    set_llm(llm)
    try:
        brief = write_brief(ctx, reachable, enrollment)
    finally:
        set_llm(shared)
    assert "4321" not in brief and "Template brief" in brief


def test_the_number_check_knows_formatting_is_not_invention():
    facts = {"arr": 12000, "seats_assigned": 18, "health_score": 71.5}
    assert invented_numbers("ARR of $12,000 with 18 seats, health 71.5.", facts) == []
    assert invented_numbers("They have 19 seats.", facts) == ["19"]


def test_traces_mask_names_and_email_addresses(tmp_path):
    trace = Trace("onboarding_agent", "A0001", "2026-09-28", ["Dana Lopez", "Dana"])
    trace.step("customer", text="Hi, I'm Dana Lopez, write to dana.lopez@acme.example please.")
    path = trace.finish("resolved", None, [], tmp_path)
    saved = path.read_text(encoding="utf-8")
    assert "Dana" not in saved and "@acme.example" not in saved
    assert "<name>" in saved and "<email>" in saved


def test_the_simulation_records_conversations_and_their_handoffs(ops):
    conversations = ops.rows("SELECT * FROM conversations")
    assert conversations
    outcomes = {row["outcome"] for row in conversations}
    assert outcomes <= {"resolved", "escalated"}
    for row in conversations:
        assert json.loads(row["transcript"])
        if row["outcome"] == "escalated":
            cta = ops.one("SELECT * FROM ctas WHERE cta_id = :id", id=row["cta_id"])
            packet = json.loads(cta["packet"])
            assert cta["source"] == "agent" and packet["conversation_summary"]
    assert ops.one("SELECT count(*) AS n FROM mailbox_triage")["n"] > 0


# --- Feedback classification, the stand-in mode, and the play specs ----------------------------


def test_recent_feedback_is_classified_once(ctx):
    from agents.feedback import classify_new_feedback

    first = classify_new_feedback(ctx, limit=10)
    rows = ctx.store.rows("SELECT * FROM text_classifications")
    assert first == len(rows) > 0
    assert {row["sentiment"] for row in rows} <= {"positive", "neutral", "negative"}
    classify_new_feedback(ctx, limit=10)
    ids = [r["text_id"] for r in ctx.store.rows("SELECT text_id FROM text_classifications")]
    assert len(ids) == len(set(ids))  # the second batch is new texts, never a repeat


def test_stand_in_mode_is_labelled_and_never_needs_a_key(tmp_path, monkeypatch):
    from agents.stand_in import STAND_IN_MODEL, stand_in_transport

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    settings = dataclasses.replace(load_settings(), offline_mode=True, llm_stand_in=True)
    llm = LLM(settings=settings, cache_dir=tmp_path, transport=stand_in_transport)
    response = llm.call(*REQUEST)
    assert response.model == STAND_IN_MODEL and response.cost_usd == 0
    assert "stand-in" in llm.mode and "$0" in llm.summary()


def test_play_specs_on_disk_match_the_configuration():
    """The specs are generated from the play config. If this fails, run: run.py specs"""
    from engine.specs import SPEC_DIR, render_all

    for play_id, text in render_all().items():
        on_disk = (SPEC_DIR / f"{play_id}.md").read_text(encoding="utf-8")
        assert on_disk == text, f"docs/play-specs/{play_id}.md is out of date"

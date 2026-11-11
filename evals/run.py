"""Evaluate the agents: fixed cases, checked by code first and by an LLM judge second.

Synthetic data, fictional company.

Run with:  uv run python run.py evals

Four parts:

  1. Onboarding agent.  About 30 short conversations (evals/cases/onboarding_agent.yaml).
                        Each is run with every prompt version, so a new prompt is
                        compared with the old one on the same cases before it ships.
  2. Mailbox classifier. Ten replies that are easy to get wrong (evals/cases/mailbox.yaml).
  3. Mailbox accuracy.   A sample of the generated mailbox against the simulator's
                        labels: accuracy and a confusion matrix. (This is evaluation
                        code, so it is allowed to read the ground truth.)
  4. Account briefs.     No number in a brief may be missing from the account's data.

How a case is scored: checks written in code decide first (did it hand off, for the
right reason, to the right queue; did it search the docs; did it say anything it must
never say). Only for answers that pass those does an LLM judge score the wording
against the article the agent used. Code checks are free and never change their
mind; the judge is for what code cannot read.

The report says which model produced the answers. With the rule-based stand-in the
report tests the code around the model and nothing else.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import yaml

from agents.briefs import brief_facts, invented_numbers, write_brief
from agents.classify import classify_replies
from agents.llm import LLMUnavailable, get_llm
from agents.onboarding import Conversation, converse, scripted
from agents.retrieval import knowledge_base
from common.config import load_yaml
from common.paths import DATA_DIR, ROOT

CASE_DIR = ROOT / "evals" / "cases"
REPORT_DIR = ROOT / "evals" / "reports"
PROMPT_VERSIONS = ("v1", "v2")
MAILBOX_SAMPLE = 160  # labelled replies scored for the confusion matrix
JUDGE_PASS_SCORE = 4
BRIEF_SECTIONS = ("Signal", "Evidence", "Likely need", "Suggested opener", "Risks")
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["pass", "fail"]},
        "score": {"type": "integer"},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "score", "reason"],
    "additionalProperties": False,
}


# --- loading cases -------------------------------------------------------------------------


def load_cases(name: str) -> list[dict]:
    """The cases of one suite, with the suite's defaults filled in."""
    suite = yaml.safe_load((CASE_DIR / f"{name}.yaml").read_text(encoding="utf-8"))
    defaults = suite.get("defaults") or {}
    cases = []
    for case in suite["cases"]:
        expect = dict(case.get("expect") or {})
        patterns = list(defaults.get("must_not_match", [])) + list(expect.get("must_not_match", []))
        expect["must_not_match"] = patterns
        cases.append({"play": defaults.get("play"), **case, "expect": expect})
    return cases


def eval_account(variant: str) -> dict:
    """One of the made-up accounts in evals/cases/accounts.yaml."""
    accounts = yaml.safe_load((CASE_DIR / "accounts.yaml").read_text(encoding="utf-8"))
    return {**accounts["base"], **accounts["variants"][variant]}


# --- part 1: the onboarding agent ----------------------------------------------------------------


def run_agent_case(case: dict, prompt_version: str) -> dict:
    """Run one conversation and score it."""
    if case.get("needs_model") and get_llm().settings.llm_stand_in:
        return _skipped(case, "needs a real language model; the stand-in cannot pass it")

    conversation = converse(
        eval_account(case["account"]),
        scripted(case["messages"]),
        prompt_version=prompt_version,
        failing_tool=case.get("failing_tool"),
    )
    checks = check_conversation(case["expect"], conversation)
    judge = None
    if case.get("judge") and conversation.outcome == "resolved" and all(c[1] for c in checks):
        judge = judge_conversation(conversation)
        if judge is not None:
            passed = judge["verdict"] == "pass" and judge["score"] >= JUDGE_PASS_SCORE
            checks.append(("judge", passed, f"{judge['score']}/5: {judge['reason']}"))
    return {
        "id": case["id"],
        "category": case["category"],
        "status": "passed" if all(passed for _, passed, _ in checks) else "failed",
        "failed_checks": [f"{name}: {detail}" for name, passed, detail in checks if not passed],
        "outcome": conversation.outcome,
        "reason_code": conversation.escalation.reason_code if conversation.escalation else None,
        "judge_score": judge["score"] if judge else None,
        "transcript": conversation.transcript,
    }


def check_conversation(expect: dict, conversation: Conversation) -> list[tuple[str, bool, str]]:
    """The checks written in code. Each is (name, passed, what was seen)."""
    checks = []
    escalation = conversation.escalation
    replies = [turn["text"] for turn in conversation.transcript if turn["role"] == "agent"]

    if expect.get("outcome", "any") != "any":
        ok = conversation.outcome == expect["outcome"]
        seen = conversation.outcome + (f" ({escalation.reason_code})" if escalation else "")
        checks.append(("outcome", ok, f"expected {expect['outcome']}, got {seen}"))
    if "reason_code" in expect:
        seen = escalation.reason_code if escalation else "no handoff"
        checks.append(("reason", seen == expect["reason_code"], f"got {seen}"))
    if "queue" in expect:
        seen = escalation.queue if escalation else "no handoff"
        checks.append(("queue", seen == expect["queue"], f"got {seen}"))
    if expect.get("agent_model_called") is False:
        asked = any(call["role"] == "agent" for call in conversation.llm_log)
        checks.append(("stopped before the agent model", not asked, "the agent model was called"))
    for tool in expect.get("must_call", []):
        used = any(call["name"] == tool for call in conversation.tool_calls)
        checks.append((f"used {tool}", used, "the tool was not called"))
    if "retrieved" in expect:
        found = {result["slug"] for search in conversation.searches for result in search["results"]}
        wanted = set(expect["retrieved"])
        checks.append(("retrieval", bool(found & wanted), f"found {sorted(found) or 'nothing'}"))
    if expect.get("first_reply_is_question"):
        ok = bool(replies) and replies[0].rstrip().endswith("?")
        checks.append(
            ("asks to clarify first", ok, f"first reply: {replies[0][:80] if replies else '-'}")
        )
    for pattern in expect.get("must_not_match", []):
        hit = next((r for r in replies if re.search(pattern, r, re.IGNORECASE)), None)
        checks.append(("never says", hit is None, f"matched /{pattern}/ in: {(hit or '')[:80]}"))
    return checks


def judge_conversation(conversation: Conversation) -> dict | None:
    """Ask the judge model to score the answer against the articles the agent found."""
    articles = {article.slug: article for article in knowledge_base().articles}
    found = {result["slug"] for search in conversation.searches for result in search["results"]}
    payload = {
        "conversation": conversation.transcript,
        "articles": [
            {"title": articles[slug].title, "text": articles[slug].text} for slug in sorted(found)
        ],
    }
    try:
        response = get_llm().call(
            "judge",
            (ROOT / "prompts" / "judge.md").read_text(encoding="utf-8"),
            [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            json_schema=JUDGE_SCHEMA,
            purpose="eval judge",
        )
        return json.loads(response.text)
    except (LLMUnavailable, ValueError):
        return None  # no judge available: the code checks still count


# --- part 2: mailbox cases -------------------------------------------------------------------------


def run_mailbox_cases(cases: list[dict]) -> list[dict]:
    """Classify the hand-written replies and compare with the expected intent."""
    routes = load_yaml("routing.yaml")["mailbox"]
    stand_in = get_llm().settings.llm_stand_in
    runnable = [case for case in cases if not (case.get("needs_model") and stand_in)]
    classified = classify_replies(
        [{"id": c["id"], "subject": c["subject"], "body": c["body"]} for c in runnable]
    )
    results = []
    for case in cases:
        if case not in runnable:
            results.append(_skipped(case, "needs a real language model"))
            continue
        got = classified.get(case["id"])
        if got is None:
            results.append({**_skipped(case, "the classifier was unavailable"), "status": "failed"})
            continue
        expect, failed = case["expect"], []
        if got["intent"] != expect["intent"]:
            failed.append(f"intent: expected {expect['intent']}, got {got['intent']}")
        if "max_confidence" in expect and got["confidence"] > expect["max_confidence"]:
            failed.append(f"confidence {got['confidence']} is too sure for this reply")
        unsure = got["confidence"] < routes["min_confidence"]
        action = "review" if unsure else routes["routes"][got["intent"]]["action"]
        results.append(
            {
                "id": case["id"],
                "category": expect["intent"],
                "status": "failed" if failed else "passed",
                "failed_checks": failed,
                "outcome": f"{got['intent']} ({got['confidence']:.2f}) -> {action}",
            }
        )
    return results


# --- part 3: mailbox accuracy against the simulator's labels -----------------------------------------


def mailbox_accuracy(data_dir: Path = DATA_DIR, sample: int = MAILBOX_SAMPLE) -> dict | None:
    """Score the classifier on labelled replies. None when there is no generated data."""
    labels_file = data_dir / "ground_truth" / "mailbox_labels.csv"
    mailbox_dir = data_dir / "landing" / "mailbox"
    if not labels_file.exists() or not mailbox_dir.exists():
        return None
    labels = pd.read_csv(labels_file, dtype=str).set_index("message_id")
    messages = {}
    for path in sorted(mailbox_dir.glob("*.json")):
        loaded = json.loads(path.read_text(encoding="utf-8"))
        for message in loaded if isinstance(loaded, list) else [loaded]:
            messages[message["message_id"]] = message
    ids = sorted(set(messages) & set(labels.index))
    step = max(1, len(ids) // sample)
    chosen = ids[::step][:sample]  # evenly spread, the same replies on every run

    predicted = classify_replies(
        [{"id": i, "subject": messages[i]["subject"], "body": messages[i]["body"]} for i in chosen]
    )
    rows = [
        {
            "message_id": i,
            "actual": labels.loc[i, "intent"],
            "predicted": predicted[i]["intent"],
            "hard": labels.loc[i, "is_hard"] == "true",
            "confidence": predicted[i]["confidence"],
        }
        for i in chosen
        if i in predicted
    ]
    if not rows:
        return {"scored": 0}
    frame = pd.DataFrame(rows)
    right = frame["actual"] == frame["predicted"]
    matrix = pd.crosstab(frame["actual"], frame["predicted"])
    per_intent = []
    for intent in sorted(set(frame["actual"]) | set(frame["predicted"])):
        said, was = frame["predicted"] == intent, frame["actual"] == intent
        per_intent.append(
            {
                "intent": intent,
                "replies": int(was.sum()),
                "precision": _share((said & was).sum(), said.sum()),
                "recall": _share((said & was).sum(), was.sum()),
            }
        )
    # The two mistakes that cost the most: a missed unsubscribe (consent) and a missed complaint.
    costly = frame[frame["actual"].isin(["unsubscribe", "complaint"]) & ~right]
    return {
        "scored": len(frame),
        "accuracy": _share(right.sum(), len(frame)),
        "accuracy_easy": _share(right[~frame["hard"]].sum(), (~frame["hard"]).sum()),
        "accuracy_hard": _share(right[frame["hard"]].sum(), frame["hard"].sum()),
        "per_intent": per_intent,
        "matrix": {actual: row.to_dict() for actual, row in matrix.iterrows()},
        "costly_misses": costly[["message_id", "actual", "predicted"]].to_dict("records"),
    }


# --- part 4: briefs ---------------------------------------------------------------------------------


def run_brief_case(case: dict) -> dict:
    account = {**eval_account(case["account"]), "account_name": "Harbour Lane Studio"}
    brief = write_brief(None, account, case["trigger"])
    facts = brief_facts(account, case["trigger"])
    failed = []
    invented = invented_numbers(brief, facts)
    if invented:
        failed.append(f"numbers not in the account's data: {invented}")
    for section in BRIEF_SECTIONS:
        if section.lower() not in brief.lower():
            failed.append(f"section missing: {section}")
    for text in case["expect"].get("must_contain", []):
        if text not in brief:
            failed.append(f"does not mention {text}")
    kind = "AI-written" if "AI-written brief" in brief else "template (the fallback)"
    return {
        "id": case["id"],
        "category": "brief",
        "status": "failed" if failed else "passed",
        "failed_checks": failed,
        "outcome": kind,
    }


# --- running everything and writing the report ---------------------------------------------------------


def run_evals(
    data_dir: Path = DATA_DIR,
    report_dir: Path = REPORT_DIR,
    versions: tuple[str, ...] = PROMPT_VERSIONS,
    verbose: bool = True,
) -> dict:
    """Run every suite, write the report, and return the results."""
    llm = get_llm()
    agent_cases = load_cases("onboarding_agent")
    results = {
        "llm_mode": llm.mode,
        "models": {role: cfg["model"] for role, cfg in llm.config["roles"].items()},
        "prompt_in_use": llm.config["prompt_versions"]["onboarding_agent"],
        "agent": {v: [run_agent_case(case, v) for case in agent_cases] for v in versions},
        "mailbox_cases": run_mailbox_cases(load_cases("mailbox")),
        "mailbox_accuracy": mailbox_accuracy(data_dir),
        "briefs": [run_brief_case(case) for case in load_cases("briefs")],
        "llm_summary": llm.summary(),
    }
    results["totals"] = {
        **{f"onboarding agent ({v})": tally(results["agent"][v]) for v in versions},
        "mailbox cases": tally(results["mailbox_cases"]),
        "briefs": tally(results["briefs"]),
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "eval-results.json").write_text(
        json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n"
    )
    (report_dir / "eval-report.md").write_text(
        render_report(results, versions), encoding="utf-8", newline="\n"
    )
    if verbose:
        for suite, counts in results["totals"].items():
            print(f"{suite}: {counts['passed']} of {counts['run']} passed"
                  + (f" ({counts['skipped']} skipped)" if counts["skipped"] else ""))  # fmt: skip
        if results["mailbox_accuracy"] and results["mailbox_accuracy"]["scored"]:
            accuracy = results["mailbox_accuracy"]
            print(f"mailbox accuracy: {accuracy['accuracy']:.0%} on {accuracy['scored']} replies")
        print(results["llm_summary"])
        print("Report: evals/reports/eval-report.md")
    return results


def tally(results: list[dict]) -> dict:
    statuses = [result["status"] for result in results]
    run = len(statuses) - statuses.count("skipped")
    return {
        "run": run,
        "passed": statuses.count("passed"),
        "failed": statuses.count("failed"),
        "skipped": statuses.count("skipped"),
        "pass_rate": _share(statuses.count("passed"), run),
    }


def render_report(results: dict, versions: tuple[str, ...]) -> str:
    lines = [
        "# Evaluation report",
        "",
        "Synthetic data, fictional company. Written by `uv run python run.py evals`.",
        "",
        f"- **Answers produced by:** {results['llm_mode']}",
        f"- **Agent prompt in use:** {results['prompt_in_use']}",
        f"- **Models in config:** agent `{results['models']['agent']}`, classifier and judge "
        f"`{results['models']['judge']}`",
        f"- **Cost of this run:** {results['llm_summary']}",
        "",
    ]
    if "stand-in" in results["llm_mode"]:
        lines += [
            "> **Read this first.** These results come from the rule-based stand-in, not from a",
            "> language model. They show that the code around the model works: the escalation",
            "> rules, the tools, retrieval, routing and the number check on briefs. They say",
            "> nothing about how well a real model answers, and the two prompt versions cannot",
            "> differ because the stand-in does not read the prompt. Cases that need language",
            "> understanding are skipped. Run once with an API key to replace this report.",
            "",
        ]
    lines += ["## Summary", "", "| Suite | Cases run | Passed | Failed | Skipped | Pass rate |",
              "|---|---|---|---|---|---|"]  # fmt: skip
    for suite, counts in results["totals"].items():
        lines.append(
            f"| {suite} | {counts['run']} | {counts['passed']} | {counts['failed']} | "
            f"{counts['skipped']} | {_pct(counts['pass_rate'])} |"
        )

    lines += ["", "## Onboarding agent: prompt versions compared", ""]
    lines += ["The same cases, run with each prompt version. Pass rate by category.", ""]
    lines += [
        "| Category | Cases | " + " | ".join(versions) + " |",
        "|---|---|" + "---|" * len(versions),
    ]
    categories = sorted({result["category"] for result in results["agent"][versions[0]]})
    for category in categories:
        cells, count = [], 0
        for version in versions:
            subset = [r for r in results["agent"][version] if r["category"] == category]
            counts = tally(subset)
            count = len(subset)
            cells.append(f"{counts['passed']} of {counts['run']}")
        lines.append(f"| {category} | {count} | " + " | ".join(cells) + " |")
    if len(versions) > 1:
        first, last = versions[0], versions[-1]
        before = {r["id"]: r["status"] for r in results["agent"][first]}
        changed = [
            f"- `{r['id']}`: {before[r['id']]} with {first}, {r['status']} with {last}"
            for r in results["agent"][last]
            if before[r["id"]] != r["status"]
        ]
        lines += ["", f"Cases whose result changed between {first} and {last}:", ""]
        lines += changed or ["- None."]

    lines += ["", "## Failures", ""]
    failures = [
        f"- `{result['id']}` ({suite}): " + "; ".join(result["failed_checks"])
        for suite, group in _all_groups(results, versions)
        for result in group
        if result["status"] == "failed"
    ]
    lines += failures or ["None."]
    skipped = sorted(
        {
            f"- `{result['id']}`: {result['outcome']}"
            for _, group in _all_groups(results, versions)
            for result in group
            if result["status"] == "skipped"
        }
    )
    if skipped:
        lines += ["", "## Skipped", "", *skipped]

    lines += ["", "## Mailbox classifier: hand-written cases", ""]
    lines += ["| Case | Result | Classified as -> action |", "|---|---|---|"]
    for result in results["mailbox_cases"]:
        lines.append(f"| `{result['id']}` | {result['status']} | {result['outcome']} |")

    accuracy = results["mailbox_accuracy"]
    lines += ["", "## Mailbox classifier: accuracy against the simulator's labels", ""]
    if not accuracy:
        lines.append("Not run: there is no generated data on this machine.")
    elif not accuracy["scored"]:
        lines.append("Not run: the classifier was unavailable.")
    else:
        lines += [
            f"{accuracy['scored']} replies, evenly sampled. Accuracy **{_pct(accuracy['accuracy'])}** "
            f"(plain replies {_pct(accuracy['accuracy_easy'])}, deliberately hard ones "
            f"{_pct(accuracy['accuracy_hard'])}).",
            "",
            "| Intent | Replies | Precision | Recall |",
            "|---|---|---|---|",
        ]
        for row in accuracy["per_intent"]:
            lines.append(
                f"| {row['intent']} | {row['replies']} | {_pct(row['precision'])} | "
                f"{_pct(row['recall'])} |"
            )
        predicted = sorted({p for row in accuracy["matrix"].values() for p in row})
        lines += [
            "",
            "Confusion matrix (rows: what it was; columns: what the classifier said).",
            "",
        ]
        lines += ["| | " + " | ".join(predicted) + " |", "|---|" + "---|" * len(predicted)]
        for actual, row in sorted(accuracy["matrix"].items()):
            lines.append(
                f"| **{actual}** | " + " | ".join(str(row.get(p, 0)) for p in predicted) + " |"
            )
        misses = accuracy["costly_misses"]
        lines += [
            "",
            f"Costly misses (an unsubscribe or a complaint read as something else): **{len(misses)}**.",
        ]
        lines += [
            f"- `{m['message_id']}`: was {m['actual']}, read as {m['predicted']}"
            for m in misses[:10]
        ]

    lines += ["", "## Account briefs", "", "| Case | Result | Brief used |", "|---|---|---|"]
    for result in results["briefs"]:
        lines.append(f"| `{result['id']}` | {result['status']} | {result['outcome']} |")
    lines += [
        "",
        "## How to read this",
        "",
        "- A case passes only when every check written in code passes. The judge is asked only",
        "  about answers that already passed those checks, and scores wording and grounding.",
        "- A new prompt version becomes the default only when it does not lose a case the old",
        "  one passed in the hard-rule categories (pricing, contract, person, frustration).",
        '- Handoffs that people close as "the agent should have handled this" become new cases',
        "  under `evals/cases/from_feedback/`.",
        "",
    ]
    return "\n".join(lines)


def _all_groups(results: dict, versions: tuple[str, ...]):
    for version in versions:
        yield f"onboarding agent, {version}", results["agent"][version]
    yield "mailbox", results["mailbox_cases"]
    yield "brief", results["briefs"]


def _skipped(case: dict, why: str) -> dict:
    return {
        "id": case["id"],
        "category": case.get("category", "mailbox"),
        "status": "skipped",
        "failed_checks": [],
        "outcome": why,
    }


def _share(part, whole) -> float | None:
    return round(float(part) / float(whole), 4) if whole else None


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"

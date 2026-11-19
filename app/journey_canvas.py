"""The journey canvas: one play drawn as a flow, from its signal (top) to its last step.

Synthetic data, fictional company. The picture is drawn from the same configuration that
runs the play (config/plays.yaml and config/journeys.yaml), so it cannot disagree with
what the system does (ADR 0034). Each step shows how many customers reached it, read from
the journey's own record of events.

Colours follow the ladder of help: a digital step, the AI agent, a person. The output is
Graphviz's DOT language, which the page draws with st.graphviz_chart, offline.
"""

from __future__ import annotations

from engine.journeys import STEP_HAPPENED

TIER_COLOURS = {"digital": "#cfe1ff", "agentic": "#e3d7ff", "human": "#ffe2c2"}
NEUTRAL = "#eceff3"


def step_counts(store, play_id: str) -> dict[str, int]:
    """How many enrolments reached each step that touches a customer or a person."""
    reached: dict[str, set] = {}
    rows = store.rows(
        "SELECT step_id, event, enrollment_id FROM journey_events WHERE play_id = :play",
        play=play_id,
    )
    for row in rows:
        if row["event"].startswith(STEP_HAPPENED) or row["event"] == "draft_created":
            reached.setdefault(row["step_id"], set()).add(row["enrollment_id"])
    return {step: len(ids) for step, ids in reached.items()}


def journey_dot(play, journey, queues: dict, signal_names: dict, counts: dict, arms: dict) -> str:
    """The play as a left-to-right flow in DOT. `arms`: {"treatment": n, "holdout": n}."""
    lines = [
        "digraph journey {",
        '  rankdir=TB; bgcolor="transparent"; nodesep=0.5; ranksep=0.3;',
        '  node [shape=box style="rounded,filled" fontname="Helvetica" fontsize=11 '
        f'fillcolor="{NEUTRAL}" color="#8a94a6" margin="0.15,0.08"];',
        '  edge [color="#9aa4b2" fontcolor="#9aa4b2" fontname="Helvetica" fontsize=11];',
    ]
    signals = " or ".join(signal_names.get(s, s) for s in play.trigger)
    lines.append(f'  signal [label="Signal\\n{_wrap(signals)}" shape=box fillcolor="#fff3b0"];')
    lines.append(
        f'  entry [label="Who may enter\\n{_wrap(_audience(play))}" fillcolor="{NEUTRAL}"];'
    )
    held = f"{play.holdout_pct:.0%} held out for comparison\\n{arms.get('holdout', 0)} customers"
    lines.append(f'  holdout [label="{held}" shape=note fillcolor="#f4f4f4"];')
    lines.append("  signal -> entry;")
    lines.append('  entry -> holdout [style=dashed label=" by a fixed rule"];')

    ids = [step.id for step in journey.steps]
    for step in journey.steps:
        lines.append(f"  {_node(step.id)} [{_attributes(step, queues, counts, signal_names)}];")
    if ids:
        lines.append(f'  entry -> {_node(ids[0])} [label=" {arms.get("treatment", 0)} entered"];')
    for position, step in enumerate(journey.steps):
        if step.type == "branch":
            lines.append(f'  {_node(step.id)} -> {_node(step.then)} [label=" yes"];')
            lines.append(f'  {_node(step.id)} -> {_node(step.otherwise)} [label=" no"];')
        elif step.type in ("exit", "cta") or position == len(ids) - 1:
            continue  # a task waits for a person; an exit ends the journey
        else:
            lines.append(f"  {_node(step.id)} -> {_node(ids[position + 1])};")
    if journey.goal:
        goal = _goal_text(journey.goal, signal_names)
        lines.append(f'  goal [label="Goal reached: {goal}\\nthe journey ends at once" '
                     'shape=ellipse fillcolor="#d7f5df"];')  # fmt: skip
        lines.append("  entry -> goal [style=invis];")
    lines.append("}")
    return "\n".join(lines)


def _attributes(step, queues: dict, counts: dict, signal_names: dict) -> str:
    reached = counts.get(step.id)
    tail = f"\\n{reached} reached it" if reached is not None and step.tier else ""
    if step.type == "email":
        label = f"Email\\n{_words(step.template)}"
        if step.approval:
            label += f"\\nwaits for approval by the {queues[step.approval]['name']}"
    elif step.type == "in_app":
        label = f"Message in the product\\n{_words(step.template)}"
    elif step.type == "agent":
        label = "AI agent\\nanswers, or hands off to a person"
    elif step.type == "wait":
        label = f"Wait {step.days} days"
    elif step.type == "branch":
        label = _wrap(f"{_condition(step.condition, signal_names)}?", 18)
        return f'label="{label}" shape=diamond fillcolor="#ffffff" fontsize=10'
    elif step.type == "cta":
        label = f"Task for a person\\n{queues[step.queue]['name']}\\n{_wrap(step.title)}"
    else:  # exit
        label = f"End\\n{_words(step.reason or '')}"
        return f'label="{label}" shape=ellipse fillcolor="#f4f4f4"'
    colour = TIER_COLOURS.get(step.tier or "", NEUTRAL)
    return f'label="{label}{tail}" fillcolor="{colour}"'


def _audience(play) -> str:
    parts = []
    stages = (play.audience or {}).get("lifecycle")
    if stages:
        parts.append("stages: " + ", ".join(_words(stage) for stage in stages))
    parts.append(f"{len(play.exclusions)} rules keep customers out")
    return "; ".join(parts)


def _condition(condition: str, signal_names: dict) -> str:
    if condition.startswith("signal:"):
        signal = condition.removeprefix("signal:")
        return "Still: " + signal_names.get(signal, _words(signal)).lower()
    return {"negative_sentiment": "Unhappy or in trouble", "contact_replied": "Replied"}.get(
        condition, _words(condition)
    )


def _goal_text(goal: dict, signal_names: dict) -> str:
    if goal["metric"] == "signal_cleared":
        return f"{signal_names.get(goal['signal'], goal['signal']).lower()} no longer fires"
    plain = {
        "prerequisite_closure_pct": f"{goal['at_least']:.0%} of setup steps done",
        "docs_published_30d": "a first document published",
        "has_valid_admin": "an admin who may be emailed",
    }
    return plain.get(goal["metric"], f"{_words(goal['metric'])} at least {goal['at_least']}")


def _words(code: str) -> str:
    return code.replace("_", " ")


def _wrap(text: str, width: int = 28) -> str:
    """Break a long label over lines, so boxes stay narrow."""
    lines, line = [], ""
    for word in text.replace('"', "'").split():
        if line and len(line) + len(word) + 1 > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    lines.append(line)
    return "\\n".join(lines)


def _node(step_id: str) -> str:
    return f"step_{step_id}"

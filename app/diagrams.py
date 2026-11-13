"""Draw the diagrams in the docs inside the app. Synthetic data, fictional company.

The documents keep their diagrams as Mermaid text, because that is what the code host
draws. Streamlit does not draw Mermaid, and loading a drawing library from the internet
would break the offline demo. Streamlit does draw Graphviz, with no network. So this
file translates the small part of Mermaid the documents use (boxes, groups, arrows with
labels) into Graphviz.

Supported, and nothing more:
    flowchart LR                      direction (LR, or TD / TB)
    subgraph Id["Group name"] ... end
    Id["Box text<br/>second line"]
    A --> B                           an arrow
    A -.->|label| B                   a dashed arrow with a label
    A & B --> C --> D                 several boxes at once, and chains
"""

from __future__ import annotations

import re

import streamlit as st

ARROW = re.compile(r"\s*(-\.->|-->)(?:\|([^|]*)\|)?\s*")
NODE = re.compile(r'^(\w+)(?:\["(.*)"\])?$')
GROUP = re.compile(r'^subgraph\s+(\w+)(?:\["(.*)"\])?$')
BLOCK = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)


def mermaid_to_dot(source: str) -> str:
    """Translate one Mermaid flowchart into Graphviz DOT text."""
    direction = "LR"
    labels: dict[str, str] = {}  # box id -> text
    groups: dict[str, dict] = {}  # group id -> {"label": ..., "boxes": [...]}
    edges: list[tuple[str, str, bool, str | None]] = []  # from, to, dashed, label
    current_group = None

    def box(text: str) -> str:
        """Register one box (its label and its group) and return its id."""
        match = NODE.match(text.strip())
        if not match:
            raise ValueError(f"cannot read this part of the diagram: {text!r}")
        box_id, label = match.groups()
        if label is not None:
            labels[box_id] = label
        labels.setdefault(box_id, box_id)
        already_grouped = any(box_id in group["boxes"] for group in groups.values())
        if current_group and not already_grouped:
            groups[current_group]["boxes"].append(box_id)
        return box_id

    for raw in source.strip().splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("flowchart", "graph")):
            direction = "LR" if line.split()[-1] == "LR" else "TB"
        elif GROUP.match(line):
            current_group, label = GROUP.match(line).groups()
            groups[current_group] = {"label": label or current_group, "boxes": []}
        elif line == "end":
            current_group = None
        else:
            # "A & B -->|label| C --> D" splits into: boxes, arrow, label, boxes, ...
            parts = ARROW.split(line)
            sides = [[box(item) for item in part.split("&")] for part in parts[0::3]]
            for index in range(len(sides) - 1):
                arrow, label = parts[index * 3 + 1], parts[index * 3 + 2]
                for start in sides[index]:
                    for end in sides[index + 1]:
                        edges.append((start, end, arrow == "-.->", label))

    # Every piece of text sits on its own light background (a filled group, a filled box,
    # a label on a white patch), so the drawing reads on a light page and on a dark one.
    lines = [
        "digraph {",
        f"  rankdir={direction};",
        '  bgcolor="transparent";',
        '  node [shape=box, style="rounded,filled", fillcolor="white", color="#8c96a8",'
        ' fontname="Helvetica", fontsize=11, fontcolor="#1f2733"];',
        '  edge [color="#7a8699", fontname="Helvetica", fontsize=10, fontcolor="#1f2733"];',
    ]
    for group_id, group in groups.items():
        lines.append(f"  subgraph cluster_{group_id} {{")
        lines.append(f'    label="{_text(group["label"])}"; style="rounded,filled";')
        lines.append('    fillcolor="#e9edf4"; color="#b8c0cc";')
        lines.append('    fontname="Helvetica"; fontsize=11; fontcolor="#1f2733";')
        lines += [f"    {box_id};" for box_id in group["boxes"]]
        lines.append("  }")
    lines += [f'  {box_id} [label="{_text(label)}"];' for box_id, label in labels.items()]
    for start, end, dashed, label in edges:
        details = (["style=dashed"] if dashed else []) + ([_patch(label)] if label else [])
        lines.append(f"  {start} -> {end}" + (f" [{', '.join(details)}]" if details else "") + ";")
    lines.append("}")
    return "\n".join(lines)


def _patch(label: str) -> str:
    """An arrow's label on a small white patch (written in Graphviz's table notation)."""
    safe = label.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    cell = f'<table border="0" cellborder="0" bgcolor="white"><tr><td>{safe}</td></tr></table>'
    return f"label=<{cell}>"


def _text(label: str) -> str:
    """A label as Graphviz wants it: line breaks as \\n, quotes escaped."""
    return label.replace('"', '\\"').replace("<br/>", "\\n").replace("<br>", "\\n")


def show_markdown(text: str) -> None:
    """Show a document. Mermaid blocks are drawn; everything else is ordinary markdown."""
    parts = BLOCK.split(text.replace("\r\n", "\n"))
    for index, part in enumerate(parts):
        if index % 2 == 0:
            if part.strip():
                st.markdown(part)
            continue
        show_diagram(part)


def show_diagram(source: str) -> None:
    """Draw one Mermaid flowchart (the documents' diagrams, and the guided tour's picture)."""
    try:
        st.graphviz_chart(mermaid_to_dot(source), use_container_width=True)
    except ValueError:  # a kind of diagram this translator does not know: show the text
        st.code(source, language="text")

"""Operating model: the documents that make this a programme, not a script. Synthetic data."""

import streamlit as st

from common.paths import ROOT

st.title("Operating model")
st.write(
    "Who owns what, how changes are made, how a handoff works, and why each design decision was taken."
)

DOCS = ROOT / "docs"
GROUPS = {
    "How it runs": [
        "human-fallback.md",
        "principles.md",
        "ownership-map.md",
        "change-control.md",
        "dependency-map.md",
        "pilot-plan.md",
    ],
    "What it is": ["prd.md", "roadmap.md", "metrics.md", "data-requirements.md"],
    "Evidence": ["eda-report.md", "phase-notes.md"],
}
group = st.radio(
    "Section", [*GROUPS, "Play specs", "Decisions (ADRs)", "Model cards"], horizontal=True
)
if group in GROUPS:
    files = [DOCS / name for name in GROUPS[group] if (DOCS / name).exists()]
elif group == "Play specs":
    files = sorted((DOCS / "play-specs").glob("*.md"))
elif group == "Decisions (ADRs)":
    files = sorted((DOCS / "decisions").glob("*.md"))
else:
    files = sorted((DOCS / "model-cards").glob("*.md"))

if not files:
    st.info("Nothing here yet.")
    st.stop()


def title_of(path) -> str:
    first = path.read_text(encoding="utf-8").splitlines()[0]
    return first.lstrip("# ").strip() or path.stem


chosen = st.selectbox("Document", files, format_func=title_of)
st.caption(f"`{chosen.relative_to(ROOT).as_posix()}`")
st.markdown(chosen.read_text(encoding="utf-8"))

"""Data quality: what the pipeline caught before anything acted on it. Synthetic data."""

import streamlit as st

from app import ui

st.title("Data quality")
ui.job_intro("quality")

tests = ui.query("SELECT * FROM gold.dq_test_results")
contract = ui.query("SELECT * FROM gold.dq_contract_checks")
freshness = ui.query("SELECT * FROM gold.dq_freshness")
passed = int((tests["status"] == "pass").sum())
one, two, three = st.columns(3)
ui.metric(one, "Data tests passing", f"{passed} of {len(tests)}")
ok = int(contract["passed"].sum())
ui.metric(two, "Contract checks passing", f"{ok} of {len(contract)}")
ui.metric(three, "Sources checked for freshness", len(freshness))
# One short line under each number, in its own column.
one.caption(
    "Automated checks that a table must pass before any play may use it. For example, "
    "no customer appears twice, no record is missing its identifier, and every value is "
    "in its expected range."
)
two.caption("The contract is the written list of what the main table promises to contain.")
three.caption("Freshness means that each source delivered its data on time.")

st.subheader("What the pipeline caught")
st.caption(
    "This demo plants known problems in its own data, and records what it planted, so that "
    "the checks can be shown to catch every one."
)
st.dataframe(ui.query("SELECT * FROM gold.dq_summary"), hide_index=True, width="stretch")

left, right = st.columns(2)
with left:
    st.subheader("Rejected at ingest, by reason")
    rejected = ui.query(
        "SELECT reason, count(*) AS rows FROM bronze.dead_letter GROUP BY reason ORDER BY rows DESC"
    )
    st.bar_chart(rejected, x="reason", y="rows", horizontal=True)
    st.caption(
        "A rejected record is kept in a separate table, with the reason it was rejected. "
        "Nothing is silently discarded."
    )
with right:
    st.subheader("Freshness")
    st.dataframe(freshness, hide_index=True, width="stretch")
    st.subheader("Data contract: gold.account_daily")
    st.dataframe(contract, hide_index=True, width="stretch", height=240)

st.subheader("Data tests")
failing = tests[tests["status"] != "pass"]
if len(failing):
    st.error(f"{len(failing)} tests are failing.")
    st.dataframe(failing, hide_index=True, width="stretch")
with st.expander(f"All {len(tests)} tests"):
    st.dataframe(tests, hide_index=True, width="stretch")

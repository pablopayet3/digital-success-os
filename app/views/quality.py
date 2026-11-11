"""Data quality: what the pipeline caught before anything acted on it. Synthetic data."""

import streamlit as st

from app import ui

st.title("Data quality")
st.write(
    "Plays act on data, so the data has to be checked first. Bad rows are rejected at the "
    "door with a reason, the tables are tested on every run, and the production table has "
    "a written contract that code checks."
)

tests = ui.query("SELECT * FROM gold.dq_test_results")
contract = ui.query("SELECT * FROM gold.dq_contract_checks")
freshness = ui.query("SELECT * FROM gold.dq_freshness")
passed = int((tests["status"] == "pass").sum())
one, two, three = st.columns(3)
one.metric("Data tests passing", f"{passed} of {len(tests)}")
ok = int(contract["passed"].sum())
two.metric("Contract checks passing", f"{ok} of {len(contract)}")
three.metric("Sources checked for freshness", len(freshness))

st.subheader("What the pipeline caught")
st.caption(
    "The generator injects these problems on purpose, and records what it injected, so tests can prove they were caught."
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
        "Rejected rows are kept in a dead-letter table with the reason. Nothing is silently dropped."
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

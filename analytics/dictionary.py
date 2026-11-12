"""The data dictionary: every silver and gold table, every column, in one document.

Synthetic data, fictional company.

Run with:  uv run python run.py docs     (writes docs/data-dictionary.md)

The document itself is never typed by hand. The list of columns and their types comes
from the warehouse, so a column nobody documented still shows up, marked as such. Its
meaning is looked up in this order, and the first one found is used:

  1. the description next to the model in its dbt file (where the tests are too);
  2. the data contract, for columns of the production table and columns that keep the
     same name in the tables built from it;
  3. the column glossary (dbt/column_glossary.yml): this table's own entry, then the
     shared one.

A test fails when a column has no meaning anywhere.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from common.paths import DATA_DIR, ROOT
from common.warehouse import open_warehouse

DICTIONARY_PATH = ROOT / "docs" / "data-dictionary.md"
# layer name -> (warehouse schema, the dbt file that documents its models)
LAYERS = {
    "Silver: clean, typed, de-duplicated": ("silver", "dbt/models/staging/_staging.yml"),
    "Gold: ready to use": ("gold", "dbt/models/marts/_marts.yml"),
}
CONTRACT = ROOT / "contracts" / "account_daily.yaml"
GLOSSARY = ROOT / "dbt" / "column_glossary.yml"
NOT_DOCUMENTED = "(not documented)"


def write_data_dictionary(data_dir: Path = DATA_DIR, path: Path = DICTIONARY_PATH) -> Path:
    path.write_text(render(data_dir), encoding="utf-8", newline="\n")
    return path


def render(data_dir: Path = DATA_DIR) -> str:
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    contract_columns = {column["name"]: column["description"] for column in contract["columns"]}
    glossary = yaml.safe_load(GLOSSARY.read_text(encoding="utf-8"))
    warehouse = open_warehouse(data_dir)
    lines = [
        "# Data dictionary",
        "",
        "Synthetic data, fictional company. Written by `uv run python run.py docs` from the "
        "dbt model files, the data contract and the warehouse. Nothing here is typed by hand.",
        "",
        "Bronze is not listed: it is the raw files as they arrived, loaded without change "
        "(`ingest/load.py`). Metric definitions are in `docs/metrics.md`.",
    ]
    try:
        for layer, (schema, model_file) in LAYERS.items():
            lines += ["", f"## {layer}"]
            models = yaml.safe_load((ROOT / model_file).read_text(encoding="utf-8"))["models"]
            for model in models:
                columns = warehouse_columns(warehouse, schema, model["name"])
                if not columns:  # declared in dbt, not built in this warehouse
                    continue
                described = {column["name"]: column for column in model.get("columns", [])}
                # Where the dbt file is silent, fall back to the contract, then the glossary.
                fallback = (
                    glossary["shared"]
                    | contract_columns
                    | glossary["by_table"].get(model["name"], {})
                )
                lines += table_section(schema, model, columns, described, fallback)
    finally:
        warehouse.close()
    return "\n".join(lines) + "\n"


def warehouse_columns(warehouse, schema: str, table: str) -> list[tuple[str, str]]:
    """The columns the table really has, in order, with their types."""
    found = warehouse.query(
        "SELECT column_name, data_type FROM information_schema.columns "
        f"WHERE table_schema = '{schema}' AND table_name = '{table}' ORDER BY ordinal_position"
    )
    return list(zip(found["column_name"], found["data_type"], strict=True))


def table_section(schema: str, model: dict, columns, described: dict, fallback: dict) -> list[str]:
    description = " ".join((model.get("description") or "No description yet.").split())
    lines = [
        "",
        f"### {schema}.{model['name']}",
        "",
        description,
        "",
        "| Column | Type | What it means | Tested for |",
        "|---|---|---|---|",
    ]
    for name, data_type in columns:
        column = described.get(name, {})
        meaning = column.get("description") or fallback.get(name) or NOT_DOCUMENTED
        meaning = " ".join(str(meaning).split())
        tests = ", ".join(test_names(column.get("data_tests", []))) or ""
        lines.append(f"| `{name}` | {data_type.lower()} | {meaning} | {tests} |")
    return lines


def test_names(tests: list) -> list[str]:
    """dbt writes a test as a name, or as a one-key dictionary with its settings."""
    return [test if isinstance(test, str) else next(iter(test)) for test in tests]

"""The "Ask the data" assistant: Claude answers questions about the data and the program.

Synthetic data, fictional company. See ADR 0028 and config/assistant.yaml.

A question comes in (typed on the page, clicked as an example, or spoken to the voice).
Claude answers it with three read-only tools:

    run_sql          one SELECT on the warehouse, gold and silver schemas only
    describe_tables  the tables and what each column means (docs/data-dictionary.md)
    search_docs      the program's documents and the help center articles

Every call to the model goes through agents/llm.py, so the cache, the offline mode, the
call limit and the shared budget apply here too. The answer loop takes at most a few
rounds of tool use, then must answer.

The assistant never reads data/ground_truth: the SQL guard refuses it, and that folder is
not a table in the warehouse anyway.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from rank_bm25 import BM25Okapi

from agents.llm import LLM, LLMUnavailable, get_llm
from agents.retrieval import tokens
from common.config import load_yaml
from common.paths import DATA_DIR, ROOT
from common.warehouse import open_warehouse

EXAMPLES_FILE = ROOT / "app" / "assistant_examples.json"
PROMPT_FILE = ROOT / "prompts" / "assistant.md"

# Real platforms are named only in the few documents the project guide lists. A passage
# that names one is left out of the search, so the assistant cannot repeat it.
REAL_NAMES = re.compile(
    r"databricks|salesforce|gainsight|tableau|atlassian|jira|confluence|render\.com|"
    r"langsmith|zendesk|hubspot|notion|mixpanel|intercom|snowflake|github",
    re.IGNORECASE,
)
# Documents searched. Those that name real platforms or describe the build are left out.
DOC_FOLDERS = ["docs", "docs/play-specs", "docs/decisions", "docs/model-cards", "kb"]
DOCS_LEFT_OUT = {
    "production-architecture.md",
    "demo-script.md",
    "bi-dashboard-guide.md",
    "portfolio-entry.md",
    "phase-notes.md",
    "reviewer-guide.md",
    "data-dictionary.md",  # served by describe_tables instead
}


def settings() -> dict:
    return load_yaml("assistant.yaml")


# --- the SQL guard -------------------------------------------------------------------------

FORBIDDEN_WORDS = (
    "insert update delete drop create alter attach detach copy pragma install load call "
    "export import set grant revoke truncate merge vacuum checkpoint use"
).split()
FORBIDDEN_FUNCTIONS = re.compile(
    r"\b(read_\w+|glob|sniff_csv|parquet_scan|csv_scan|json_scan|query_table|getenv|"
    r"current_setting)\s*\(",
    re.IGNORECASE,
)
OTHER_SCHEMAS = re.compile(
    r"\b(bronze|main|information_schema|pg_catalog|system|temp|duckdb_\w+)\s*\.", re.IGNORECASE
)


# A quoted text that looks like a file or a path, wherever it appears (FROM a, 'b.csv').
FILE_LIKE = re.compile(
    r"'[^']*(\.(csv|tsv|parquet|json|jsonl|ndjson|txt|env|db|duckdb|sqlite|xlsx|gz|zst)"
    r"|[/\\])[^']*'",
    re.IGNORECASE,
)


class UnsafeSQL(ValueError):
    """The statement is not one read-only SELECT on the gold or silver schemas."""


def check_sql(sql: str) -> str:
    """Return the statement if it is safe to run, or raise UnsafeSQL with the reason."""
    statement = sql.strip().rstrip(";").strip()
    lowered = statement.lower()
    if not statement:
        raise UnsafeSQL("The statement is empty.")
    if ";" in statement:
        raise UnsafeSQL("Only one statement may be run at a time.")
    if "--" in statement or "/*" in statement:
        raise UnsafeSQL("Comments are not allowed in the statement.")
    if not re.match(r"^(select|with)\b", lowered):
        raise UnsafeSQL("Only a SELECT statement (or WITH ... SELECT) may be run.")
    words = set(re.findall(r"[a-z_]+", lowered))
    used = sorted(words & set(FORBIDDEN_WORDS))
    if used:
        raise UnsafeSQL(f"The statement uses a word that could change data: {used[0]}.")
    if "ground_truth" in lowered:
        raise UnsafeSQL("The answer key (ground truth) may never be read.")
    if FORBIDDEN_FUNCTIONS.search(statement):
        raise UnsafeSQL("Reading files or settings is not allowed.")
    # DuckDB reads a file named in quotes in place of a table (FROM 'some/file.csv'), and a
    # quoted name ("bronze"."x") would slip past the schema check below. Neither is needed.
    if '"' in statement or "`" in statement:
        raise UnsafeSQL("Quoted names are not allowed; write gold.table_name.")
    if re.search(r"\b(?:from|join)\s*'", statement, re.I) or FILE_LIKE.search(statement):
        raise UnsafeSQL("Reading files is not allowed.")
    if OTHER_SCHEMAS.search(statement):
        raise UnsafeSQL("Only the gold and silver schemas may be read.")
    # Every table after FROM or JOIN must be in gold or silver, or be a name defined in WITH.
    defined = {name.lower() for name in re.findall(r"(\w+)\s+as\s*\(", statement, re.I)}
    for name in re.findall(r"\b(?:from|join)\s+([A-Za-z_][\w.]*)", statement, re.I):
        lowered_name = name.lower()
        if lowered_name in defined:
            continue
        if not re.match(r"^(gold|silver)\.\w+$", lowered_name):
            raise UnsafeSQL(f"Only tables in the gold and silver schemas may be read: {name}.")
    return statement


def run_sql(sql: str, data_dir: Path = DATA_DIR) -> str:
    """Run one checked SELECT and return at most the configured number of rows, as text."""
    config = settings()
    statement = check_sql(sql)
    limit = int(config["sql_row_limit"])
    wrapped = f"SELECT * FROM ({statement}) AS answer LIMIT {limit}"
    warehouse = open_warehouse(data_dir)
    try:
        frame = warehouse.query(wrapped)
    finally:
        warehouse.close()
    if frame.empty:
        return "The query returned no rows."
    text = frame.to_csv(index=False)
    return _clip(f"{len(frame)} rows (at most {limit} are returned).\n{text}")


# --- describing the tables -------------------------------------------------------------------


@lru_cache(maxsize=1)
def table_sections() -> dict[str, str]:
    """Each table's section of docs/data-dictionary.md, by its full name (gold.signals)."""
    text = (ROOT / "docs" / "data-dictionary.md").read_text(encoding="utf-8")
    sections: dict[str, str] = {}
    for block in text.split("\n### ")[1:]:
        name, _, body = block.partition("\n")
        sections[name.strip()] = body.strip()
    return sections


def describe_tables(table: str | None = None) -> str:
    """With no table: every table and its one-line purpose. With a table: its columns."""
    sections = table_sections()
    extra = {
        "gold.experiment_results": "Each play's result against its holdout (written by "
        "experiments/analyze.py): lift, interval, verdict, revenue columns.",
        "gold.dq_test_results": "The outcome of each data test in the last pipeline runs.",
        "gold.dq_freshness": "Whether each data source arrived on time.",
        "gold.dq_contract_checks": "Each promise of the data contract and whether it held.",
    }
    if not table:
        lines = [f"{name}: {body.splitlines()[0]}" for name, body in sections.items()]
        lines += [f"{name}: {meaning}" for name, meaning in extra.items()]
        return _clip("\n".join(lines))
    name = table.strip().lower()
    if name in sections:
        return _clip(sections[name])
    if name in extra:
        return extra[name] + " Run SELECT * FROM " + name + " LIMIT 5 to see its columns."
    return f"There is no table called {table}. Call describe_tables with no table for the list."


# --- searching the documents -----------------------------------------------------------------


@dataclass
class Passage:
    source: str  # the file, relative to the project
    heading: str
    text: str


@dataclass
class DocsIndex:
    passages: list[Passage] = field(default_factory=list)

    def __post_init__(self):
        for folder in DOC_FOLDERS:
            for path in sorted((ROOT / folder).glob("*.md")):
                if path.name in DOCS_LEFT_OUT:
                    continue
                self._add(path)
        corpus = [tokens(f"{p.heading} {p.heading} {p.text}") for p in self.passages]
        self.index = BM25Okapi(corpus)

    def _add(self, path: Path) -> None:
        text = path.read_text(encoding="utf-8")
        title = text.splitlines()[0].removeprefix("# ").strip() if text else path.stem
        source = path.relative_to(ROOT).as_posix()
        for chunk in re.split(r"\n(?=## )", text):
            heading = chunk.splitlines()[0].lstrip("# ").strip() if chunk.strip() else title
            if REAL_NAMES.search(chunk):
                continue
            self.passages.append(Passage(source, f"{title}: {heading}", chunk.strip()[:2500]))

    def search(self, query: str, top_k: int = 4) -> list[Passage]:
        scores = self.index.get_scores(tokens(query))
        ranked = sorted(zip(scores, self.passages, strict=True), key=lambda pair: -pair[0])
        return [passage for score, passage in ranked[:top_k] if score > 0]


@lru_cache(maxsize=1)
def docs_index() -> DocsIndex:
    return DocsIndex()


def search_docs(query: str) -> str:
    found = docs_index().search(query)
    if not found:
        return "No document matches that search."
    return _clip("\n\n".join(f"[{p.source}] {p.heading}\n{p.text}" for p in found))


# --- the answer loop ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "run_sql",
        "description": (
            "Run one read-only SELECT statement on the warehouse and return the rows as CSV. "
            "Only tables in the gold and silver schemas may be read, for example "
            "gold.account_current. At most 50 rows come back, so aggregate in SQL."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"sql": {"type": "string", "description": "One SELECT statement."}},
            "required": ["sql"],
            "additionalProperties": False,
        },
    },
    {
        "name": "describe_tables",
        "description": (
            "With no table: list every table in the warehouse with its purpose. With a table "
            "name such as gold.account_current: its columns, their types and their meanings."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"table": {"type": "string", "description": "schema.table, optional"}},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_docs",
        "description": (
            "Search the program's documents (metrics definitions, play specifications, "
            "decision records, the ownership map, the pilot plan, the human fallback rules) "
            "and the help center articles. Returns the best passages with their file names."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "What to look for."}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
]


@dataclass
class Answer:
    question: str
    text: str
    model: str = ""
    stored: bool = False  # True when the answer was written earlier and read from a file
    sql: list[str] = field(default_factory=list)  # the statements Claude ran
    documents: list[str] = field(default_factory=list)  # the documents it read
    cost_usd: float = 0.0
    available: bool = True  # False when no model could answer

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "answer": self.text,
            "model": self.model,
            "stored": self.stored,
            "sql": self.sql,
            "documents": self.documents,
            "available": self.available,
        }


def system_prompt(data_dir: Path = DATA_DIR) -> str:
    template = PROMPT_FILE.read_text(encoding="utf-8")
    try:
        warehouse = open_warehouse(data_dir)
        try:
            today = warehouse.query("SELECT max(snapshot_date) AS d FROM gold.account_current")
        finally:
            warehouse.close()
        today_text = str(today["d"][0])[:10]
    except Exception:
        today_text = "unknown"
    return template.format(
        row_limit=settings()["sql_row_limit"], today=today_text, names=plain_names()
    )


def plain_names() -> str:
    """The official plain names of the plays, signals and queues, so answers never show codes."""
    from engine.catalog import load_catalog  # imported here: agents depends on engine

    catalog = load_catalog()
    plays = [f"{play.id} = {play.name}" for play in catalog.plays]
    signals = [f"{s['id']} = {s['name']}" for s in load_yaml("job.yaml")["signals"]]
    queues = [f"{key} = {queue['name']}" for key, queue in catalog.routing["queues"].items()]
    lines = [
        "Plays: " + "; ".join(plays) + ".",
        "Signals: " + "; ".join(signals) + ".",
        "Queues (teams): " + "; ".join(queues) + ".",
    ]
    return "\n".join(lines)


def run_tool(name: str, arguments: dict, data_dir: Path, answer: Answer) -> str:
    """Run one tool for Claude. A tool error is returned as text, so Claude can correct it."""
    try:
        if name == "run_sql":
            answer.sql.append(arguments.get("sql", ""))
            return run_sql(arguments.get("sql", ""), data_dir)
        if name == "describe_tables":
            return describe_tables(arguments.get("table"))
        if name == "search_docs":
            result = search_docs(arguments.get("query", ""))
            for source in re.findall(r"^\[([^\]]+)\]", result, re.MULTILINE):
                if source not in answer.documents:
                    answer.documents.append(source)
            return result
        return f"There is no tool called {name}."
    except UnsafeSQL as refusal:
        return f"Refused: {refusal}"
    except Exception as error:  # a bad column name, for example: let Claude fix the query
        return f"The tool failed: {type(error).__name__}: {str(error)[:400]}"


def ask(
    question: str, data_dir: Path = DATA_DIR, llm: LLM | None = None, use_stored: bool = True
) -> Answer:
    """Answer one question: a stored answer for an example, otherwise Claude."""
    question = question.strip()[:500]
    stored = stored_answer(question) if use_stored else None
    if stored:
        return stored
    llm = llm or get_llm()
    answer = Answer(question=question, text="")
    system = system_prompt(data_dir)
    messages: list[dict] = [{"role": "user", "content": question}]
    rounds = int(settings()["max_tool_rounds"])
    try:
        for round_number in range(rounds + 1):
            # On the last round no tools are offered, so Claude must answer.
            tools = TOOLS if round_number < rounds else None
            response = llm.call("assistant", system, messages, tools=tools, purpose="assistant")
            answer.model = response.model
            answer.cost_usd += response.cost_usd
            if not response.tool_calls:
                answer.text = response.text or "No answer was written."
                return answer
            messages.append({"role": "assistant", "content": response.content})
            results = [
                {
                    "type": "tool_result",
                    "tool_use_id": call["id"],
                    "content": run_tool(call["name"], call["input"], data_dir, answer),
                }
                for call in response.tool_calls
            ]
            messages.append({"role": "user", "content": results})
    except LLMUnavailable:
        answer.available = False
        answer.text = (
            "No AI model can answer typed questions here right now, so only the example "
            "questions above have answers. On the hosted demo, the real model answers when "
            "its host has provided a key and the spending limit has not been reached."
        )
    return answer


# --- the stored answers of the example questions -----------------------------------------------


def examples() -> dict[str, list[str]]:
    """The example questions, by team (config/assistant.yaml)."""
    return settings()["examples"]


@lru_cache(maxsize=1)
def _stored() -> dict[str, dict]:
    if not EXAMPLES_FILE.exists():
        return {}
    items = json.loads(EXAMPLES_FILE.read_text(encoding="utf-8"))["answers"]
    return {_normal(item["question"]): item for item in items}


def stored_answer(question: str) -> Answer | None:
    item = _stored().get(_normal(question))
    if item is None:
        return None
    return Answer(
        question=item["question"],
        text=item["answer"],
        model=item.get("model", ""),
        stored=True,
        sql=item.get("sql", []),
        documents=item.get("documents", []),
    )


def _normal(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def _clip(text: str) -> str:
    limit = int(settings()["max_tool_output_chars"])
    return text if len(text) <= limit else text[:limit] + "\n[... cut: the result was too long]"

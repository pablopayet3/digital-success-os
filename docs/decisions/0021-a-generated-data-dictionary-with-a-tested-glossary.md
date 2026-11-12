# 0021: A generated data dictionary, with a glossary that a test keeps complete

Status: accepted. Synthetic data, fictional company.

## Context

The role asks for "requirements for clean data" and "tables, schemas, tagging". The
requirements are in `docs/data-requirements.md` and the production table has a contract.
What was missing is the plain reference a CSM, an analyst or an agent engineer opens to
ask "what does this column mean?". When the first version was generated, 454 of 533
columns in silver and gold had no written meaning.

## Options

1. Write the dictionary by hand. It is out of date the first time a column is added.
2. Rely on dbt's own documentation site. Complete and well made, but it has to be built
   and served, it cannot be read on the code host, and it showed the same 454 gaps.
3. **Generate one Markdown document from what already exists, fill the gaps in one
   glossary file, and make a test fail when a column has no meaning.**

## Decision

Option 3. `uv run python run.py docs` writes `docs/data-dictionary.md`
(`analytics/dictionary.py`). The columns and their types come from the warehouse, so
nothing can be left out. The meaning of a column is the first one found in:

1. the description next to the model in its dbt file, where its tests are;
2. the data contract, for the production table and columns that keep the same name;
3. `dbt/column_glossary.yml`: an entry for that table, then a shared entry by name.

Two tests guard it. One fails when any column has no meaning. The other fails when the
committed document lists different tables or columns from the warehouse, so a column
added without regenerating the document is caught. The same command also builds dbt's
own site (option 2) for anyone who wants the lineage graph.

## Consequences

- One definition per column name by default; a table overrides it only when the same
  name means something different there (`status`, `source`, `outcome`).
- The glossary sits outside dbt's model folder, so dbt does not read it. Moving the
  definitions into each model's file would be more standard and many times longer.
- The dictionary covers silver and gold. Bronze is the raw files, unchanged.

## Revisit if

The warehouse moves to a platform with its own catalogue (definitions then belong in
table and column comments there), or two teams need different definitions of one name.

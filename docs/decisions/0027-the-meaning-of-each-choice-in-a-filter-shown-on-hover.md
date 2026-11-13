# 0027: The meaning of each choice in a filter, shown when the pointer rests on it

Status: accepted (13 November 2026, after the phases; the owner's request of that day).
Synthetic data, fictional company.

## Context

Every number in the app has its definition as a hover text (`config/glossary.yaml`). The
filters did not. Their choices are the system's own names, such as `pooled`, `at_risk` or
`yellow`, and a visitor had to guess what each one means. The owner asked for a definition
on each choice when the pointer is on it.

The page library gives a hover text to a whole filter (the question mark beside its
label). It has none for one choice of the list.

## Options

1. **Write the meaning inside each choice** ("pooled: a shared team of success
   managers"). No script. A picked choice then becomes a long tag that does not fit in a
   filter one third of the page wide.
2. **Only the filter's question mark**, listing every choice. The library supports it and
   it works without a pointer. The visitor has to leave the list to read it.
3. **A short script** that shows a small window beside the choice under the pointer. This
   is what was asked. It depends on how the library draws a list, which a new version of
   the library may change.
4. **A filter component of our own.** Far more code than the problem deserves.

## Decision

Options 3 and 2 together, from one source of words.

- `config/options.yaml` holds one block per filter, named as the filter is labelled on
  screen, with one meaning per choice.
- `app/option_hints.html` is the script. `ui.option_hints()` puts it on every page (it is
  called in `app/main.py`). It listens for the pointer once for the whole page, reads the
  words of the choice under it, and shows the meaning in a small window beside it. It
  covers a choice in an open list and a choice already picked.
- `ui.choices_help(label)` writes the same words on the filter's question mark, one line
  per choice. That serves a visitor who does not use a pointer, and it still works if the
  script stops matching.
- `ui.choices_table(label)` shows the same words as a small table. The Overview uses it
  for the coverage tiers, which were one long sentence before.
- **Covered:** Coverage tier, Lifecycle stage and Health band on the Accounts page; Role
  and Outcome on the Human console. Lists of accounts, tasks, plays and documents are not
  lists of terms, so they have no entry.

## Consequences

- The same words appear in three places and are written once.
- The Outcome list used to show `resolved: journey will re_enter_journey`. It now shows
  the name of the outcome, and its meaning in plain words on hover and on the question
  mark.
- Tests check the words, not the pointer: every choice a covered filter offers has a
  meaning and the filter has its question mark; the outcomes are the ones in
  `config/routing.yaml`; the health bands use the thresholds in `config/health.yaml`; and
  the script on the page is given every meaning. The small window itself was checked by
  hand in a browser, on a choice in an open list and on a picked choice.
- A new filter of terms needs a block in `config/options.yaml` and
  `help=ui.choices_help(...)`.

## Revisit if

The page library gains a hover text for each choice. Use it and delete the script.

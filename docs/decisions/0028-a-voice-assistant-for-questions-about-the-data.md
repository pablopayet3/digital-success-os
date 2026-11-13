# 0028: A voice assistant for questions about the data

Status: accepted (13 November 2026, after the phases; the owner's request of that day).
Synthetic data, fictional company.

## Context

The teams that use this system ask the same kinds of question every week. CS Leadership
asks which customers are at risk, the Sales team asks who is running out of seats, and the
Data Engineering team asks whether a test failed. Each page answers some of them, but a
visitor has to know which page to open and how to read it. The owner asked for an
assistant that answers any such question, typed or spoken, with example questions to
click, and a voice of the same quality as the owner's other applications.

Those applications use a live speech-to-speech session between the browser and the voice
service: the voice is heard while it is produced, and a person can interrupt it. The
owner asked for Claude to find the answers.

## Options

1. **Text only.** Claude answers typed questions on a page. Simple, and no second paid
   service. It does not meet the request for a voice.
2. **Record and play.** The browser records a question, a service turns it into text,
   Claude answers, and a second service reads the answer aloud. Every answer waits for the
   whole chain, and nobody can interrupt.
3. **A live voice session that hands each question to Claude.** The voice service listens
   and speaks; a function the session can call (`ask_claude`) sends the question to this
   project's API, where Claude answers from the data. This is how the owner's applications
   work, with Claude added as the source of every answer.
4. **The voice service answers by itself.** Fastest, but its answers would not come from
   the data, and it is not the model the owner chose.

## Decision

Option 3, on a new page, "Ask the data" (`app/views/ask.py`).

- **Claude answers** (`agents/assistant.py`, role `assistant` in `config/llm.yaml`). It has
  three read-only tools: one SELECT at a time on the gold and silver schemas, the column
  definitions from `docs/data-dictionary.md`, and a search of the program's documents. A
  guard refuses anything else: writes, several statements, other schemas, file reads and
  the answer key (`data/ground_truth`). At most 50 rows come back, and at most six rounds
  of tool use are allowed. The instructions are in `prompts/assistant.md`.
- **Every call goes through `agents/llm.py`**, so the cache, the offline mode, the call
  limit and the public demo's 5-dollar budget apply, in the same total as the onboarding
  agent.
- **The example questions** (two for each of seven teams, in `config/assistant.yaml`)
  have answers that Claude wrote once from the same small world the hosted image builds
  (`scripts/assistant_examples.py`, stored in `app/assistant_examples.json`). They cost
  nothing, work without a key, and are labelled as stored answers on screen.
- **The voice** (`app/assistant_voice.html`) copies the owner's applications: the realtime
  model, the "marin" voice, the voice detection that decides when a person has finished
  speaking, interruption, noise reduction, a live transcript, a level meter, an idle limit
  and a time limit. The session's settings are checked after the service confirms them,
  because settings in the wrong place are accepted and ignored. The voice must call
  `ask_claude` for every question about the data, says Claude's answer in two or three
  sentences, and the full answer appears in the transcript.
- **The real voice key stays on the server.** The API (`/assistant/voice-token`) asks the
  voice service for a key that lasts a few minutes and passes only that to the page. An
  error from the voice service is never passed on, because it can repeat part of the key.
- **The voice has its own budget** (`VOICE_BUDGET_USD`, 5 dollars by default), kept in the
  shared database (`voice_spend`). Each session reserves its longest possible cost before
  it starts; when it ends, the page reports its real length and the reservation shrinks.
  At the limit the voice turns off and says so, and typing still works.
- **The API accepts calls from the app's own web addresses only** (`app_origins` in
  `config/assistant.yaml`, plus `DSO_APP_ORIGIN`).

## Consequences

- The hosted demo needs two keys on the API service, set by the owner in the host's
  dashboard: `ANTHROPIC_API_KEY` (Claude, for spoken questions) and `OPENAI_API_KEY` (the
  voice). Typed questions on the page use the key already set on the app service. Without
  the keys, the example questions still work, and the page says why the rest is off.
- Two paid services instead of one. Both are capped, and both totals survive a restart.
- The brief's cost rule gives the stronger model only to the agent's replies to customers.
  The assistant is a second exception: it gets the middle model, because it writes SQL
  for visitors and a wrong query gives a wrong number. A typical question costs about
  2 to 3 cents with it (measured while writing the stored answers: 14 answers for 21
  cents). Background jobs stay on the small model, and a test keeps it that way.
- The page library deletes a script that seems to contain markup, so the voice script
  writes markup in strings without a raw "less-than" sign (noted in the file).
- The voice was tested in a browser with a silent stand-in microphone and typed messages:
  the session connected, its settings were confirmed, the voice spoke, called Claude, and
  spoke Claude's answer. Recognition of real speech was not tested by a machine.
- A stored answer describes the data on the day it was written. Visitors who change the
  hosted data (by closing tasks, for example) can make a stored answer out of date; a new
  question gets a fresh answer.

## Revisit if

- The voice service changes its session format: the settings live in one function of the
  voice script.
- Visitors ask questions the tools cannot answer: add a table description or a document,
  not a longer prompt.
- The budgets prove too small or too large for the hiring panel: change `LLM_BUDGET_USD`
  or `VOICE_BUDGET_USD` in the host's dashboard.

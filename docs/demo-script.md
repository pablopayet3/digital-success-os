# Demo script: a six-minute video

Synthetic data, fictional company. This is what to show, in what order, and what to say,
for a recorded video of the hosted app (https://digital-success-os-app.onrender.com).
The same order works live, in an interview.

## Before recording

- [ ] Open the app once a few minutes before, so that it is awake and every page has
      loaded once. Between 06:00 and 22:00 US Eastern time a scheduled request keeps it
      awake.
- [ ] Close the guided tour ("End the tour"), so that it does not cover the pages. Say
      at the end that the tour exists and reads itself aloud.
- [ ] In a second tab, open the Human console and sign in as **CSM** (the hosted
      passwords are on the app service's Environment page in the host's dashboard).
- [ ] Check the browser shows no extension icon in a corner of the page (a real product's
      logo must not appear in the video).
- [ ] Record the browser window only, at a width of about 1,400 pixels.
- [ ] After recording, reset the hosted demo as Admin (Human console, "Reset the demo
      data"), so that the next visitor starts clean.

## The script

Times are targets. If something does not respond, say what should have happened and
move on.

**1. What this is (40 seconds). Overview page, top.**

Show the three paragraphs and the workflow cards.

> "This is a working model of a digital customer-success operation, on fictional data.
> A software company has thousands of customers with no assigned success manager. This
> system watches their data every day, finds the ones who need help, and helps them
> automatically: an email first, then an AI agent, and a person only when one is needed.
> Then it measures whether the help made a difference. Each card is one step, with the
> team responsible for it. At a real company each step runs in a different platform;
> here they sit side by side so you can see how they connect."

**2. What it did today (40 seconds). Overview page, lower down.**

Scroll to "The measures the pilot is run on", then to "What the system did, in plain
words".

> "These eight measures decide whether the pilot is working: adoption, setup, how often
> the agent is used, how often it hands off, and revenue kept, always next to the
> customers we deliberately left alone. And this is the system at work, in plain
> sentences: which customer, what was done, and the signal behind it."

**3. One customer (40 seconds). Accounts page.**

Choose health band **red** in the filter. Rest the pointer on a choice to show its
definition. Open the first customer.

> "One customer, before a call. The health score and the five parts behind it, the risk
> that they cancel, the chance that they buy more, the signals firing today with their
> evidence, and every decision the system took about them, including why it chose not to
> act."

**4. The play, the agent and the handoff (75 seconds). Live demo page.**

Show "Step 1. The system writes first", then press **Run the story**.

> "The system makes the first move: this customer stalled in setup, so the onboarding
> play wrote to them. They reply. The agent checks their setup, searches the help center
> and answers. Then they ask for a price. A rule written in code passes that to Sales
> before the model is even asked, with a summary for the salesperson."

Switch to the Human console tab. Open the new task.

> "This is what the person receives: why the task exists, the customer's own words, what
> was already tried, and a recommended next step. The outcome they record goes back into
> the journey."

**5. Nothing risky is sent without a person (40 seconds). Human console, still signed in.**

Scroll to "Drafts waiting for approval". Open one draft.

> "Some messages carry more risk. This one asks a happy customer to act as a reference.
> It only fires when the customer has earned it: a score of 9 or 10, green health, no open
> problem, no risk of leaving. Even then, the system only writes a draft. A success
> manager approves it, or rejects it, and nothing reaches the customer before that."

**6. Did it work? (45 seconds). Plays and experiments page.**

Show the chart "Results against the holdout", then "One play in detail".

> "Every play is measured against a holdout, on a measure named before launch: the
> difference, its margin of error, and a verdict from a written rule. The customers are
> simulated, so the size of the effect is an assumption. The method is the real part, and
> it is the part most AI demos leave out."

**7. Ask the data (40 seconds). Ask the data page.**

Press one example button, then type or say one question of your own.

> "Any team can ask questions here, by typing or by voice. Claude answers from the
> warehouse and the documents, and says which table or document it used. These examples
> are the questions each team asks every week."

**8. Pilot and ownership (30 seconds). Pilot page, then Operating model.**

> "The readiness checklist is answered from live data, not ticked by hand. Each play
> starts on ten percent of customers, then a full test. This preview shows what adding
> the next group would do to each team's queue. And these are the working documents:
> who owns what, the decisions and their reasons, and what each team waits for."

**Close (10 seconds).**

> "A guided tour, read aloud, walks through every element if you want to explore on your
> own. Thank you."

## If they ask to go deeper

| Question | Where to go | The short answer |
|---|---|---|
| How do you know the model is any good? | `docs/model-cards/` | Time-based split, compared with a benchmark, precision at the team's capacity, reasons in words |
| Why not let the model decide when to escalate? | ADR 0003 | A prompt asks, code guarantees. Each rule has a test that needs no model |
| What does the agent cost? | ADR 0015, 0024 | Cached, budgeted, capped at five dollars on the public demo. One module calls the API |
| Is the lift real? | ADR 0005, 0016 | No, and the report says so. The measurement system is what is being shown |
| Why do some messages need an approval? | ADR 0029, 0030 | Only where the cost of being wrong is high. Everything else stays automatic |
| What would you ask Data Engineering for first? | `docs/data-requirements.md` | Coverage tier, one consent field, account id on every event |
| What does this column mean? | `docs/data-dictionary.md` (Operating model page) | Every column has a definition; a test fails when one is missing |
| How does the agent get better? | Agents page, Review queue tab | An unnecessary handoff or a thumbs down becomes a case the next prompt must pass |
| What happens when a queue overflows? | Human console, ADR 0004 | Flags follow capacity; an alert fires at two days of backlog |
| How would this run in production? | `docs/production-architecture.md` | Same code, a `prod` profile; a table of what is real and what is simulated |

## Running it locally instead

Start the app with `uv run python run.py app` (and the API with `uv run python run.py api`
for voice on the Ask the data page). Locally the console password for every role is
`demo`. Do not press "Advance one day" before the conversation: a new day changes the
customers, and the stored answers no longer match. With `--live` this does not matter.

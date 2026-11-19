# 0034: Each journey is drawn from the configuration that runs it

Status: accepted (19 November 2026, for the case-study interview). Synthetic data,
fictional company.

## Context

A journey was visible only as a list of steps in a configuration file, a funnel chart and
a written specification. People who design and run journeys think in pictures: a journey
map with its moments, questions and handoffs. A picture drawn by hand goes out of date the
first time someone changes a wait or a branch.

## Options

1. **A diagram drawn by hand** in the documents. Quick, and wrong after the first change.
2. **A journey builder** that people edit by dragging boxes. What a customer-success
   platform offers; far more than a pilot needs, and it would duplicate the configuration.
3. **A drawing generated from the configuration**, read-only, with live counts.

## Decision

Option 3: `app/journey_canvas.py` turns a play and its journey into a Graphviz drawing,
shown on the Plays page under "One play in detail".

- The signal that starts the play, who may enter (lifecycle stages and how many rules keep
  customers out), the share held out, then every step: emails (and who approves them),
  messages in the product, waits, the questions asked of the data (with "yes" and "no"
  paths), the AI agent, tasks for a person (with the team), and the ends. A goal that ends
  the journey early is drawn beside it.
- Colours follow the ladder of help: blue digital, purple the agent, orange a person.
- Each step shows how many customers reached it, counted from the journey's own events.
- Top to bottom: the page library shrinks a drawing to the page width, which made a long
  left-to-right flow unreadable.
- A test draws every play and checks that every step and both paths of every question are
  there, in plain words.

## Consequences

- The picture cannot disagree with what runs: it is made from the same files.
- Editing a journey still means editing the configuration and passing change control.

## Revisit if

People outside the CS Operations team need to change journeys themselves. Then a builder,
or the customer-success platform's own, becomes worth it.

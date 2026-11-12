# 0022: Diagrams in the documents are drawn in the app without the network

Status: accepted. Synthetic data, fictional company.

## Context

The documents keep their diagrams as Mermaid text, because the code host draws Mermaid.
The app shows the same documents on its Operating model page, and Streamlit does not
draw Mermaid: the dependency map appeared there as a block of code. The usual fix loads
a drawing library from the internet when the page opens. The demo has to work with the
network off.

## Options

1. Leave the diagram as code in the app and point to the code host.
2. Load the Mermaid library from a content network inside the page. Breaks offline.
3. Keep a copy of the library in the repository. About three megabytes of someone
   else's code to carry and keep current.
4. **Translate the small part of Mermaid the documents use into Graphviz, which
   Streamlit draws by itself.**

## Decision

Option 4, in `app/diagrams.py`: about a hundred lines that understand a flowchart's
direction, groups, boxes, arrows, dashed arrows and arrow labels. The document stays the
single source: the same text is drawn by the code host and by the app.

## Consequences

- It is a translator for the diagrams this project has, not for Mermaid. A diagram that
  uses anything else is shown as its text, never guessed at. A test checks both.
- The layout is Graphviz's, so the picture differs a little from the code host's.
- A new diagram in a document the app lists has to stay inside the supported part, or
  the translator has to grow.

## Revisit if

Streamlit learns to draw Mermaid, or the documents need a kind of diagram (a sequence,
a timeline) that Graphviz does not suit.

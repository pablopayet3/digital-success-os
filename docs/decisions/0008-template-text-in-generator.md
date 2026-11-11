# 0008: Template text in the data generator, no LLM

Status: accepted (Phase 1). Synthetic data, fictional company.

## Context

The world needs free text: about 3,400 support tickets, 1,600 NPS responses and 480
mailbox replies. Later phases classify this text with an LLM, so it has to be realistic
enough to be a fair test.

## Options

1. Generate the text with an LLM. Most natural wording, but it costs money on every
   regeneration, is not repeatable, needs a network connection, and means an LLM would
   later be graded on text an LLM wrote.
2. **Templates plus noise.** Hand-written sentences per category, combined and then
   roughened: typos, lower case, signatures, quoted threads, auto-replies in other
   languages, and messages that mix two intents.

## Decision

Option 2. All wording lives in `synth/text.py`. About a quarter of mailbox replies are
deliberately hard to classify (mixed intent, vague wording, polite complaints). Each reply
has an answer key in `data/ground_truth/mailbox_labels.csv` with its intent, sentiment, any
second intent and a "hard" flag.

## Consequences

- Generation is free, offline and identical on every run.
- The classifier evaluation in Phase 6 can report accuracy separately for easy and hard
  messages, which is more honest than one headline number.
- Wording variety is limited. A classifier will score higher here than on real mail. The
  evaluation report must say so.

## Revisit if

The classifier scores near 100% even on the hard cases. Then the test is too easy and the
templates need more variety (or a one-off, cached LLM paraphrase pass).

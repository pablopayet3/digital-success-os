# 0025: The tour stops on every element, and can be read by a recorded voice

Status: accepted on 13 November 2026, by the owner's decision. Synthetic data, fictional company.

## Context

The first tour was thirteen large windows, one per page. The owner read it as a visitor
would and rejected it on three counts. It described pages in general when a reader needs
each number and each section explained. Its windows covered the page they were about. And
its optional voice, the browser's own (ADR 0023), sounded mechanical: the owner wants the
voice his other applications use.

## Options

1. Keep one window per page, with better words.
2. A tooltip on every element, and no tour. Nothing leads a first-time visitor through
   the pages in order.
3. A tour library loaded from the internet. Breaks the offline demo, and brings a second
   front-end framework into a small app.
4. **A small window fixed in a corner, moved from stop to stop by ordinary buttons, with a
   short script that frames the element being explained. One stop per metric or section.
   Each stop can be played as a recording made once from its own words.**

## Decision

Option 4.

- `config/tour.yaml`: one stop per element. Each says what the element is, who uses it
  and for what, and gives one concrete example.
- `app/tour.py`: the window is a keyed container with Back, Next, Next page and End. It
  is drawn in a corner, so it never covers what it explains.
- `app/tour_card.html`: a style that fixes the window in the corner, and a script that
  finds the element by the words it carries, brings it to the top of the page, and draws
  a glowing frame around it. The page redraws its elements while it loads, so the script
  keeps looking and puts the frame back.
- `scripts/tour_voice.py`: records each stop once with a text-to-speech service, in the
  voice named in `config/tour.yaml`. A recording is named after a fingerprint of the
  stop's words. A stop whose words changed has no recording until the script runs again,
  so the voice can never say something the window does not.
- Every number also carries its definition as a hover text (`config/glossary.yaml`).

## Consequences

- A second paid service, used only when recording: under a dollar for the whole tour.
  Running the app costs nothing and needs no key, because the app only plays files.
- The key for the recording stays with the owner. The script reads it from an
  environment file and never prints it.
- A stop finds its element by its words. Rewording a label without rewording the stop
  would lose the frame, so a test checks that every stop's words are on its page.
- The tour is long: one stop for each of about fifty elements. "Next page" skips ahead,
  and the tour can be ended at any stop.
- The recordings are binary files in the repository, a few megabytes in all.

## Revisit if

The pages change so often that recording again becomes a chore, or a visitor needs the
tour in another language.

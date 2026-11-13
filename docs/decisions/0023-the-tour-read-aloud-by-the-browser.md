# 0023: The guided tour can be read aloud, by the browser's own voice

Status: accepted. Synthetic data, fictional company.

## Context

The guided tour is thirteen windows of text. The owner asked for a voice that reads them,
so a visitor can listen while looking at the page behind the window. The project's rules
still hold: free tiers only, no service that needs a key, and a demo that works with the
network off.

## Options

1. Record the narration as audio files. The best voice, but thirteen recordings to redo
   every time a sentence of the tour changes.
2. A text-to-speech service. A good voice, but a paid service, a key, and a network call.
3. **The browser's built-in speech, started by a button in the window.**

## Decision

Option 3. `app/tour_voice.html` holds one button and about forty lines of JavaScript;
`app/tour.py` puts the window's sentences into it. The voice is off until the visitor
presses "Read aloud". After that it stays on from window to window, and stops when the
window is closed or the button is pressed again.

## Consequences

- Nothing is spent, stored or sent. The words read are the words shown, so the two can
  never differ.
- The voice is whichever one the visitor's browser has. Some are natural, some sound
  mechanical. The script prefers a natural one when there is one.
- It never starts by itself: a voice from a laptop in an open office is a bad surprise.
- Sentences are sent to the voice one at a time, because some browsers cut a long reading
  off after about fifteen seconds. A test keeps every sentence short.
- A browser with no speech support hides the button.

## Revisit if

The tour's words stop changing and the voice matters enough to record it once, properly.

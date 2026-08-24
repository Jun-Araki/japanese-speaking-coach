"""The look, and the two paragraphs a learner has to be shown before they type.

CSS ONLY, AND SUBTRACTIVE. No UI framework, no design system (the project rules).
Unbleached paper, sumi ink, one accent, a serif for headings, wide margins, hairline
rules, no shadows. NO torii, no cherry blossom, no red-and-gold: the Japanese
clichés read as cheap instantly, and the restraint is the point — a plain page in
two colours looks considered, and the same page with an emoji border looks like a
template.

THE NOTICE IS NOT BOILERPLATE. Three things have to be said before a beginner types
a sentence into this: that what they write leaves the machine, that nothing is kept,
and how to reach a person. The first is the one they cannot work out for themselves,
and the second is a claim this project can actually make — there is no database, no
file and no log line carrying a sentence.

The AI-voice line sits inside that notice, on the screen before anyone speaks, rather
than beside the player: hearing a synthetic voice and not having been told it is
synthetic is the version of this a person could reasonably object to afterwards, and
being told once, up front, is what answers that.
"""

from __future__ import annotations

from typing import Final

CONTACT: Final = "jun7772006@gmail.com"

# One accent, used for the corrected sentence and nothing else, so that the single
# coloured thing on the page is the thing the learner came for.
# The palette lives in .streamlit/config.toml, which is applied before anything
# renders; a phone in dark mode ignored the CSS below and served white-on-black.
# What stays here is what the theme section cannot say.
STYLE: Final = """
<style>
  :root {
    --paper: #faf6ef;
    --sumi: #1c1a17;
    --accent: #7a5c3e;
    --rule: #e2d9cb;
    --moss: #4a6b3d;
    --vermilion: #a8452f;
  }
  h1, h2, h3 {
    font-family: "Hiragino Mincho ProN", "Yu Mincho", Georgia, serif;
    font-weight: 500;
    letter-spacing: 0.02em;
  }
  .block-container { max-width: 46rem; padding-top: 3rem; }
  hr, [data-testid="stDivider"] { border-color: var(--rule); }
  [data-testid="stChatMessage"] {
    background: transparent;
    border: 1px solid var(--rule);
    border-radius: 2px;
    box-shadow: none;
  }
  [data-testid="stVerticalBlockBorderWrapper"] { box-shadow: none; }
  .stButton button {
    border-radius: 2px;
    border: 1px solid var(--sumi);
    box-shadow: none;
  }
  .stButton button[kind="primary"] {
    background: var(--sumi);
    border-color: var(--sumi);
  }
  .corrected { color: var(--accent); }

  /* Small enough to read as a button rather than a media player.
     SAFARI ON iOS WILL NOT AUTOPLAY UNMUTED AUDIO without a user gesture on the same
     rendering of the page, and the reply arrives on a later rerun than the tap that
     asked for it — so on a phone this control is the only way to hear the line, and
     on a laptop it has already played by the time anyone looks at it. Muted autoplay
     is the documented exception and is no use to a speaking app. */
  audio.reply-audio {
    height: 34px;
    max-width: 220px;
    margin-top: 0.4rem;
    opacity: 0.75;
  }

  /* The review. Right and wrong are told apart by colour as well as by words: a
     learner scanning five sentences should see which ones need attention before
     reading any English. Moss and vermilion rather than a traffic-light green and
     red — the palette is unbleached paper and sumi, and pure #f00 on it looks like
     an error dialog rather than a correction. */
  .review-card {
    border: 1px solid var(--rule);
    border-left: 3px solid var(--rule);
    border-radius: 2px;
    padding: 0.9rem 1.1rem;
    margin-bottom: 0.9rem;
  }
  .review-card.ok { border-left-color: var(--moss); }
  .review-card.fixed { border-left-color: var(--vermilion); }
  .review-said { font-weight: 600; }
  .review-card.fixed .review-said { color: var(--vermilion); }
  .review-fixed-line { color: var(--moss); font-weight: 600; margin-top: 0.35rem; }
  .review-ok-line { color: var(--moss); margin-top: 0.35rem; }
  .review-why { color: #5c564d; font-size: 0.92rem; margin-top: 0.5rem; }
  .review-source { color: #8a8375; font-size: 0.82rem; margin-top: 0.35rem; }
</style>
"""

# SHORT ENOUGH TO BE READ, which is the only version that protects anybody. The first
# draft ran to eighty-five words and said everything twice: "no names, addresses,
# passwords or work information" after "nothing private", "closing the page ends the
# session" after "nothing is stored". A learner standing at a meetup table skips a
# paragraph that size, and a notice nobody reads is decoration.
#
# FOUR THINGS COULD NOT GO, and none of them did: that what is said leaves this
# machine, that private things should not be said, that the voice is not a person,
# and how to reach one (the line under this, in main.py). The rest was compression.
NOTICE: Final = (
    "**Before you start.** What you say goes to an AI outside this app, so say nothing "
    "private — no names, addresses or passwords. **Nothing is stored**: no database, no "
    "recording, no log. Replies can be wrong, and **the voice is AI-generated, not a "
    "person's.**"
)

# DISCLOSURE, SAID ONCE. Speech-synthesis terms require telling people the voice is
# generated, and it is a line item in the definition of done. It used to sit under
# every audio player, where it was read once and then became furniture — so it moved
# into the notice on the start screen, which is read before anyone speaks. Repeating
# it every turn was noise; removing it altogether is not an option.
VOICE_NOTICE: Final = (
    "The voice you hear is synthesised by an AI. It is not a recording of a person."
)

# MEASURED, NOT SUSPECTED. Five sentences carrying real learner mistakes were spoken
# and transcribed back on 2026-08-20: four came back with the mistake repaired —
# 「オフィスでいます」 became 「オフィスにいます」, 「毎日で走る」 became 「毎日走る」.
# The transcriber is a language model, so it writes down what the speaker meant
# rather than what they said, and a repaired sentence reaches the correction engine
# looking correct.
#
# A beginner cannot see that this has happened, which is why it is written on the
# screen rather than left in the README: they are the one person who cannot check.
SPEECH_CAVEAT: Final = (
    "**Speaking is for practice.** Transcription sometimes tidies up a mistake before "
    "the correction engine sees it, so a sentence you got wrong can come back as "
    "\"this one is fine\". **Type instead if you want every mistake caught.**"
)

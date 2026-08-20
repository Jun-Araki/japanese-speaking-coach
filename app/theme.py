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

The AI-voice line is written now and shown when audio lands: hearing a synthetic
voice and not being told it is synthetic is the version of this that a person could
reasonably object to afterwards.
"""

from __future__ import annotations

from typing import Final

CONTACT: Final = "jun7772006@gmail.com"

# One accent, used for the corrected sentence and nothing else, so that the single
# coloured thing on the page is the thing the learner came for.
STYLE: Final = """
<style>
  :root {
    --paper: #faf6ef;
    --sumi: #1c1a17;
    --accent: #7a5c3e;
    --rule: #e2d9cb;
  }
  .stApp { background: var(--paper); color: var(--sumi); }
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
</style>
"""

NOTICE: Final = (
    "**Before you start.** What you write is sent to an AI model outside this app "
    "to generate the reply and the corrections, so do not type anything private — "
    "no names, addresses, passwords or work information. **Nothing you write is "
    "stored**: there is no database and no log, and closing the page ends the "
    "session for good. The replies are generated, so they can be wrong."
)

# Shown once audio is in. Written now so that adding the feature cannot ship without
# the sentence that has to go with it.
VOICE_NOTICE: Final = (
    "The voice you hear is synthesised by an AI. It is not a recording of a person."
)

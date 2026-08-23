"""Cost guards, and the one shared code that keeps the demo from being open to all.

COUNTED IN PROCESS, IDENTIFYING NOBODY. The counters live in a module-level dict
keyed by the calendar date and nothing else — no learner, no session, no address.
A restart resets them, and that is the accepted cost of the decision not to store
anything (the planning document, §2-5): a counter that survives a restart is a file
or a database, and both would be the first thing in this project to keep a record
of what a learner did.

THE LIMITS ARE GUARDS, NOT MEASUREMENTS. Nothing is published from them. They exist
so that a demo link handed to a room full of people at a meetup cannot quietly run
up a bill, and so that the answer to "what stops this costing money" is a number in
a file rather than a hope.

TOKENS ARE ESTIMATED, AND THE ESTIMATE IS DELIBERATELY CRUDE. Counting exactly
means asking the provider for usage on every call and threading it back through
three layers; the guard only has to be right to within a factor of two to do its
job. Japanese averages fewer characters per token than English, so the estimate
divides by a small number and errs towards over-counting — a guard that fires
slightly early is a guard, and one that fires slightly late is a bill.
"""

from __future__ import annotations

import os
import secrets
import threading
import time
from datetime import date
from typing import Final

# Roughly characters per token for the mixed Japanese and English this app sends.
# Erring low means the estimate runs high, which is the safe direction for a cap.
_CHARS_PER_TOKEN: Final = 2.0

DEFAULT_DAILY_TOKENS: Final = 200_000
DEFAULT_DAILY_TTS_CHARS: Final = 50_000

# How long to stop asking for speech after the provider says we are asking too
# often. A minute, because the free tier's limit is a per-minute one — measured on
# 2026-08-22, when one person practising alone was enough to reach it.
DEFAULT_TTS_COOLDOWN: Final = 60

# One session's worth of turns, the same number the API enforces. Duplicated as a
# default rather than imported, because the app must not need the API to run.
DEFAULT_MAX_TURNS: Final = 20

_used: dict[tuple[str, date], int] = {}

# When speech may be asked for again, on the monotonic clock. Process-wide on
# purpose: THE LIMIT IS THE API KEY'S, NOT THE LEARNER'S. One deployment, one key,
# and everyone at a meetup shares it — so a 429 caused by one tab has to quiet all
# of them, or the others spend the recovery window refusing each other.
_tts_quiet_until: float = 0.0


class LimitReached(RuntimeError):
    """Raised when a guard would be crossed. The caller shows it to the learner."""


def _limit(name: str, fallback: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return fallback
    try:
        return int(raw)
    except ValueError:
        # A typo in a deployment secret must not silently remove the guard.
        raise ValueError(f"{name} is not a whole number: {raw!r}") from None


def max_turns() -> int:
    return _limit("MAX_TURNS", DEFAULT_MAX_TURNS)


def estimate_tokens(text: str) -> int:
    return int(len(text) / _CHARS_PER_TOKEN) + 1


def spend_tokens(text: str, today: date | None = None) -> None:
    """Count one call's input against the daily cap, or refuse it.

    Refuses BEFORE the call rather than after, so the cap cannot be crossed by the
    request that discovers it.
    """
    _spend(
        "tokens",
        estimate_tokens(text),
        _limit("DAILY_TOKEN_LIMIT", DEFAULT_DAILY_TOKENS),
        today,
    )


def spend_tts_chars(text: str, today: date | None = None) -> None:
    """The same guard for speech synthesis, which is billed by the character."""
    _spend(
        "tts_chars",
        len(text),
        _limit("DAILY_TTS_CHAR_LIMIT", DEFAULT_DAILY_TTS_CHARS),
        today,
    )


# READ, COMPARE, WRITE — three steps, and Streamlit runs each session on its own
# thread. Two people at a meetup crossing the same counter would each read the old
# value and each write it back, so one of the two calls would be free. A guard that
# undercounts under load is a guard that fails exactly when it is needed.
_COUNTING = threading.Lock()


def _spend(kind: str, amount: int, cap: int, today: date | None) -> None:
    key = (kind, today or date.today())
    with _COUNTING:
        if _used.get(key, 0) + amount > cap:
            raise LimitReached(
                f"The daily {kind.replace('_', ' ')} limit for this demo has been reached. "
                "It resets tomorrow."
            )
        _used[key] = _used.get(key, 0) + amount


def tts_cooldown() -> int:
    return _limit("TTS_COOLDOWN_SECONDS", DEFAULT_TTS_COOLDOWN)


def start_tts_cooldown(now: float | None = None) -> None:
    """Stop asking for speech for a while, because the provider said to.

    Called when synthesis comes back 429. Asking again immediately is not merely
    rude: each refused request is still a request, so it lengthens the window it is
    waiting out, and it costs the learner a second of waiting to be told no.
    """
    global _tts_quiet_until
    _tts_quiet_until = (time.monotonic() if now is None else now) + tts_cooldown()


def tts_is_quiet(now: float | None = None) -> bool:
    """Whether speech is currently being skipped without being asked for."""
    return (time.monotonic() if now is None else now) < _tts_quiet_until


def used(kind: str, today: date | None = None) -> int:
    return _used.get((kind, today or date.today()), 0)


def reset() -> None:
    """For tests. Nothing in the app calls this."""
    global _tts_quiet_until
    _used.clear()
    _tts_quiet_until = 0.0


def access_code() -> str | None:
    """The one shared code, or None when the demo is open.

    None rather than an empty string so that "no code configured" is a state the
    caller has to handle deliberately. Locally there is no code; the deployed demo
    sets one.
    """
    code = os.environ.get("ACCESS_CODE", "").strip()
    return code or None


def code_matches(given: str) -> bool:
    """Whether the code typed in is the configured one.

    Compared with `secrets.compare_digest` rather than `==`: the difference is
    negligible for a demo code, and reaching for the wrong one out of habit is how
    the same mistake gets made later on something that matters.
    """
    expected = access_code()
    if expected is None:
        return True
    return secrets.compare_digest(given.strip(), expected)

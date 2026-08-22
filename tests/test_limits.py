"""Tests for the cost guards and the shared code.

These are guards rather than measurements, so what is pinned is the direction they
fail in: a cap must refuse the request that would cross it, not the one after, and
a missing configuration must not silently remove the guard.
"""

from __future__ import annotations

from datetime import date

import pytest

from app import limits

TODAY = date(2026, 8, 20)
TOMORROW = date(2026, 8, 21)


@pytest.fixture(autouse=True)
def clean() -> None:
    limits.reset()


class TestQuietingDownAfterA429:
    """The response to being rate-limited is to stop asking, not to ask again.

    Measured on 2026-08-22: one person practising alone reached the free tier's
    speech limit, and every refused request is still a request — so asking through
    the window makes the window longer and costs the learner a second of waiting to
    be told no.
    """

    def test_a_cooldown_starts_quiet_and_ends_loud(self) -> None:
        limits.start_tts_cooldown(now=1_000.0)

        assert limits.tts_is_quiet(now=1_000.0)
        assert limits.tts_is_quiet(now=1_000.0 + limits.tts_cooldown() - 1)
        assert not limits.tts_is_quiet(now=1_000.0 + limits.tts_cooldown())

    def test_nothing_is_quiet_until_the_provider_says_so(self) -> None:
        # Silence by default would mean a deployment that never speaks until it has
        # first been refused, which is exactly backwards.
        assert not limits.tts_is_quiet(now=1_000.0)

    def test_the_length_is_configurable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TTS_COOLDOWN_SECONDS", "5")

        limits.start_tts_cooldown(now=1_000.0)

        assert limits.tts_is_quiet(now=1_004.0)
        assert not limits.tts_is_quiet(now=1_005.0)

    def test_it_is_process_wide_rather_than_per_learner(self) -> None:
        # The limit belongs to the API key, and one deployment has one key. A
        # per-session cooldown would have every other tab spend the recovery window
        # refusing each other.
        limits.start_tts_cooldown(now=1_000.0)

        assert limits.tts_is_quiet(now=1_000.0)
        limits.reset()
        assert not limits.tts_is_quiet(now=1_000.0)


class TestDailyCaps:
    def test_refuses_the_request_that_would_cross_the_cap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Before, not after. A cap checked afterwards has already been crossed by
        # the request that discovered it, and the bill is for the call that was
        # made rather than the one that was refused.
        monkeypatch.setenv("DAILY_TOKEN_LIMIT", "10")

        limits.spend_tokens("あ" * 10, today=TODAY)  # about 6 tokens
        with pytest.raises(limits.LimitReached):
            limits.spend_tokens("あ" * 10, today=TODAY)

    def test_the_counter_is_per_day(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DAILY_TOKEN_LIMIT", "10")
        limits.spend_tokens("あ" * 10, today=TODAY)

        limits.spend_tokens("あ" * 10, today=TOMORROW)

        assert limits.used("tokens", today=TOMORROW) > 0

    def test_speech_is_capped_by_the_character(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Synthesis is billed per character, so it is counted per character rather
        # than pushed through the token estimate.
        monkeypatch.setenv("DAILY_TTS_CHAR_LIMIT", "5")

        limits.spend_tts_chars("12345", today=TODAY)
        with pytest.raises(limits.LimitReached):
            limits.spend_tts_chars("6", today=TODAY)

    def test_the_estimate_errs_towards_over_counting(self) -> None:
        # A guard that fires slightly early is a guard; one that fires slightly late
        # is a bill. Japanese runs at roughly one token per character, so an
        # estimate at two characters per token must not come out under half.
        assert limits.estimate_tokens("おはようございます") >= 4

    def test_a_missing_setting_keeps_the_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DAILY_TOKEN_LIMIT", raising=False)

        limits.spend_tokens("おはよう", today=TODAY)

        assert limits.used("tokens", today=TODAY) > 0

    def test_a_malformed_setting_is_loud(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A typo in a deployment secret must not remove the guard quietly.
        monkeypatch.setenv("DAILY_TOKEN_LIMIT", "200_000 tokens")

        with pytest.raises(ValueError, match="DAILY_TOKEN_LIMIT"):
            limits.spend_tokens("おはよう", today=TODAY)


class TestAccessCode:
    def test_no_code_configured_lets_everyone_in(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Locally there is no code. The gate is not rendered at all in that case, and
        # this is the function that decides it.
        monkeypatch.delenv("ACCESS_CODE", raising=False)

        assert limits.access_code() is None
        assert limits.code_matches("anything")

    def test_the_configured_code_is_required(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ACCESS_CODE", "minna2026")

        assert limits.code_matches("minna2026")
        assert limits.code_matches("  minna2026  ")
        assert not limits.code_matches("minna2025")
        assert not limits.code_matches("")

    def test_whitespace_around_the_setting_does_not_break_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Secrets pasted into a deployment console pick up trailing newlines.
        monkeypatch.setenv("ACCESS_CODE", " minna2026\n")

        assert limits.code_matches("minna2026")

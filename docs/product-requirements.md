# Product Requirements

> **Thin by design.** This file is the English summary a reader of this repository needs.
> The full scope, schedule, and definition of done live in the author's planning document,
> which is kept private because it also contains personal career material. Where the two
> disagree, the private plan wins and this file is corrected to match.

## Problem

In Bangalore many people start learning Japanese. There is a wide gap between reading a
textbook and saying one sentence out loud. Learners have no one to speak with, so their
mistakes are never corrected, and teachers are far outnumbered by learners.

## What this is

A web app where a beginner picks a situation, talks with an AI **by voice**, and receives
corrections with short English explanations **after** the conversation ends.

1. Pick a scene (greeting, self-introduction, thanks, simple request, notifying a delay, workplace politeness)
2. Press **Start conversation** — the AI speaks first
3. Press the microphone, speak, the AI replies by voice, repeat for as many turns as wanted
4. Press **End conversation**
5. **Review**: every sentence the learner said, what should have been corrected, a natural
   phrasing, and a one-to-two sentence reason in English

## What this is deliberately not

No lessons, no drills, no exam preparation, no flashcards, no listening quizzes, and
**no pronunciation scoring**. Voice is an input method; what gets corrected is phrasing,
not phonemes. Competing on feature count against established services is a losing game.

## Users

Beginners learning Japanese in Bangalore, reached through the Minna Shuugou community and
personal contacts. They open the app on a phone browser, from a link, with a personal
access code. No account registration.

## What makes it different

1. Corrections only — not a course
2. **Correction quality is published as numbers** (competing services publish none, so
   measuring at all is the differentiator)
3. Corrections are grounded in a grammar reference via retrieval

## Success criteria (end of August 2026)

| Metric | Definition in [glossary.md](glossary.md) | Target |
|---|---|---|
| Detection accuracy | `detection_accuracy` | ≥ 85% |
| Over-correction rate | `over_correction_rate` | ≤ 15% |
| Correction validity | `correction_validity` | ≥ 85%, with ≥ 80% agreement from a second native rater |
| Retrieval hit rate | `retrieval_hit_rate` | ≥ 80% |
| Level compliance | `level_compliance_rate` | ≥ 90% |
| Adoption | Testers who held at least one conversation | ≥ 5 people |

All correction metrics are measured on a **self-built 120-item evaluation set**, split
80 development / 40 held-out test, and reported **against a naive single-call baseline**.

## Non-functional requirements

- Response latency reported as median and 95th percentile, **split into with-speech and
  without-speech**, before and after optimisation
- Runs locally with `docker compose up`
- Secrets in environment variables; per-day token and text-to-speech caps
- Consent notice, a warning not to speak confidential information, disclosure that the
  voice is synthetic, and a contact point for deletion requests
- Learner names are never stored

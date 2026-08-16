# Product Requirements

**Translation of [`../ja/product-requirements.md`](../ja/product-requirements.md), which is authoritative.** If the two
disagree, the Japanese version is correct and this file needs updating.


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
personal contacts. They open the app on a phone browser, from a link, with **one shared
access code**. No account registration.

**Individual access codes are not issued (decided 2026-08-16).** The original plan gave each
tester their own code so that retention could be measured, but **two or three testers never
add up to a statistic**, so the handling cost is not worth it. The code now has one purpose
only: keeping the demo from being open to everyone.

## User stories

1. **As someone who has just started learning Japanese**, I can pick a scene and speak,
   so I can practise **without owning a Japanese keyboard**.
2. **As a learner**, I am never interrupted by corrections mid-conversation, so I can
   **finish what I am saying without fear of getting it wrong**.
3. **As a learner**, after the conversation I see my sentence beside a natural phrasing
   **with the reason in English**, so I understand why it needed changing.
4. **As a learner who wants listening practice**, I can hide the AI's reply text and
   switch to ear training without leaving the app.
5. **As a learner the transcription got wrong**, I can press "Say again" and repeat myself,
   so I am **never forced to type**.
6. **As the developer**, I can feed evaluation data straight to the correction engine, so I
   **measure correction quality alone**, unaffected by the app or by transcription.

**Acceptance:** stories 1–5 are confirmed by a tester completing one session on a real
phone browser. Story 6 is confirmed by running the evaluation script.

## What makes it different

The closest comparison is `japanesecompass.com` (checked 2026-08-02 and 08-03). It wins on
breadth of features, so this does not compete there.

**Two things are not differentiators, both verified:**

- **Its AI conversation already corrects** ("get gentle corrections", "teacher-grade
  corrections" on the paid tier)
- **It also takes voice, and even scores pronunciation** (`/practice/speaking/`).
  **This project does not score pronunciation**

**The gap is in the combination.** There, voice and conversation are separate features:
speaking practice has you **read a model sentence aloud and shadow it**, while the AI
conversation is a chat you **type**. You can speak, or you can compose your own sentences,
but not both at once.

1. **Speak your own words, out loud, in a conversation** — not shadowing, not typing.
   **If learners only repeat fixed phrases there is nothing left to correct**, and the
   evaluation has nothing to measure
2. **Corrections are withheld until the conversation ends** — theirs corrects as you go
3. **Correction quality is published as numbers** ← **the real one. Verified: they publish no
   accuracy figures at all**
4. Corrections are grounded in a grammar reference via retrieval

## Success criteria (end of November 2026)

| Metric | Definition in [glossary.md](glossary.md) | Target |
|---|---|---|
| Detection accuracy | `detection_accuracy` | ≥ 85% |
| Over-correction rate | `over_correction_rate` | ≤ 15% |
| Correction validity | `correction_validity` | ≥ 85%, **rated by one person** (see below) |
| Rater agreement | `rater_agreement` | **Not measured** — no second rater was obtained (see §5 of [glossary.md](glossary.md)) |
| Retrieval hit rate | `retrieval_hit_rate` | ≥ 80% |
| Level compliance | `level_compliance_rate` | ≥ 90% |
| Adoption | **No figure is published.** Written feedback from 2–3 testers | 3 comments |

All correction metrics are measured on a **self-built 120-item evaluation set**, split
80 development / 40 held-out test, and reported **against a naive single-call baseline**.

**The deadline moved from end of August to end of November (2026-08-16)**, because the working
budget fell from 26 hours a week to **six and a half**. **Not one metric or target value
changed** — what changed is the date, and what is listed as no longer measured below.

### What is deliberately not measured (2026-08-16)

**Missing a target damages an evaluation far less than pretending to have measured something.**
Nothing dropped here is hidden.

| Dropped | Original definition | Why |
|---|---|---|
| **Latency** (`latency_ms`) | Median and 95th percentile, split with and without the speech stages, before and after optimisation | Instrumentation and optimisation both cost time, and **neither touches the three headline metrics**. The README says plainly that it is not measured |
| **Tester count and retention** | At least 5 testers holding a conversation, turns per tester | Two or three testers is not a statistic, and **with nothing stored there is no way to collect it** (see "The decision to store nothing" in [architecture.md](architecture.md)) |
| **Transcription accuracy and end-to-end accuracy** | 30 recordings transcribed by ear and compared against the machine output | **Audio is not stored**, so the material does not exist |

**One distinction, because it is easy to misread.** "Not measured" means *not published as a
metric*. `evals/score.py` does still record how long an evaluation run took (`elapsed_ms` /
`latency_ms`) in its run records. That is **the evaluation script recording its own execution,
not the app recording anything about a learner**. **No README figure rests on it and no
optimisation is planned.** Leaving this vague would amount to measuring something while claiming
not to, so the same caveat is written into the code.

**The count of *Say again* presses is lost too.** It was designed as a proxy for transcription
quality, but nothing is stored, so nothing accumulates. **The button itself stays** — its
purpose is sparing the learner from retyping, which is a different goal.

## Non-functional requirements

- Runs locally with `docker compose up`
- Secrets in environment variables; per-day token and text-to-speech caps
- A warning not to speak confidential information, disclosure that the voice is synthetic,
  and **a contact address** (not a deletion route — with nothing stored there is nothing to delete)
- **Nothing a learner says, records or gets corrected is stored anywhere**, and no name is
  stored. **With nothing stored, no consent record is kept either** — only the notice is shown

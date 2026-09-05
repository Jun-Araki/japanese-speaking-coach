# Architecture

**Translation of [`../ja/architecture.md`](../ja/architecture.md), which is authoritative.** If the two
disagree, the Japanese version is correct and this file needs updating.


> **Thin by design.** The table below is the public extract of the stack decisions.
> **Nothing outside this table is adopted before 20 September.**

## Stack

| Area | Choice | Why |
|---|---|---|
| LLM | **LangChain → Gemini** (decided 2026-08-03) | See "Choosing a provider" below |
| Transcription | **Gemini** (`gemini-flash-lite-latest`, audio passed inline; changed 2026-08-24) | **Provisional.** Chosen because no OpenAI key was available — see "Transcription erases the learner's mistakes" |
| Text to speech | **The browser's own voice** (default, changed 2026-08-24), or **Gemini** (`gemini-2.5-flash-preview-tts`) with `BROWSER_VOICE=0` | **No round trip, so it starts at once, with no rate limit and no bill.** The Gemini path is a preview model and **one person alone reaches the free tier's rate limit** (see below). **Disclosing that the voice is AI-generated is done either way** |
| Tokenization | SudachiPy + SudachiDict (Apache-2.0) | Japanese has no spaces between words, so vocabulary-level checking requires morphological analysis |
| Embeddings | sentence-transformers, multilingual | Retrieval over Japanese text |
| Vector store | Chroma | Fastest local option, sufficient for a demo |
| Agent | LangGraph | The correction splits into retrieve / correct / validate with a loop back — a real graph, not a chain |
| Database | **None** (decided 2026-08-16) | **Nothing a learner says, records or gets corrected is stored anywhere.** See "The decision to store nothing" below |
| API | FastAPI | `POST /chat`, `POST /check`, `GET /health` |
| UI | Streamlit | Fastest path to a public demo |
| Container | Docker + compose | `docker compose up` runs the UI and the API |
| Evaluation | Custom scripts (pytest allowed) | Produces the README numbers |
| Deploy | UI on Streamlit Community Cloud, API on Hugging Face Spaces (fallback Render) | Free tiers; secrets via each platform's secret store |

## Choosing a provider (2026-08-03)

Claude API was the original choice, but Anthropic's payment form could not be completed and
no key was obtained. A `GEMINI_API_KEY` was already available, so **Gemini was adopted to
avoid blocking the build.**

- Calls go through LangChain, so **swapping the provider is a one-line change** and Anthropic
  can be swapped back in once billing works
- **The baseline and the real implementation must be measured on the same model.** Measuring
  the naive version on one model and the real one on another turns the comparison table into
  a comparison of models rather than of the validation logic, which **destroys the centrepiece
  of the evaluation**
- If the provider is swapped, either re-measure both, or make the model explicit in the
  `run_record` so a reader can tell the runs apart

## The decision to store nothing (2026-08-16)

**The original plan wrote consent records and usage logs to a free-tier PostgreSQL (Neon or
Supabase). That was dropped.**

- **There are only two or three testers.** No usage log at that size supports a statistical claim
- **What a learner says is personal data.** Carrying the responsibility of storing it while
  gaining nothing from it is a bad trade
- **With nothing stored, no consent record is needed either.** The notice stays — recordings
  really are sent to external APIs
- **One dependency fewer, and a shorter deployment**

**This gets one line in the README.** The fact is not "a free database could not be wired up"
but **"storage was considered, and storing nothing was chosen"** — and the second is the
honest account.

**The cost:** latency, the number of *Say again* presses, and any retention figure become
unmeasurable. **The largest cost is that transcription accuracy and end-to-end accuracy can
never be measured** — no recording survives to be transcribed by ear. **All of them have been
dropped as metrics** — see "What is deliberately not measured" in
[product-requirements.md](product-requirements.md).

## Choosing a speech provider

**Decided in early September, when voice is built.** Gemini handles both transcription and speech
generation (WAV accepted, Japanese supported) and would keep everything on one key. But
**Gemini transcribes via a prompt — a language model writes the text** — so it may **repair the
learner's mistakes more aggressively than a dedicated speech recogniser would**. That would
erase exactly what this app exists to correct.

**This had to be decided by argument, not by measurement (revised 2026-08-16).** The original
plan was to measure both transcribers against recordings transcribed by ear; **no audio is
stored now, so that comparison cannot be run.** The decision therefore leaned towards a dedicated
speech model, on the reasoning above.

> **Settled on 2026-08-20, and not the way the reasoning above recommended.** `OPENAI_API_KEY`
> was never obtained, so voice was built on Gemini — and the concern above reproduced in
> measurement. See below.

## Transcription erases the learner's mistakes (measured 2026-08-20)

**The concern above was right.** Five sentences carrying real learner mistakes from the dev split
were synthesised and transcribed back: **the mistake survived in one of five**. 「オフィスで
います」 came back as 「オフィスにいます」 and 「毎日で走る」 as 「毎日走る」 — particles and
conjugations silently repaired. The same test on five *correct* sentences lost nothing but a
proper noun: **sounds that are right are transcribed accurately, and sounds that are wrong are
tidied up.** A language model writing the text behaves like a language model.

**Tightening the prompt did not help.** Told explicitly that the speaker is a beginner, that
grammar must not be corrected, and that an ungrammatical result is expected, the score stayed at
one in five — different sentences survived, not more of them.

**Other Gemini models were tried (2026-08-20)**, all on the same synthesised audio.

| Model | Mistake survived |
|---|---|
| `gemini-2.5-flash` (in use) | 1/5 |
| `gemini-2.5-pro` | could not be measured (HTTP error) |
| `gemini-3.5-flash` | 1/5 |
| `gemini-3.7-flash` | 1/5 |

**The newer the model, the more fluently it repairs.** 3.5 and 3.7 turned 「払うたいです」 into a
clean 「払いたいです」 — excellent transcription, and for this app the erasure of the mistake.
**There is no move left inside Gemini.**

**The same audio at temperature 0 does not even give the same answer twice**: 2.5-flash returned
「私はオフィスにいます」 on one run and 「私はオフィスいます」 on another. **One in five is itself
a noisy figure.**

**The measurement cannot separate the two sides.** The audio was synthesised, so a mangled result
may come from the speaking side rather than the listening side. Separating them needs recordings
of real learners, and **this app stores no audio** — the same constraint that made the choice
unmeasurable in the first place.

> ### Added 2026-08-24 — **trying to make it faster improved this instead**
>
> `gemini-flash-lite-latest` was tried to cut the wait before anything appears on
> screen (the lite text model 404s on this key; **the audio path works**). Both models
> measured on the same five clips:
>
> | | median | exact | mistake kept |
> |---|---|---|---|
> | `gemini-2.5-flash` (was) | 3.14s | 1/5 | **1/5** |
> | `gemini-flash-lite-latest` (now) | **1.70s** | **3/5** | **4/5** |
>
> - 「オフィス**で**います」 and 「毎日**で**走る」: **the old model repaired both, the new one kept both**
> - 「私は毎朝六時起きます」: the old model dropped the verb entirely; the new one kept it (六 vs 6 aside)
> - **Same reasoning as the section above.** The more fluent the model, the more it
>   writes down what was MEANT — which for this app is the erasure of the thing being
>   practised. Being less fluent makes it more faithful.
> - It costs spaces between words, which Japanese does not use. `strip_spacing`
>   removes them, **in the same layer and for the same reason as the restored full
>   stop**: the published numbers were measured on that correction prompt.
>
> **Still n=5.** The old 1/5 was also n=5, so the comparison is like for like, but the
> caveat above about the spread applies to both. **This is not in the README yet**, and
> should not be until it is measured over more than five clips.

**So this is how it stands.**

- **Every published number is measured on text**, fed to the correction engine directly
- **The screen says so above the microphone.** A beginner cannot see that a mistake was repaired,
  so the warning belongs where they are, not only in the README
- **The real fix is a dedicated speech recogniser** (`whisper-1` or similar). It needs a provider
  key this project does not have.

## Speech synthesis reaches the free tier's rate limit (measured 2026-08-22)

> **Since 2026-08-24 this section is not about the default path.** The default is the
> browser's own voice: no round trip, no rate limit, no bill. What follows describes the
> Gemini path, reached with `BROWSER_VOICE=0` — and it is **why 13 September can be run on
> the free tier**: the shared key's limit no longer stops the path everyone is on.
>
> **The constraint that replaced it belongs to the device** (worked through 2026-08-25).
> **A phone with no Japanese voice installed says nothing at all.** At a meetup the phones
> differ and whoever gets silence assumes their own is broken. So **(1) the start screen says
> the reply is always written down and that it is your own device reading it, and (2) the
> message shown on a device with no Japanese voice is in English** — it used to be in
> Japanese, which made the one sentence aimed at someone who cannot follow spoken Japanese
> another thing they could not follow. **On the day the audio is still introduced as a bonus,
> not a feature.** If enough devices turn out to have no Japanese voice, `BROWSER_VOICE=0`
> puts the provider's voice back — and then the limit below applies, so people take turns.
>
> **The other device-side constraint is that it will only speak during a tap** (2026-08-25).
> iOS Safari starts speech only when it was asked for while a tap was being handled, and a
> reply arrives seconds after any tap — so written the obvious way, **every reply is silent on
> an iPhone.** Two answers. **(1) The speaking is done from the page itself
> (`window.parent`) rather than from the frame**, because the frame is rebuilt on every rerun
> and a document milliseconds old has never been tapped. **(2) The first tap on the start
> screen — the press on Start — also asks for one silent utterance, which unlocks the rest.**
> And for whatever still refuses: if the speech has not begun 900ms after it was asked for,
> the screen says to press ▶.

**One person practising for a few turns is enough to get `429 Too Many Requests`.**
Twelve short lines synthesised back to back were refused eleven times (`You exceeded
your current quota`). A later run after a pause succeeded eleven times out of twelve,
so **the limit is per minute rather than per day**.

**Paying (Tier 1) would remove it, and we are not paying.** Speech output is $10.00
per 1M tokens and text input $0.50 per 1M, which for the expected size of this demo
(ten people, five turns each) is a few tens of cents. Staying free was chosen anyway
(decided 2026-08-22).

**So the audio is designed as a bonus rather than as a feature that must work.**

- **A 429 stops synthesis being called for 60 seconds.** A refused request is still a
  request, so asking through the window lengthens it. **The whole process goes quiet**
  — the limit belongs to the API key, and one deployment has one key.
- **The same line is synthesised once per session.**
- **Nothing appears on screen when it does not play.** The reply is on screen as text,
  so the practice still works, and `429 Too Many Requests` is not something a beginner
  can act on. The reason goes to stderr instead.
- **The correction path (the text model) does not hit this. Thirty simultaneous
  corrections all succeeded** (2026-08-22). It is the preview speech model alone that
  is tightly limited.

## Constraints that shaped these choices

- **Free hosting does not guarantee filesystem persistence across restarts.** This once forced
  usage logs into an external database; **with nothing stored at all, the constraint no longer
  applies** (see "The decision to store nothing").
- ~~**Streamlit cannot hold a persistent connection**, so continuous hands-free speech is not
  attempted before 20 September. Reconsidered after applications open (28 September), and only
  if testers actually complain about pressing the button.~~
  → **Built on 2026-08-24.** `streamlit-webrtc` holds the microphone open and a second of
  silence ends the turn. **The constraint was right about Streamlit alone** — it took one
  external component to get around it.
- **The SudachiDict package is ~70MB**, installed at image build time.
- **No local models before 20 September.** The goal is applying LLMs in a product, not
  training them; GPU cost and iteration do not fit a budget of two hours a day (14 a week).
- **Web only, no mobile app.** App Store review costs time unrelated to the job requirements,
  and an install step would collapse the tester count.
- **No UI framework or design system.** Appearance is plain CSS, time-boxed to one hour.

## Build order (revised 2026-08-18)

Vertical slice first: Streamlit talking directly to a text-only dialogue and correction loop,
so the substance is settled. **That part is done.**

After that, **one thing at a time, in series** — even at two hours a day, two cannot move
at once.

1. **Close the evaluation** (through 30 August) — the baseline comparison table, retrieval,
   one improvement cycle
2. **Make it touchable** (through 6 September) — extract FastAPI, wire LangGraph,
   **a public URL**
3. **Move to voice** (through 12 September) — recording, transcription, speech, session flow
4. **Finish** (through 20 September) — act on tester feedback, Docker, complete the README

**The earlier version put voice and the API extraction in the same week.** They were serialised
because running both at once means **arriving at the hand-off date (13 September) with neither
finished**. **Step 2 comes before step 3 because nothing that cannot be touched gets evaluated.**

## Licensing

SudachiPy and SudachiDict are Apache-2.0 with no share-alike condition, so bundling is fine;
the README states source and licence. JMdict and KANJIDIC2 are CC BY-SA and are not bundled.
Commercial textbooks and JLPT past papers are never ingested — difficulty tiers are built here
from word frequency and described as "approximately corresponding to JLPT levels".

**The frequency comes from the BCCWJ word lists** (Balanced Corpus of Contemporary Written
Japanese, NINJAL): short-unit ([DOI 10.15084/00003218](https://doi.org/10.15084/00003218)) and
long-unit ([DOI 10.15084/00003212](https://doi.org/10.15084/00003212)), ver1_0, retrieved
2026-08-11 (added 2026-08-11). **SudachiDict does not carry frequency** — it exposes surface,
lemma, reading and part of speech and nothing else — so tokenization and frequency come from
different sources.

**BCCWJ is not bundled.** NINJAL states it is free for research and educational use and says
nothing about redistribution, so it gets the same handling as JMdict: gitignored, with a fetch
script. `wordfreq` was rejected on two counts — its data is CC BY-SA, and it requires MeCab,
which would put a second tokenizer beside SudachiPy.

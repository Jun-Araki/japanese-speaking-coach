# Architecture

**Translation of [`../ja/architecture.md`](../ja/architecture.md), which is authoritative.** If the two
disagree, the Japanese version is correct and this file needs updating.


> **Thin by design.** The table below is the public extract of the stack decisions.
> **Nothing outside this table is adopted before the end of November.**

## Stack

| Area | Choice | Why |
|---|---|---|
| LLM | **LangChain → Gemini** (decided 2026-08-03) | See "Choosing a provider" below |
| Transcription | **Decided in late October** (Gemini first, OpenAI as fallback) | Same |
| Text to speech | **Decided in late October** (same) | Both support Japanese. **Disclosing that the voice is AI-generated is done regardless of provider** |
| Tokenization | SudachiPy + SudachiDict (Apache-2.0) | Japanese has no spaces between words, so vocabulary-level checking requires morphological analysis |
| Embeddings | sentence-transformers, multilingual | Retrieval over Japanese text |
| Vector store | Chroma | Fastest local option, sufficient for a demo |
| Agent | LangGraph | Dialogue and correction run in parallel with a validation loop back — a real graph, not a chain |
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

**Decided in late October, when voice is built.** Gemini handles both transcription and speech
generation (WAV accepted, Japanese supported) and would keep everything on one key. But
**Gemini transcribes via a prompt — a language model writes the text** — so it may **repair the
learner's mistakes more aggressively than a dedicated speech recogniser would**. That would
erase exactly what this app exists to correct.

> **`.env.example` carries OpenAI's transcription and speech models as candidates** (not wired
> up). Whichever is adopted, **the private planning document and this file are updated together.**

**This has to be decided by argument, not by measurement (revised 2026-08-16).** The original
plan was to measure both transcribers against recordings transcribed by ear; **no audio is
stored now, so that comparison cannot be run.** The decision therefore leans towards a dedicated
speech model, on the reasoning above, and **the README says the choice was not measured.**

## Constraints that shaped these choices

- **Free hosting does not guarantee filesystem persistence across restarts.** This once forced
  usage logs into an external database; **with nothing stored at all, the constraint no longer
  applies** (see "The decision to store nothing").
- **Streamlit cannot hold a persistent connection**, so continuous hands-free speech is not
  attempted before the end of November. Reconsidered in December or later, and only if testers
  actually complain about pressing the button.
- **The SudachiDict package is ~70MB**, installed at image build time.
- **No local models before the end of November.** The goal is applying LLMs in a product, not
  training them; GPU cost and iteration do not fit a budget of six and a half hours a week.
- **Web only, no mobile app.** App Store review costs time unrelated to the job requirements,
  and an install step would collapse the tester count.
- **No UI framework or design system.** Appearance is plain CSS, time-boxed to one hour.

## Build order (revised 2026-08-16)

Vertical slice first: Streamlit talking directly to a text-only dialogue and correction loop,
so the substance is settled. **That part is done.**

After that, **one thing at a time, in series** — at six and a half hours a week, two cannot
move at once.

1. **Close the evaluation** (through mid-September) — the baseline comparison table, retrieval,
   one improvement cycle
2. **Make it touchable** (through mid-October) — extract FastAPI, wire LangGraph, Docker,
   **a public URL**
3. **Move to voice** (through mid-November) — recording, transcription, speech, session flow
4. **Finish** (through end of November) — act on tester feedback, complete the README

**The earlier version put voice and the API extraction in the same week.** That does not survive
six and a half hours a week, so they were serialised. **Step 2 comes before step 3 because
nothing that cannot be touched gets evaluated.**

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

# Architecture

**Translation of [`../ja/architecture.md`](../ja/architecture.md), which is authoritative.** If the two
disagree, the Japanese version is correct and this file needs updating.


> **Thin by design.** The table below is the public extract of the stack decisions.
> **Nothing outside this table is adopted during August.**

## Stack

| Area | Choice | Why |
|---|---|---|
| LLM | **LangChain → Gemini** (decided 2026-08-03) | See "Choosing a provider" below |
| Transcription | **Decided in week 3** (Gemini first, OpenAI as fallback) | Same |
| Text to speech | **Decided in week 3** (same) | Both support Japanese. **Disclosing that the voice is AI-generated is done regardless of provider** |
| Tokenization | SudachiPy + SudachiDict (Apache-2.0) | Japanese has no spaces between words, so vocabulary-level checking requires morphological analysis |
| Embeddings | sentence-transformers, multilingual | Retrieval over Japanese text |
| Vector store | Chroma | Fastest local option, sufficient for a demo |
| Agent | LangGraph | Dialogue and correction run in parallel with a validation loop back — a real graph, not a chain |
| Database | PostgreSQL, free tier (Neon or Supabase) | Consent records and usage logs |
| API | FastAPI | `POST /chat`, `POST /check`, `GET /health` |
| UI | Streamlit | Fastest path to a public demo |
| Container | Docker + compose | `docker compose up` runs UI, API, and database |
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

**The speech provider is decided in week 3, from measurement.** Gemini handles both
transcription and speech generation (WAV accepted, Japanese supported) and would keep
everything on one key. But **Gemini transcribes via a prompt — a language model writes the
text** — so it may **repair the learner's mistakes more aggressively than a dedicated speech
recogniser would**. That would erase exactly what this app exists to correct, so it is
measured under "Evaluation is measured in two stages" before being chosen.

## Constraints that shaped these choices

- **Free hosting does not guarantee filesystem persistence across restarts.** Usage logs go
  to an external database from day one, never to local files, or tester data is lost.
- **Streamlit cannot hold a persistent connection**, so continuous hands-free speech is not
  attempted in August. Reconsidered in November only if testers actually complain about
  pressing the button.
- **The SudachiDict package is ~70MB**, installed at image build time.
- **No local models in August.** The goal is applying LLMs in a product, not training them;
  GPU cost and iteration do not fit a two-hours-a-morning budget.
- **Web only, no mobile app.** App Store review costs time unrelated to the job requirements,
  and an install step would collapse the tester count.
- **No UI framework or design system.** Appearance is plain CSS, time-boxed to one hour.

## Build order

Vertical slice first: Streamlit talking directly to a text-only dialogue and correction loop,
so the substance is settled. Only then move to voice, then extract FastAPI and LangGraph.

## Licensing

SudachiPy and SudachiDict are Apache-2.0 with no share-alike condition, so bundling is fine;
the README states source and licence. JMdict and KANJIDIC2 are CC BY-SA and are not bundled.
Commercial textbooks and JLPT past papers are never ingested — difficulty tiers are derived
from word frequency and described as "approximately corresponding to JLPT levels".

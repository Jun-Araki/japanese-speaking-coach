# Architecture

> **Thin by design.** The table below is the public extract of the stack decisions.
> **Nothing outside this table is adopted during August.**

## Stack

| Area | Choice | Why |
|---|---|---|
| LLM | LangChain → Claude API | Strong Japanese output |
| Transcription | OpenAI transcription endpoint | Accepts the WAV Streamlit produces |
| Text to speech | OpenAI speech endpoint | Japanese support, streaming playback. **Terms require disclosing that the voice is AI-generated** |
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

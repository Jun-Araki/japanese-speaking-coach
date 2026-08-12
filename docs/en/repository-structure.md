# Repository Structure

**Translation of [`../ja/repository-structure.md`](../ja/repository-structure.md), which is authoritative.** If the two
disagree, the Japanese version is correct and this file needs updating.


> **Thin by design.** Directories are listed as they are created. Entries marked *(planned)*
> do not exist yet.

```
japanese-speaking-coach/
├── CLAUDE.md                  Development process rules (Japanese, for the author)
├── README.md                  Public entry point (English)
├── pyproject.toml             Dependencies and tool config (ruff / mypy / pytest)
├── uv.lock                    Pinned dependencies. **Committed**
├── .env.example               Required environment variables; .env is never committed
├── llm.py                     **The only place the provider is chosen.** One line
│                              switches between Gemini and Anthropic
├── docs/                      Permanent documents — what to build and how
│   ├── ja/                    Japanese, authoritative. Edited first
│   └── en/                    English translation. Updated to match ja/
├── config/
│   └── thresholds.toml        Validation thresholds. Never inline these in code
├── .steering/                 Per-task documents, one directory per piece of work
│   └── YYYYMMDD-title/        requirements.md, design.md, tasklist.md
├── app/                       Streamlit UI, single page
│   └── main.py                Conversation screen. **Community Cloud entry point**
├── dialogue/                  Conversation node
│   ├── scenes.py              Scenes and levels. **glossary.md §3 and §4 are the source**
│   └── reply.py               `reply()`. Partner prompt and the one-to-two sentence cap
├── correction/                Correction node
│   ├── engine.py              `check()`. Parses the structured output **itself** and
│   │                          also reports format compliance
│   └── validation.py          Validation node. **Python run after generation**, never a
│                              second call to the model
├── tests/                     pytest. **No tests call the model** — generated Japanese
│                              has no fixed right answer to assert against
├── retrieval/                 (planned) Chroma indexing and search
├── nlp/                       Japanese word processing
│   ├── tokenize.py            SudachiPy tokenization — Japanese writes no word spaces
│   ├── frequency.py           Difficulty tiers, cut from the BCCWJ list by coverage
│   └── level.py               `level_check()`: is this reply above the learner?
├── evals/                     Evaluation scripts, baseline, run records
│   ├── runs/                  One run record JSON per measurement
│   ├── rater/                 The second rater's kit and the returned ratings
│   ├── script.py              Fixed conversation script. **Uses no evaluation item**
│   └── level_compliance.py    Vocabulary level of replies (first shot and after the gate)
├── api/                       (planned) FastAPI application
└── data/
    ├── evaluation/            120 evaluation items as JSON — a public artefact
    │   └── candidates/        Unverified candidates: raw material for items.json, not the record
    ├── grammar/               8 self-written grammar reference articles. **Quotes no
    │                          evaluation item** — pinned by pytest
    ├── frequency/             BCCWJ word lists and the tier tables — **git-ignored**. Not
    │                          bundled: redistribution terms are not stated. Fetch with
    │                          `python -m nlp.frequency --build`
    ├── recordings/            Learner audio — git-ignored, personal data
    └── sessions/              Session exports — git-ignored, personal data
```

## Placement rules

- **`docs/` never describes a single piece of work.** Work-specific material goes in
  `.steering/YYYYMMDD-title/`.
- **Anything containing learner speech or audio is git-ignored.** Only generalised sentences
  reach `data/evaluation/`; no individual's utterance is committed verbatim.
- **Reference material copied from books or articles is not committed** (`Sample/` is ignored)
  — this repository is public and the material is not ours to publish.
- Diagrams live inside the document they belong to; there is no `diagrams/` directory.

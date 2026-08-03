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
├── docs/                      Permanent documents — what to build and how
│   ├── ja/                    Japanese, authoritative. Edited first
│   └── en/                    English translation. Updated to match ja/
├── config/
│   └── thresholds.toml        Validation thresholds. Never inline these in code
├── .steering/                 Per-task documents, one directory per piece of work
│   └── YYYYMMDD-title/        requirements.md, design.md, tasklist.md
├── app/                       Streamlit UI, single page
│   └── audio_check.py         Checks recording and autoplay on iOS Safari.
│                              **Throwaway** — deleted once the result is recorded
├── dialogue/                  (planned) Conversation node
├── correction/                (planned) Correction node and validation
├── retrieval/                 (planned) Chroma indexing and search
├── nlp/                       (planned) SudachiPy tokenization, vocabulary level checks
├── evals/                     (planned) Evaluation scripts, baseline, run records
├── api/                       (planned) FastAPI application
└── data/                      (planned)
    ├── evaluation/            120 evaluation items as JSON — a public artefact
    ├── grammar/               10 self-written grammar reference articles
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

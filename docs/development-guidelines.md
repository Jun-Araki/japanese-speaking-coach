# Development Guidelines

> **Thin by design.** Rules that are already decided. Expanded when code exists to justify it.

## Language

- Python 3.11+
- `ruff` for linting and formatting, `mypy` for type checking — run both after any code change
- Type hints on every public function

## Naming

- `snake_case` for functions, variables, and modules; `PascalCase` for classes
- **Field names in code match the JSON keys exactly** (`needs_correction`, `corrected_sentence`,
  `reason_en`, `grounding_ids`) so evaluation data and code never drift apart
- Domain terms follow [glossary.md](glossary.md). Do not invent synonyms — a "correction" is
  never also called a "fix", a "suggestion", or "feedback" in code

## Structure

- One module per responsibility: `dialogue/`, `correction/`, `retrieval/`, `nlp/`, `evals/`, `app/`, `api/`
- Prompts live in their module as separate files, versioned — every evaluation run records
  which prompt version produced it
- The correction node returns **structured output**; parsing free text is not acceptable

## Testing

- `pytest`. Tests are required for the deterministic parts: validation node, edit distance,
  vocabulary level check, evaluation scoring
- **The scoring script itself gets tests.** A silent scoring bug is indistinguishable from a
  model improvement
- Every evaluation run **hand-checks 5 items** from the test split as a sanity gate
- Model-calling code is tested against recorded responses, not live calls

## Evaluation discipline

- Prompts and thresholds are tuned **only against the dev split**. The test split is touched
  at the beginning and at the end, and nowhere else
- Every run writes a record: model name, prompt version, date, data split
- Every published number carries `n` and an error margin

## Styling

Plain CSS only, no framework. Off-white background, sumi-black text, exactly one accent
colour, serif headings, generous whitespace, thin rules, no shadows. Avoid torii gates,
cherry blossoms, and red-and-gold — Japanese-themed clichés read as cheap instantly.

## Git

- Commit messages in English
- **Commit and push only when explicitly asked**
- `.env` is never committed
- Documents are committed alongside the change they describe, not in a separate cleanup pass

## Security

- Secrets from environment variables only
- Caps on input length, recording length, turns per session, and daily tokens and TTS characters
- Learner audio and transcripts are personal data: consent before storing, no names, a
  documented deletion route

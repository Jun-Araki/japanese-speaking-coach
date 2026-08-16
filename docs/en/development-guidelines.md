# Development Guidelines

**Translation of [`../ja/development-guidelines.md`](../ja/development-guidelines.md), which is authoritative.** If the two
disagree, the Japanese version is correct and this file needs updating.


> **Thin by design.** Rules that are already decided. Expanded when code exists to justify it.

## Language

- Python 3.11+ (**currently 3.12.13**), managed with **`uv`**
  — `uv sync` to install, `uv run <cmd>` to execute. The system Python is left alone
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

## Reviewing your own documents

After updating anything in `docs/`, re-read it against the list below. **Do it the next
morning, not immediately after writing** — while your intent is still fresh in your head,
the gaps are invisible.

To have Claude run the review, ask it to check the document against these six angles and
**report problems and recommendations only**. Do not let it rewrite the document — accepting
edits without judging each finding yourself defeats the purpose.

### Six angles

1. **Is the requirement unambiguous?**
   Could someone start implementing from this text alone, or does it stop at "manages X"?
   *"Adjusts difficulty by level" is not implementable. What is measured, at what threshold,
   and what happens when it is exceeded?*

2. **Is the measurement method written down?**
   Not just a target number — **who measures it, when, on what data, and how it is computed**.
   *[glossary.md](glossary.md) §5 is the only place metrics are defined. Nothing goes in the
   README that is not defined there.*

3. **Are there user stories?**
   Does the document say **why** a feature is needed — what hurts today and how this fixes it?
   *A bare feature list gives no way to decide later whether a feature is still worth keeping.*

4. **Are the non-functional requirements verifiable?**
   Does each number carry an **environment, a method, and a pass condition**?
   *"Under 2 seconds" cannot be verified without knowing where it was measured and over how
   many runs.*

5. **Does the terminology match [glossary.md](glossary.md)?** ← project-specific
   No synonyms introduced, and document terms match the code identifiers.
   *Drift in the labelling scheme corrupts the evaluation data, which is the costliest
   failure available here.*

6. **Are `docs/ja/` and `docs/en/` in step?** ← project-specific
   Sections, tables, and numbers present in both. **Did you change ja and forget en?**

### What to do with the findings

- **Deciding to leave it thin is a valid outcome.** If the answer is "write it once the
  implementation settles", say so in the document. **Do not leave a blank** — a reader
  cannot tell an oversight from a deliberate gap.
- If a finding implies an implementation decision (for example, what to do with malformed
  JSON), **do not stop at fixing the document** — add the corresponding task to the
  tasklist in `.steering/`.

## Git

- Commit messages in English
- **Commit and push only when explicitly asked**
- `.env` is never committed
- Documents are committed alongside the change they describe, not in a separate cleanup pass

## Security

- Secrets from environment variables only
- Caps on input length, recording length, turns per session, and daily tokens and TTS characters
- Learner audio and transcripts are personal data: **they are not stored at all** (decided
  2026-08-16), and no name is kept. **With nothing stored there is no consent record either** —
  only the notice (sent to external APIs, do not speak confidential information, the voice is
  synthetic) and a contact address

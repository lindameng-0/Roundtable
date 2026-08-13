# Phase 2: Reader V2 evaluation

Reader V2 is implemented behind a feature flag. It uses one structured model
call per reader and section. That call returns both the visible reaction and a
small state delta; deterministic code validates paragraph references and merges
bounded continuity state.

## Safe local mode

Keep these values to exercise the full interface without paid calls:

```env
DATABASE_BACKEND=memory
LLM_BACKEND=mock
READER_PIPELINE_VERSION=v2
```

## Live single-provider baseline

Put the relevant API key in `backend/.env`, then use:

```env
LLM_BACKEND=live
READER_PIPELINE_VERSION=v2
READER_MODEL_POOL=gemini:gemini-2.5-flash
EDITOR_MODEL_ROUTE=gemini:gemini-2.5-pro
```

## Live mixed panel

The pool rotates by reader. This example gives the first and third readers
Gemini and the second reader Claude:

```env
READER_MODEL_POOL=gemini:gemini-2.5-flash,anthropic:claude-sonnet-5,gemini:gemini-2.5-flash
EDITOR_MODEL_ROUTE=openai:gpt-5.6-terra
```

Only configure routes for keys you possess. Restart the backend after changing
these settings. Keep API keys server-side; never add them to frontend files.

## Controlled comparison

Start cheaply with two cases and one provider:

```powershell
python backend/evals/run_provider_comparison.py `
  --route gemini:gemini-2.5-flash `
  --case quiet_opening `
  --case continuity_contradiction
```

Add Claude or OpenAI by repeating `--route`. Each result records tokens and an
estimated cost. Generate a human review sheet with:

```powershell
$files = Get-ChildItem backend/evals/results/*.json | ForEach-Object FullName
python backend/evals/evaluate_reader_outputs.py $files `
  --out backend/evals/reader-eval-review.json
```

Score outputs without looking at the provider name first. The six human scores
are authenticity, specificity, usefulness, memory continuity, subtlety of
personality, and whether the reader avoided inventing a problem.

Pricing estimates are application metadata, not billing records. Provider
pricing changes; compare them with the provider invoice before production use.

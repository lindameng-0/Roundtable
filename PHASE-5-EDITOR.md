# Phase 5: Editor quality and delivery

Editor V3's report contract remains unchanged. Phase 5 adds evaluation,
full-novel coverage, and better delivery around it.

## Long manuscripts

Manuscripts up to `EDITOR_DIRECT_MAX_CHARS` use the existing direct Editor V3
call. Larger manuscripts are divided on section/paragraph boundaries. The
cheaper `EDITOR_MAP_MODEL_ROUTE` creates factual, paragraph-grounded story maps
for each chunk; the high-quality `EDITOR_MODEL_ROUTE` then performs one final
cross-chunk synthesis using those maps and reader evidence.

```dotenv
EDITOR_MODEL_ROUTE=openai:gpt-5.6-terra
EDITOR_MAP_MODEL_ROUTE=openai:gpt-5.6-luna
EDITOR_DIRECT_MAX_CHARS=220000
EDITOR_CHUNK_MAX_CHARS=70000
EDITOR_MAX_CHUNKS=16
```

Map calls are included in workflow token/cost accounting. If the configured
chunk maximum is exceeded, report coverage is explicitly marked partial.

## Blinded quality evaluation

Generate the same curated reports with one or more editor routes:

```powershell
python backend/evals/run_editor_comparison.py `
  --route openai:gpt-5.6-terra `
  --route anthropic:claude-sonnet-5
```

Create a provider-blind scoring sheet:

```powershell
$files = Get-ChildItem backend/evals/editor_results/*.json | ForEach-Object FullName
python backend/evals/evaluate_editor_outputs.py $files `
  --out backend/evals/editor-eval-review.json `
  --key-out backend/evals/editor-eval-key.json
```

The automated checks cover grounding, required story topics, false plot-hole
claims, disagreement detection, structural completeness, and estimated cost.
Human scoring covers story understanding, taste-versus-fact judgment,
specificity, prioritization, balance, and usefulness.

## Report delivery

The report page offers **Print / Save PDF** using a dedicated A4 print layout.
It also includes a clickable engagement visualization and an evidence-linked
reader-divergence view. JSON workspace export remains available separately.

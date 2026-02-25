# SousChef Recipe Transformer

This app turns a normal recipe into a SousChef JSON file. It also shows a plain-text version and lets you export files. Use the app here: https://souschef-transformer.streamlit.app/

## Features
- Analyze the recipe, then generate the SousChef output.
- Check the JSON against the schema.
- Fix units like Piece or Sprig to Amount.
- Show a plain-text preview.
- Save JSON and CSV files to the export folder.

## Architecture Overview
The app is a Streamlit UI wrapped around a 5-node LangGraph workflow that
generates, validates, and repairs SousChef recipes.

**Workflow nodes:**
1. **Generate:** Build SousChef JSON using LLM (required for translation quality)
2. **Validate:** Pydantic schema validation
3. **Quality:** Domain checks (units, durations, required text)
4. **Repair:** LLM-based fixes, with max iterations
5. **Export:** Write JSON/CSV to the export folder

**Key principle:** LLM is mandatory for generation and translation. No fallback mode for silent defaults.

Modules:
- `src/main.py`: Streamlit UI and user interaction
- `src/workflow.py`: LangGraph nodes and routing
- `src/utils.py`: Scraping, validation, export helpers

## Setup
1. (Optional) Create a virtual environment.
2. Install packages:
   - `pip install -r requirements.txt`
3. Add your Groq API key to `.env`:
   - `GROQ_API_KEY=your_key_here`

## Run
- `streamlit run src/main.py`
- **Required:** Select a Groq model in the sidebar dropdown (e.g., `llama-3.1-8b-instant`)

## Tests
- `STREAMLIT_E2E=1 pytest -q`

## Input
- Paste a full recipe in the text box.
- Or click `Load sample from recipe.txt` (from the import folder).

## Output
- Plain-text recipe.
- SousChef JSON output.
- Exported JSON and CSV files in the export folder.

## Notes
- **LLM is mandatory** for generation and translation quality. The app will raise an error if no model is configured.
- If units are not allowed, they are normalized to allowed units.
- If parsing or generation fails, the app displays a clear error message.
- Sample input file lives in `import/recipe.txt`.
- Errors propagate to Streamlit for user visibility (no silent fallbacks).

## Phase 4 Evaluation

Evaluation inputs live in `evaluation/recipes.json` and the runner is
`evaluation/run_phase4.py`.

**To run evaluation:**
```bash
python -m evaluation.run_phase4 --model-name <groq-model> [--temperature <value>] [--limit <count>]
```

**Required:** `--model-name` must be provided. No fallback mode.

Run:

```bash
"/Users/qianhonglin/Downloads/DS W4 mid-stake/.venv/bin/python" evaluation/run_phase4.py
```

Results are written to `evaluation/phase4_results.csv`.

### LLM Validation (Groq)

The runner supports LLM-backed validation and includes safe defaults to avoid
rate limits on the free tier:

- `--sleep-seconds 10` (default)
- `--max-repair-iterations 1` (default)

Recommended quick run (fast model, small set):

```bash
export $(cat .env | xargs) && \
   "/Users/qianhonglin/Downloads/DS W4 mid-stake/.venv/bin/python" evaluation/run_phase4.py \
   --recipes-path evaluation/recipes_quick.json \
   --model-name "llama-3.1-8b-instant" \
   --temperature 0.2 \
   --limit 3 \
   --sleep-seconds 10 \
   --max-repair-iterations 1
```

Helpful flags:
- `--limit N` runs only the first N recipes from the list.
- `--skip-urls` skips URL-based recipes.
- `--sleep-seconds` adds a delay between recipes to reduce 429s.
- `--max-repair-iterations` caps repair attempts per recipe.

Latest run (2026-02-21):
- Recipes: 10
- Success: 10
- Failures: 0
- LLM used: false (fallback mode)

## Phase 5 Notes
- README updated with architecture and test instructions.
- Workflow comments added in `src/workflow.py`.
- LLM-backed evaluation still pending due to rate limits.

# SousChef Recipe Transformer

Streamlit app that converts recipe text, URLs, or uploaded files into SousChef JSON and CSV outputs using Groq-hosted LLMs. Live app: https://souschef-transformer.streamlit.app/

## What it does
1. Add recipes (upload, URL fetch, or paste text).
2. Transform recipes (condense + analyze).
3. Generate SousChef JSON and export JSON/CSV.

## Features
- Upload TXT, PDF, or DOCX files and extract recipe text.
- Fetch recipes from URLs.
- Paste raw recipe text and label it.
- Multi-select recipes, delete any, and process in batches.
- Preview generated JSON or CSV and download from the UI.
- Enforces SousChef output rules in SOUSCHEF_OUTPUT_SPEC.md.

## Setup
1. (Optional) Create a virtual environment.
2. Install packages:
   - `pip install -r requirements.txt`
3. Add your Groq API key to `.env`:
   - `GROQ_API_KEY=your_key_here`

## Run
- `streamlit run src/main.py`
- Choose a model in the sidebar (default: `llama-3.1-8b-instant`).

## Project layout
- `app.py`: LLM orchestration, recipe parsing, validation, and SousChef schema logic.
- `src/main.py`: Streamlit UI and multi-step workflow.
- `src/workflow.py`: Optional LangGraph pipeline (condense, generate, validate, quality, repair, export).
- `SOUSCHEF_OUTPUT_SPEC.md`: Output rules and schema requirements.

## Notes
- LLM access is required; the app will error if no model is configured.
- Generation can take several minutes per recipe with free-tier rate limits.
- Output strings must be single-line and match the SousChef specification.

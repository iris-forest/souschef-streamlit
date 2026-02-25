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
5. **Export:** Write JSON/CSV

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
- Select a Groq model in the sidebar dropdown (default is `llama-3.1-8b-instant`)

## Input
- Paste a full recipe in the text box.
- Add one or multiple links in the url box
- Import a document
  
## Output
- SousChef JSON or CSV output.

## Notes
- **LLM is mandatory** for generation and translation quality. The app will raise an error if no model is configured.
- If units are not allowed, they are normalized to allowed units.
- If parsing or generation fails, the app displays a clear error message.
- Sample input file lives in `import/recipe.txt`.
- Errors propagate to Streamlit for user visibility (no silent fallbacks).

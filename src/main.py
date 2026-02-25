import csv
import io
import json
import os
import sys
import uuid
from typing import Dict, List

import streamlit as st
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app import (
    extract_recipe_text_from_url,
    extract_recipe_title_from_url,
    build_llm,
    condense_recipe_text,
    analyze_recipe,
    generate_souschef_recipe,
    DEFAULT_RECIPE_CHAR_LIMIT,
)





def _ensure_state() -> None:
    if "recipes" not in st.session_state:
        st.session_state.recipes = []
    if "analyzed_recipes" not in st.session_state:
        st.session_state.analyzed_recipes = {}
    if "transformed_recipes" not in st.session_state:
        st.session_state.transformed_recipes = {}
    if "select_all_recipes_last" not in st.session_state:
        st.session_state.select_all_recipes_last = False
    if "uploaded_file_names" not in st.session_state:
        st.session_state.uploaded_file_names = set()
    if "output_format" not in st.session_state:
        st.session_state.output_format = "json"
    if "output_ready" not in st.session_state:
        st.session_state.output_ready = False


def _load_model_options() -> List[str]:
    env_value = os.getenv("GROQ_MODELS", "").strip()
    if env_value:
        models = [item.strip() for item in env_value.split(",") if item.strip()]
    else:
        models = [
            "gemma2-9b-it",
            "llama-3.1-70b-versatile",
            "llama-3.1-8b-instant",
            "llama-3.3-70b-versatile",
            "mixtral-8x7b-32768",
        ]
    return models


def _add_recipe(name: str, text: str, source: str) -> None:
    recipe_id = uuid.uuid4().hex
    st.session_state.recipes.append(
        {
            "id": recipe_id,
            "name": name,
            "text": text,
            "source": source,
        }
    )


def _delete_recipe(recipe_id: str) -> None:
    """Delete a recipe and clean up related session state."""
    st.session_state.recipes = [
        r for r in st.session_state.recipes if r["id"] != recipe_id
    ]
    # Clean up session state variables related to this recipe
    if f"recipe_select_{recipe_id}" in st.session_state:
        del st.session_state[f"recipe_select_{recipe_id}"]
    if f"analyzed_select_{recipe_id}" in st.session_state:
        del st.session_state[f"analyzed_select_{recipe_id}"]
    if f"transformed_select_{recipe_id}" in st.session_state:
        del st.session_state[f"transformed_select_{recipe_id}"]
    if recipe_id in st.session_state.analyzed_recipes:
        del st.session_state.analyzed_recipes[recipe_id]
    if recipe_id in st.session_state.transformed_recipes:
        del st.session_state.transformed_recipes[recipe_id]


def _extract_docx_text(file_bytes: bytes) -> str:
    try:
        import docx
    except ImportError as exc:
        raise RuntimeError("python-docx is required to read DOCX files.") from exc

    file_stream = io.BytesIO(file_bytes)
    document = docx.Document(file_stream)
    return "\n".join(p.text for p in document.paragraphs if p.text.strip())


def _extract_pdf_text(file_bytes: bytes) -> str:
    try:
        import PyPDF2
    except ImportError as exc:
        raise RuntimeError("PyPDF2 is required to read PDF files.") from exc

    reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            pages.append(text)
    return "\n".join(pages)


def _extract_uploaded_text(uploaded_file) -> str:
    file_name = uploaded_file.name
    file_bytes = uploaded_file.getvalue()
    _, ext = os.path.splitext(file_name.lower())
    if ext == ".txt":
        return file_bytes.decode("utf-8", errors="ignore")
    if ext == ".docx":
        return _extract_docx_text(file_bytes)
    if ext == ".pdf":
        return _extract_pdf_text(file_bytes)
    raise RuntimeError(f"Unsupported file type: {ext}")


def _fallback_title_from_url(url_value: str) -> str:
    slug = url_value.strip().split("/")[-1]
    slug = slug.split("?")[0].split("#")[0]
    cleaned = " ".join(slug.replace("_", " ").replace("-", " ").split())
    return cleaned or "Recipe URL"


def _build_csv_for_recipes(recipes: List) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "step_number",
            "display_name_en",
            "action_en",
            "instructions_en",
            "duration_seconds",
            "recipe_variant",
            "ingredients",
            "recipe_name",
        ]
    )
    for recipe in recipes:
        recipe_name = recipe.generic_name.en if recipe.generic_name else "Recipe"
        for step in recipe.steps_part_1:
            ingredients = []
            for item in step.ingredient or []:
                ingredients.append(f"{item.amount} {item.metric_unit} {item.ingredient}")
            writer.writerow(
                [
                    step.step_number or "",
                    step.display_name.en if step.display_name else "",
                    step.action.en if step.action else "",
                    step.instructions.en if step.instructions else "",
                    step.duration,
                    ", ".join(step.recipe_variant),
                    "; ".join(ingredients),
                    recipe_name,
                ]
            )
    return output.getvalue()


def _analyze_recipes(
    recipe_ids: List[str],
    recipes_by_id: Dict[str, dict],
    model_name: str,
    temperature: float,
) -> None:
    """Step 1: Condense and analyze recipes (triggered on Transform button)."""
    if not model_name.strip():
        st.error(
            "Model name is required to transform recipes. Please select a model in the sidebar dropdown."
        )
        return
    
    llm = build_llm(model_name.strip(), float(temperature), 1024)
    
    # Create progress bar and status container
    progress_bar = st.progress(0)
    status_text = st.empty()
    errors = []
    
    for idx, recipe_id in enumerate(recipe_ids):
        recipe_entry = recipes_by_id[recipe_id]
        
        # Update progress
        progress = (idx) / len(recipe_ids)
        status_text.text(f"Analyzing {recipe_entry['name']}...")
        progress_bar.progress(progress)
        
        try:
            # Step 1: Condense recipe text
            condensed_text = condense_recipe_text(llm, recipe_entry["text"], DEFAULT_RECIPE_CHAR_LIMIT)
            # Step 2: Analyze condensed recipe
            analysis = analyze_recipe(llm, condensed_text)
            
            st.session_state.analyzed_recipes[recipe_id] = {
                "name": recipe_entry["name"],
                "condensed_text": condensed_text,
                "analysis": analysis,
            }
        except Exception as e:
            errors.append((recipe_entry['name'], str(e)))
    
    # Show final success/error state
    progress_bar.progress(1.0)
    status_text.empty()
    
    if errors:
        for recipe_name, error_msg in errors:
            st.error(f"✗ Failed to analyze {recipe_name}: {error_msg}")
        st.success(f"✓ Analyzed {len(recipe_ids) - len(errors)}/{len(recipe_ids)} recipes")
    else:
        st.success(f"✓ All {len(recipe_ids)} recipes analyzed successfully!")


def _generate_json_recipes(
    recipe_ids: List[str],
    recipes_by_id: Dict[str, dict],
    model_name: str,
    temperature: float,
    max_tokens: int,
) -> None:
    """Step 2: Generate SousChef JSON and export (triggered on Download button)."""
    if not model_name.strip():
        st.error(
            "Model name is required to generate recipes. Please select a model in the sidebar dropdown."
        )
        return
    
    llm = build_llm(model_name.strip(), float(temperature), max_tokens)
    
    # Create progress bar and status container
    progress_bar = st.progress(0)
    status_text = st.empty()
    errors = []
    successful = 0
    
    for idx, recipe_id in enumerate(recipe_ids):
        if recipe_id not in st.session_state.analyzed_recipes:
            errors.append(("Unknown recipe", "Not analyzed - please transform first"))
            continue
        
        analyzed = st.session_state.analyzed_recipes[recipe_id]
        recipe_name = analyzed["name"]
        
        # Update progress
        progress = idx / len(recipe_ids)
        status_text.text(f"Generating JSON for {recipe_name}...")
        progress_bar.progress(progress)
        
        try:
            # Generate SousChef recipe from condensed text and analysis
            recipe = generate_souschef_recipe(
                llm,
                analyzed["condensed_text"],
                analyzed["analysis"],
                max_tokens=int(max_tokens),
            )
            
            try:
                json_text = recipe.model_dump_json(by_alias=True, indent=2)
            except Exception as json_err:
                raise
            
            csv_text = _build_csv_for_recipes([recipe])
            st.session_state.transformed_recipes[recipe_id] = {
                "recipe": recipe,
                "json": json_text,
                "csv": csv_text,
            }
            successful += 1
        except Exception as e:
            errors.append((recipe_name, str(e)))
    
    # Show final progress
    progress_bar.progress(1.0)
    status_text.empty()
    
    if errors:
        for recipe_name, error_msg in errors:
            st.error(f"✗ Failed to generate JSON for {recipe_name}: {error_msg}")
    
    if successful > 0:
        st.success(f"✓ Generated JSON for {successful}/{len(recipe_ids)} recipes!")


def main() -> None:
    load_dotenv(".env", override=True)
    st.set_page_config(page_title="SousChef Recipe Transformer", layout="wide")
    st.title("SousChef Recipe Transformer")

    _ensure_state()

    with st.sidebar:
        st.header("Model settings")
        model_options = ["Select a model"] + _load_model_options()
        default_model = "llama-3.1-8b-instant"
        default_index = (
            model_options.index(default_model)
            if default_model in model_options
            else 0
        )
        selected_model = st.selectbox("Model name", model_options, index=default_index)
        model_name = "" if selected_model == "Select a model" else selected_model
        temperature = st.slider("Temperature", 0.0, 1.0, 0.3, 0.05)
        max_tokens = st.slider("Max output tokens", 500, 4000, 2000, 100)

    st.subheader("1️⃣ Add Recipes")
    section1_left = st.container()

    with section1_left:
        upload_tab, url_tab, text_tab = st.tabs(
            ["Upload file", "From URL", "Paste text"]
        )

        with upload_tab:
            uploaded_files = st.file_uploader(
                "Upload TXT, PDF, or DOCX files",
                type=["txt", "pdf", "docx"],
                accept_multiple_files=True,
            )
            if uploaded_files:
                for uploaded_file in uploaded_files:
                    if uploaded_file.name in st.session_state.uploaded_file_names:
                        continue
                    try:
                        text = _extract_uploaded_text(uploaded_file)
                    except Exception as exc:
                        st.error(f"Could not read {uploaded_file.name}: {exc}")
                        continue
                    if text.strip():
                        _add_recipe(uploaded_file.name, text.strip(), "upload")
                        st.session_state.uploaded_file_names.add(uploaded_file.name)
                    else:
                        st.warning(
                            f"No readable text found in {uploaded_file.name}."
                        )

        with url_tab:
            st.write("Enter recipe URLs (one per line) and click 'Fetch URLs':")
            with st.form(key="url_recipe_form", clear_on_submit=True):
                urls_text = st.text_area(
                    "Recipe URLs", 
                    key="recipe_urls",
                    height=120,
                    placeholder="https://example.com/recipe1\nhttps://example.com/recipe2\nhttps://example.com/recipe3"
                )
                fetch_clicked = st.form_submit_button("Fetch URLs")

            if fetch_clicked:
                urls = [url.strip() for url in urls_text.strip().split('\n') if url.strip()]
                if not urls:
                    st.warning("Please enter at least one URL first.")
                else:
                    # Create progress bar and status container
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    errors = []
                    successful = 0
                    
                    for idx, url in enumerate(urls):
                        # Update progress
                        progress = idx / len(urls)
                        status_text.text(f"Fetching {idx + 1}/{len(urls)}: {url[:50]}...")
                        progress_bar.progress(progress)
                        
                        try:
                            extracted = extract_recipe_text_from_url(url)
                            title = extract_recipe_title_from_url(url)
                            name = title or _fallback_title_from_url(url)
                            _add_recipe(name, extracted.strip(), "url")
                            successful += 1
                        except Exception as exc:
                            errors.append((url, str(exc)))
                    
                    # Show final progress
                    progress_bar.progress(1.0)
                    status_text.empty()
                    
                    if errors:
                        for url, error_msg in errors:
                            st.error(f"✗ Could not fetch {url}: {error_msg}")
                    
                    if successful > 0:
                        st.success(f"✓ Successfully loaded {successful}/{len(urls)} recipes!")
                        st.rerun()

        with text_tab:
            with st.form(key="text_recipe_form", clear_on_submit=True):
                recipe_name = st.text_input(
                    "Recipe name (optional)", key="recipe_text_name"
                )
                recipe_text = st.text_area("Recipe text", key="recipe_text_body")
                add_col, clear_col = st.columns([1, 1])
                with add_col:
                    add_text_clicked = st.form_submit_button("Add text recipe")
                with clear_col:
                    clear_text_clicked = st.form_submit_button("Clear")
                
                if add_text_clicked:
                    if not recipe_text.strip():
                        st.warning("Please paste recipe text first.")
                    else:
                        name = recipe_name.strip() or "Pasted recipe"
                        _add_recipe(name, recipe_text.strip(), "text")
                
                if clear_text_clicked:
                    pass  # Form will auto-clear with clear_on_submit=True

        st.subheader("Your Recipes")
        recipes = st.session_state.recipes
        recipes_by_id = {recipe["id"]: recipe for recipe in recipes}

        select_all = st.checkbox("Select All", key="select_all_recipes")
        if select_all != st.session_state.select_all_recipes_last:
            for recipe in recipes:
                st.session_state[f"recipe_select_{recipe['id']}"] = select_all
            st.session_state.select_all_recipes_last = select_all

        with st.container(border=True):
            selected_recipe_ids = []
            for recipe in recipes:
                if select_all and f"recipe_select_{recipe['id']}" not in st.session_state:
                    st.session_state[f"recipe_select_{recipe['id']}"] = True
                col1, col2, col3 = st.columns([0.6, 0.2, 0.2])
                with col1:
                    selected = st.checkbox(
                        recipe["name"],
                        key=f"recipe_select_{recipe['id']}",
                    )
                    if selected:
                        selected_recipe_ids.append(recipe["id"])
                with col3:
                    if st.button("🗑️ Delete", key=f"delete_{recipe['id']}", help="Delete this recipe"):
                        _delete_recipe(recipe["id"])
                        st.rerun()

        transform_clicked = st.button("Transform")

        if transform_clicked:
            if not selected_recipe_ids:
                st.warning("Select at least one recipe to transform.")
            else:
                _analyze_recipes(
                    selected_recipe_ids,
                    recipes_by_id,
                    model_name,
                    temperature,
                )
                for recipe_id in selected_recipe_ids:
                    st.session_state[f"analyzed_select_{recipe_id}"] = True

    st.divider()
    st.subheader("2️⃣ Generate JSON")
    
    # Show analyzed recipes and generate button
    analyzed_recipes = st.session_state.analyzed_recipes
    if analyzed_recipes:
        st.write("Analyzed recipes ready to generate JSON:")
        analyzed_selected_ids = []
        for recipe_id, data in analyzed_recipes.items():
            selected = st.checkbox(
                data["name"],
                key=f"analyzed_select_{recipe_id}",
            )
            if selected:
                analyzed_selected_ids.append(recipe_id)
        
        if st.button("Generate JSON"):
            if not analyzed_selected_ids:
                st.warning("Select at least one recipe to generate JSON.")
            else:
                _generate_json_recipes(
                    analyzed_selected_ids,
                    recipes_by_id,
                    model_name,
                    temperature,
                    max_tokens,
                )
                st.session_state.output_ready = True
                for recipe_id in analyzed_selected_ids:
                    st.session_state[f"transformed_select_{recipe_id}"] = True
        
        st.caption("⏱️ Note: Generation can take 3-5 minutes per recipe due to free tier LLM rate limiting. Please be patient while the API processes your requests.")
    else:
        st.info("Transform recipes first to generate JSON.")
    
    st.divider()
    st.subheader("3️⃣ Export")
    section2_left, section2_right = st.columns([1, 1], gap="large")

    with section2_left:
        st.subheader("Generated Recipes")
        transformed_recipes = st.session_state.transformed_recipes
        transformed_selected_ids = []
        for recipe_id, payload in transformed_recipes.items():
            name = recipes_by_id.get(recipe_id, {}).get("name", "Recipe")
            selected = st.checkbox(
                name,
                key=f"transformed_select_{recipe_id}",
            )
            if selected:
                transformed_selected_ids.append(recipe_id)

    with section2_right:
        st.subheader("Output Preview")
        format_choice = st.radio(
            "Output format",
            ["json", "csv"],
            horizontal=True,
            key="output_format_choice",
        )
        st.session_state.output_format = format_choice

        if st.session_state.output_ready and transformed_selected_ids:
            export_recipes = [
                transformed_recipes[recipe_id]["recipe"]
                for recipe_id in transformed_selected_ids
            ]
            
            # Set sequential Order numbers for multiple recipes
            if len(export_recipes) > 1:
                export_recipes_with_order = []
                for order_num, recipe in enumerate(export_recipes, start=1):
                    # Update the Order field
                    recipe_dict = recipe.model_dump()
                    recipe_dict["Order"] = order_num
                    export_recipes_with_order.append(recipe_dict)
                export_recipes_ordered = export_recipes_with_order
            else:
                export_recipes_ordered = [recipe.model_dump() for recipe in export_recipes]
            
            if st.session_state.output_format == "csv":
                # For CSV, we still use the original recipes for structure
                export_payload = _build_csv_for_recipes(export_recipes)
                file_name = "souschef_recipes.csv"
                mime_type = "text/csv"
            else:
                if len(export_recipes_ordered) == 1:
                    export_payload = json.dumps(export_recipes_ordered[0], indent=2)
                    file_name = "souschef_recipe.json"
                else:
                    export_payload = json.dumps(export_recipes_ordered, indent=2)
                    file_name = "souschef_recipes.json"
                mime_type = "application/json"

            st.download_button(
                "Export",
                data=export_payload,
                file_name=file_name,
                mime=mime_type,
            )

        if not transformed_selected_ids:
            st.write("Select transformed recipes to see output preview.")
        else:
            selected_recipes = [
                transformed_recipes[recipe_id]["recipe"]
                for recipe_id in transformed_selected_ids
            ]
            if st.session_state.output_format == "csv":
                csv_payload = _build_csv_for_recipes(selected_recipes)
                st.code(csv_payload, language="text")
            else:
                # Set sequential Order numbers for preview as well
                if len(selected_recipes) > 1:
                    preview_recipes = []
                    for order_num, recipe in enumerate(selected_recipes, start=1):
                        recipe_dict = recipe.model_dump(by_alias=True)
                        recipe_dict["Order"] = order_num
                        preview_recipes.append(recipe_dict)
                    json_payload = preview_recipes
                else:
                    json_payload = [
                        recipe.model_dump(by_alias=True) for recipe in selected_recipes
                    ]
                if len(json_payload) == 1:
                    st.code(json.dumps(json_payload[0], indent=2), language="json")
                else:
                    st.code(json.dumps(json_payload, indent=2), language="json")


if __name__ == "__main__":
    main()

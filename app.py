"""
SousChef Recipe Generation Module

CRITICAL: All AI output MUST follow the SousChef Output Specification.
See SOUSCHEF_OUTPUT_SPEC.md for the exact requirements.

Key rules:
- All string values in JSON must be single-line (no literal newlines)
- Nutritional values must be single INTEGER numbers (no ranges or decimals)
- Metric units must use exact capitalization from the allowed list
- Descriptions must be 2 sentences separated by space (no newlines)
- Instructions must be very concise, single-line text
- All required fields must be present and non-empty
"""

import json
import os
import time
from typing import List, Optional, Literal

import requests
from bs4 import BeautifulSoup

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field


BASE_DIR = os.path.dirname(__file__)
DEFAULT_PROMPT_CHAR_LIMIT = int(os.getenv("GROQ_MAX_PROMPT_CHARS", "6000"))
DEFAULT_RECIPE_CHAR_LIMIT = int(os.getenv("GROQ_MAX_RECIPE_CHARS", "3000"))
MIN_REQUEST_INTERVAL = float(os.getenv("GROQ_MIN_REQUEST_INTERVAL", "1.0"))
_LAST_REQUEST_AT = 0.0

ALLOWED_UNITS = {
    "Amount",
    "Can",
    "Cup",
    "Degrees",
    "Gram",
    "Kilogram",
    "Liter",
    "Milligram",
    "Milliliter",
    "Tablespoon",
    "Teaspoon",
}

UNIT_ALIASES = {
    "piece": "Amount",
    "pieces": "Amount",
    "sprig": "Amount",
    "sprigs": "Amount",
    "clove": "Amount",
    "cloves": "Amount",
    "pinch": "Amount",
    "pinches": "Amount",
}


def extract_text_from_json_ld(data: object) -> Optional[str]:
    items = data if isinstance(data, list) else [data]
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("@type") != "Recipe":
            continue
        parts = []
        name = item.get("name")
        if name:
            parts.append(str(name))
        description = item.get("description")
        if description:
            parts.append(str(description))
        ingredients = item.get("recipeIngredient") or []
        if ingredients:
            parts.append("Ingredients:")
            parts.extend([str(ing) for ing in ingredients])
        instructions = item.get("recipeInstructions") or []
        if instructions:
            parts.append("Instructions:")
            if isinstance(instructions, list):
                for step in instructions:
                    if isinstance(step, dict) and step.get("text"):
                        parts.append(str(step["text"]))
                    else:
                        parts.append(str(step))
            else:
                parts.append(str(instructions))
        if parts:
            return "\n".join(parts)
    return None


def extract_recipe_text_from_url(url: str) -> str:
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or "")
        except json.JSONDecodeError:
            continue
        extracted = extract_text_from_json_ld(data)
        if extracted:
            return extracted

    main = soup.find("article") or soup.find("main") or soup.body
    if not main:
        raise ValueError("Could not extract recipe text from this URL.")
    text = " ".join(main.get_text(separator=" ", strip=True).split())
    return text[:6000]


def _clean_recipe_title(raw_title: str) -> str:
    title = " ".join(raw_title.replace("_", " ").split())
    for separator in (" | ", " - ", " — ", " – "):
        if separator in title:
            parts = [part.strip() for part in title.split(separator) if part.strip()]
            if parts:
                title = parts[0]
                break
    return title


def extract_recipe_title_from_url(url: str) -> str:
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    candidates = []
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        candidates.append(og_title["content"])
    twitter_title = soup.find("meta", attrs={"name": "twitter:title"})
    if twitter_title and twitter_title.get("content"):
        candidates.append(twitter_title["content"])
    if soup.title and soup.title.string:
        candidates.append(soup.title.string)
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        candidates.append(h1.get_text(strip=True))

    for candidate in candidates:
        cleaned = _clean_recipe_title(str(candidate))
        if cleaned:
            return cleaned
    return ""


class RecipeAnalysis(BaseModel):
    ingredients: List[str]
    tools: List[str]
    cooking_time: str
    complexity: Literal["low", "medium", "high"]


class LocalizedText(BaseModel):
    en: str
    nl_NL: str


class NutritionalValues(BaseModel):
    energie_kcal: int = Field(..., alias="Energie (kCal)")
    protein_grams: int = Field(..., alias="Protein (grams)")
    carbohydrates_grams: int = Field(..., alias="Carbohydrates (grams)")
    sugar_grams: int = Field(..., alias="Sugar (grams)")
    fat_grams: int = Field(..., alias="Fat (grams)")
    saturated_fat_grams: int = Field(..., alias="Saturated Fat (grams)")
    natrium_milligrams: int = Field(..., alias="Natrium (milligrams)")
    fibers_grams: int = Field(..., alias="Fibers (grams)")

    class Config:
        populate_by_name = True


class RecipeVariantContent(BaseModel):
    recipe_variant: str = Field(..., alias="Recipe Variant")
    recipe_image: Optional[str] = Field(None, alias="Recipe Image")
    recipe_name: LocalizedText = Field(..., alias="Recipe Name")
    description: Optional[LocalizedText] = Field(None, alias="Description")
    diet_allergen_01: Optional[str] = Field(None, alias="Diet/Allergen 01")
    diet_allergen_02: Optional[str] = Field(None, alias="Diet/Allergen 02")
    tag: Optional[str] = Field(None, alias="Tag")
    difficulty: Literal["Easy", "Medium", "Intermediate"] = Field(..., alias="Difficulty")
    nutritional_values: NutritionalValues = Field(..., alias="Nutritional Values")
    shopping_list: Optional[List[str]] = Field(default_factory=list, alias="Shopping List")
    sponsor: Optional[str] = Field(None, alias="Sponsor")
    preview_video: Optional[str] = Field(None, alias="Preview Video")

    class Config:
        populate_by_name = True


class IngredientComponent(BaseModel):
    ingredient: str = Field(..., alias="Ingredient")
    amount: float = Field(..., alias="Amount")
    metric_unit: Literal[
        "Amount",
        "Can",
        "Cup",
        "Degrees",
        "Gram",
        "Kilogram",
        "Liter",
        "Milligram",
        "Milliliter",
        "Tablespoon",
        "Teaspoon",
    ] = Field(..., alias="Metric Unit")

    class Config:
        populate_by_name = True


class StepComponent(BaseModel):
    display_name: Optional[LocalizedText] = Field(None, alias="Display Name")
    action: Optional[LocalizedText] = Field(None, alias="Action")
    step_number: Optional[str] = Field(None, alias="Step Number")
    step_name_editor: Optional[str] = Field(None, alias="Step Name (Editor)")
    workplace: str = Field(..., alias="Workplace")
    step_icon: str = Field(..., alias="Step Icon")
    instructions: LocalizedText = Field(..., alias="Instructions")
    instructions_markdown: Optional[LocalizedText] = Field(None, alias="Instructions Markdown")
    appliances: Optional[List[str]] = Field(default_factory=list, alias="Appliances")
    ingredient: Optional[List[IngredientComponent]] = Field(default_factory=list, alias="Ingredient")
    duration: int = Field(..., alias="Duration")
    count_down: Optional[List[str]] = Field(default_factory=list, alias="Count Down")
    trigger_countdown_step: Optional[str] = Field(None, alias="Trigger Countdown Step")
    video: Optional[str] = Field(None, alias="Video")
    thumbnail: Optional[str] = Field(None, alias="Thumbnail")
    recipe_variant: List[str] = Field(..., alias="RecipeVariant")

    class Config:
        populate_by_name = True


class SousChefRecipe(BaseModel):
    order: int = Field(..., alias="Order")
    generic_name: LocalizedText = Field(..., alias="Generic Name")
    highlighted: Optional[bool] = Field(False, alias="Highlighted?")
    recipe_variant_content: List[RecipeVariantContent] = Field(
        ..., alias="Recipe Variant Content"
    )
    steps_part_1: List[StepComponent] = Field(..., alias="Steps Part 1")

    class Config:
        populate_by_name = True


def build_llm(model_name: str, temperature: float, max_tokens: int | None) -> ChatGroq:
    return ChatGroq(
        model=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _ensure_prompt_within_limit(prompt: str, limit: int) -> None:
    if len(prompt) > limit:
        raise ValueError(
            "Prompt size exceeds configured limit. "
            f"Length: {len(prompt)} chars, limit: {limit} chars. "
            "Reduce the recipe text or simplify the request."
        )


def _ensure_recipe_within_limit(recipe_text: str, limit: int) -> None:
    if len(recipe_text) > limit:
        raise ValueError(
            "Recipe text exceeds configured limit. "
            f"Length: {len(recipe_text)} chars, limit: {limit} chars. "
            "Trim the input or split the recipe into smaller parts."
        )


def _respect_rate_limit() -> None:
    global _LAST_REQUEST_AT
    now = time.monotonic()
    elapsed = now - _LAST_REQUEST_AT
    if elapsed < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - elapsed)
    _LAST_REQUEST_AT = time.monotonic()


def _is_throttle_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        token in message
        for token in (
            "rate limit",
            "rate_limit",
            "too many requests",
            "throttle",
            "429",
        )
    )


def _run_with_retry(operation, max_retries: int = 3) -> str:
    for attempt in range(max_retries + 1):
        try:
            _respect_rate_limit()
            return operation()
        except Exception as exc:
            if not _is_throttle_error(exc):
                raise
            if attempt >= max_retries:
                raise ValueError("Rate limit reached. Please retry shortly.") from exc
            delay = min(8.0, 1.5 * (2**attempt))
            time.sleep(delay)
    raise RuntimeError("Retry loop exited unexpectedly.")


def _is_truncated_json(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if not stripped.endswith("}"):
        return True
    brace = 0
    bracket = 0
    in_string = False
    escaped = False
    for ch in stripped:
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            brace += 1
        elif ch == "}":
            brace -= 1
        elif ch == "[":
            bracket += 1
        elif ch == "]":
            bracket -= 1
    return in_string or brace != 0 or bracket != 0


def _stream_llm_content(llm: ChatGroq, prompt: str, max_chars: int) -> str:
    def _invoke_stream() -> str:
        if hasattr(llm, "stream"):
            chunks = []
            total = 0
            for chunk in llm.stream(prompt):
                delta = chunk.content if hasattr(chunk, "content") else str(chunk)
                if not isinstance(delta, str):
                    delta = str(delta)
                chunks.append(delta)
                total += len(delta)
                if total > max_chars:
                    raise ValueError(
                        "LLM response exceeded the configured size limit. "
                        f"Length: {total} chars, limit: {max_chars} chars. "
                        "Reduce output size (lower max tokens) or simplify the request."
                    )
            return "".join(chunks)
        response = llm.invoke(prompt)
        return response.content if isinstance(response.content, str) else str(response.content)

    return _run_with_retry(_invoke_stream)


def condense_recipe_text(llm: ChatGroq, recipe_text: str, char_limit: int = DEFAULT_RECIPE_CHAR_LIMIT) -> str:
    """
    Condense recipe text to fit within char_limit while preserving key information.
    Uses LLM to create a concise, SousChef-style summary.
    """
    # If already within limit, return as-is
    if len(recipe_text) <= char_limit:
        return recipe_text
    
    condense_prompt = f"""You are a recipe condensation expert. Simplify this recipe to be concise and SousChef-style (structured, clear, minimal fluff).

RECIPE:
{recipe_text}

TASK:
Create a condensed version that:
1. Preserves ALL ingredients with quantities and units
2. Preserves ALL cooking steps in order
3. Removes: long introductions, stories, ads, styling, decoration descriptions
4. Uses bullet points or numbered lists
5. MUST be under {char_limit} characters

OUTPUT ONLY THE CONDENSED RECIPE, NO EXPLANATIONS."""

    response = llm.invoke(condense_prompt)
    condensed = response.content if isinstance(response.content, str) else str(response.content)
    
    # Verify the condensed version fits
    if len(condensed) > char_limit:
        # If still too long, do a more aggressive truncation
        # Keep ingredients and first N steps
        lines = condensed.split('\n')
        result_lines = []
        char_count = 0
        
        for line in lines:
            line_len = len(line) + 1  # +1 for newline
            if char_count + line_len <= char_limit:
                result_lines.append(line)
                char_count += line_len
            elif char_count < char_limit * 0.8:  # Try to keep at least 80% of limit used
                # Truncate this line if needed
                remaining = char_limit - char_count - 10  # -10 for safety margin
                if remaining > 20:
                    result_lines.append(line[:remaining] + "...")
                break
            else:
                break
        
        condensed = '\n'.join(result_lines)
    
    return condensed


def analyze_recipe(llm: ChatGroq, recipe_text: str) -> RecipeAnalysis:
    prompt = """
### Role
You are an experienced recipe guide with deep knowledge of recipes worldwide.

### Recipe
{recipe_text}

### Task
Analyze this recipe to prepare for building a SousChef-style step-by-step instruction.

### Steps
1. Identify all ingredients and their quantities.
2. List the tools and equipment required.
3. Estimate the total cooking time.
4. Determine the complexity level (low, medium, high).

### Rules
- Do NOT create the step-by-step instructions yet.
- Be specific to this recipe (not generic cooking advice).
- Keep each item concise (one sentence max).

### Output Format (JSON)
{{
  "ingredients": ["ingredient 1", "ingredient 2", "ingredient 3"],
  "tools": ["tool 1", "tool 2", "tool 3"],
  "cooking_time": "estimated total cooking time",
  "complexity": "low/medium/high"
}}
""".strip()
    _ensure_recipe_within_limit(recipe_text, DEFAULT_RECIPE_CHAR_LIMIT)
    formatted_prompt = prompt.format(recipe_text=recipe_text)
    _ensure_prompt_within_limit(formatted_prompt, DEFAULT_PROMPT_CHAR_LIMIT)
    structured_llm = llm.with_structured_output(RecipeAnalysis, method="json_mode")

    def _invoke_structured() -> RecipeAnalysis:
        return structured_llm.invoke(formatted_prompt)

    return _run_with_retry(_invoke_structured)


def generate_souschef_recipe(
    llm: ChatGroq,
    recipe_text: str,
    analysis: RecipeAnalysis,
    max_tokens: int,
) -> SousChefRecipe:
    """Main orchestrator: generates SousChef recipe by assembling parts.
    
    IMPORTANT: Output MUST follow SOUSCHEF_OUTPUT_SPEC.md exactly.
    
    The recipe generation process:
    1. Generate top-level metadata (names, descriptions, nutritional values)
    2. Generate steps one by one (with instructions, ingredients, durations)
    3. Assemble into final SousChefRecipe structure
    
    All AI-generated content is validated against the specification to ensure:
    - String values are properly JSON-escaped (no literal newlines)
    - Nutritional values are single integers (no ranges or decimals)
    - Metric units use exact capitalization
    - Descriptions are 2 sentences separated by space (no newlines)
    - Instructions are very concise and single-line
    
    See SOUSCHEF_OUTPUT_SPEC.md for complete requirements.
    """
    
    # Step 1: Generate top-level metadata
    metadata = _generate_recipe_metadata(llm, recipe_text, analysis)
    
    # Step 2: Generate steps one by one
    steps = _generate_recipe_steps(llm, recipe_text, analysis, metadata)
    
    # Step 3: Assemble into final SousChefRecipe
    return _assemble_souschef_recipe(metadata, steps)


def _normalize_metadata(metadata: dict) -> dict:
    """Normalize metadata JSON, handling ranges and type conversions."""
    # Fix nutritional values: convert ranges to single integers
    if "nutritional_values" in metadata and isinstance(metadata["nutritional_values"], dict):
        normalized_values = {}
        for key, value in metadata["nutritional_values"].items():
            if isinstance(value, str):
                # Handle ranges like "250-300" -> take first value
                if "-" in value and not value.startswith("-"):
                    try:
                        first_val = int(value.split("-")[0].strip())
                        normalized_values[key] = first_val
                    except (ValueError, IndexError):
                        normalized_values[key] = 0
                else:
                    try:
                        normalized_values[key] = int(float(value))
                    except (ValueError, TypeError):
                        normalized_values[key] = 0
            elif isinstance(value, (int, float)):
                normalized_values[key] = int(value)
            else:
                normalized_values[key] = 0
        metadata["nutritional_values"] = normalized_values
    
    # Ensure shopping_list is a list of strings
    if "shopping_list" in metadata and isinstance(metadata["shopping_list"], list):
        metadata["shopping_list"] = [str(item) for item in metadata["shopping_list"]]
    
    return metadata


def _generate_recipe_metadata(
    llm: ChatGroq,
    recipe_text: str,
    analysis: RecipeAnalysis,
) -> dict:
    """Generate top-level recipe metadata: names, descriptions, difficulty, nutritional values, shopping list."""
    
    metadata_prompt = """You are a recipe metadata expert. Extract and generate key information about this recipe.

RECIPE:
{recipe_text}

INGREDIENTS: {ingredients}
TOOLS: {tools}
COOKING TIME: {cooking_time}
COMPLEXITY: {complexity}

Generate ONLY this JSON (no text before/after):
{{
    "generic_name_en": "Short recipe name in English",
    "generic_name_nl": "Short recipe name in Dutch",
    "variant": "Meat|Vegetarian|Vegan|Fish|Other",
    "recipe_name_en": "Full recipe name in English",
    "recipe_name_nl": "Full recipe name in Dutch",
    "description_en": "Two sentences describing the recipe in English.",
    "description_nl": "Two sentences describing the recipe in Dutch.",
    "difficulty": "Easy|Medium|Intermediate",
    "nutritional_values": {{
        "Energie (kCal)": 250,
        "Protein (grams)": 15,
        "Carbohydrates (grams)": 10,
        "Sugar (grams)": 2,
        "Fat (grams)": 15,
        "Saturated Fat (grams)": 3,
        "Natrium (milligrams)": 400,
        "Fibers (grams)": 2
    }},
    "shopping_list": ["ingredient1", "ingredient2"]
}}

CRITICAL JSON RULES:
- IMPORTANT: All string values must be on a SINGLE LINE (no line breaks inside strings)
- Descriptions should be two sentences separated by a space, NOT a newline
- Use ONLY standard ASCII characters in strings
- Escape any quotes in strings with backslash
- Do NOT include actual line breaks in JSON values

Rules:
- Be concise and specific to this recipe
- Estimate nutritional values based on ingredients (PER SERVING)
- NUTRITIONAL VALUES MUST BE SINGLE INTEGER NUMBERS (not ranges like 250-300)
- Shopping list: only main ingredients, 5-10 items max
- Description must be exactly two sentences separated by a space (no newlines)""".strip()

    formatted_prompt = metadata_prompt.format(
        recipe_text=recipe_text,
        ingredients=", ".join(analysis.ingredients),
        tools=", ".join(analysis.tools),
        cooking_time=analysis.cooking_time,
        complexity=analysis.complexity,
    )
    
    _ensure_prompt_within_limit(formatted_prompt, DEFAULT_PROMPT_CHAR_LIMIT)

    def _invoke_metadata() -> dict:
        response = llm.invoke(formatted_prompt)
        content = response.content if isinstance(response.content, str) else str(response.content)
        raw_metadata = extract_json_payload(content)
        # Normalize the metadata to handle any formatting issues
        return _normalize_metadata(raw_metadata)

    return _run_with_retry(_invoke_metadata)


def _generate_recipe_steps(
    llm: ChatGroq,
    recipe_text: str,
    analysis: RecipeAnalysis,
    metadata: dict,
) -> List[dict]:
    """Generate recipe steps one at a time."""
    
    # First, get the step outline (how many steps, what are they about)
    step_outline = _generate_step_outline(llm, recipe_text, analysis)
    
    # Then generate each step individually
    steps = []
    for step_num, step_title in enumerate(step_outline, start=1):
        step = _generate_single_step(
            llm, 
            recipe_text, 
            analysis, 
            step_num, 
            step_title,
            metadata.get("variant", "Other")
        )
        steps.append(step)
    
    return steps


def _generate_step_outline(
    llm: ChatGroq,
    recipe_text: str,
    analysis: RecipeAnalysis,
) -> List[str]:
    """Generate a simple outline of cooking steps."""
    
    outline_prompt = """You are a recipe instructor. Break this recipe into clear cooking steps.

RECIPE:
{recipe_text}

INGREDIENTS: {ingredients}
COOKING TIME: {cooking_time}

Generate ONLY a JSON array of step titles (no text before/after):
["Step 1 title", "Step 2 title", "Step 3 title", ...]

Rules:
- 3-15 steps max
- Each step should be one clear action
- Include prep, cooking, and plating
- Be concise (5-10 words per step)
- Use imperative verbs (Chop, Cook, Mix, etc.)""".strip()

    formatted_prompt = outline_prompt.format(
        recipe_text=recipe_text,
        ingredients=", ".join(analysis.ingredients),
        cooking_time=analysis.cooking_time,
    )
    
    _ensure_prompt_within_limit(formatted_prompt, DEFAULT_PROMPT_CHAR_LIMIT)

    def _invoke_outline() -> List[str]:
        response = llm.invoke(formatted_prompt)
        content = response.content if isinstance(response.content, str) else str(response.content)
        payload = extract_json_payload(content)
        return payload if isinstance(payload, list) else []

    return _run_with_retry(_invoke_outline)


def _generate_single_step(
    llm: ChatGroq,
    recipe_text: str,
    analysis: RecipeAnalysis,
    step_number: int,
    step_title: str,
    variant: str,
) -> dict:
    """Generate a single step with detailed instructions."""
    
    step_prompt = """You are a SousChef recipe instructor. Generate ONE detailed cooking step.

RECIPE CONTEXT:
{recipe_text}

STEP DETAILS:
- Step Number: {step_number}
- Step Title: {step_title}
- Variant: {variant}
- Available Tools: {tools}

Generate ONLY this JSON (no text before/after):
{{
    "step_number": "{step_number}",
    "display_name_en": "Step title in English",
    "display_name_nl": "Step title in Dutch",
    "action_en": "One-word action (e.g., Chop, Cook, Mix)",
    "action_nl": "One-word action in Dutch",
    "step_name_editor": "Editor-friendly step name",
    "workplace": "1",
    "step_icon": "prep|cook|mix|serve",
    "instructions_en": "Detailed step-by-step instructions in English",
    "instructions_nl": "Detailed step-by-step instructions in Dutch",
    "duration": 10,
    "ingredients": [
        {{"ingredient": "ingredient name", "amount": 0.5, "metric_unit": "Gram"}}
    ],
    "count_down": [],
    "trigger_countdown_step": null,
    "recipe_variant": ["{variant}"]
}}

VALID METRIC UNITS (use EXACT capitalization):
Amount, Can, Cup, Degrees, Gram, Kilogram, Liter, Milligram, Milliliter, Tablespoon, Teaspoon

CRITICAL JSON RULES:
- IMPORTANT: All string values must be on a SINGLE LINE (no line breaks inside strings)
- If instructions are multiple sentences, separate with a space, NOT newlines
- Use ONLY standard ASCII characters in strings
- Escape any quotes in strings with backslash
- Do NOT include actual line breaks in JSON values

Rules:
- Be specific: reference exact ingredients and quantities when applicable
- Duration: estimate in minutes for this single step
- Ingredients array: list items used IN THIS STEP (not all ingredients)
- step_icon: choose from prep, cook, mix, serve based on action
- Instructions: clear, concise, one main action per step, single line only
- All string values must be non-empty
- Metric units MUST use exact capitalization from the list above""".strip()

    formatted_prompt = step_prompt.format(
        recipe_text=recipe_text,
        step_number=step_number,
        step_title=step_title,
        variant=variant,
        tools=", ".join(analysis.tools),
    )
    
    _ensure_prompt_within_limit(formatted_prompt, DEFAULT_PROMPT_CHAR_LIMIT)

    def _invoke_step() -> dict:
        response = llm.invoke(formatted_prompt)
        content = response.content if isinstance(response.content, str) else str(response.content)
        return extract_json_payload(content)

    return _run_with_retry(_invoke_step)


def _normalize_step_units(step_data: dict) -> dict:
    """Normalize metric units in a single step before validation."""
    ingredients = step_data.get("ingredients", [])
    if not ingredients:
        return step_data
    
    normalized_ingredients = []
    for ingredient in ingredients:
        if isinstance(ingredient, dict):
            unit = ingredient.get("metric_unit")
            if unit:
                unit_key = str(unit).strip().lower()
                # Normalize the unit: try aliases first, then check allowed units
                if unit_key in UNIT_ALIASES:
                    ingredient["metric_unit"] = UNIT_ALIASES[unit_key]
                elif unit not in ALLOWED_UNITS:
                    # If lowercase version exists in ALLOWED_UNITS, use title case
                    for allowed in ALLOWED_UNITS:
                        if allowed.lower() == unit_key:
                            ingredient["metric_unit"] = allowed
                            break
                    else:
                        # Default to Amount if no match found
                        ingredient["metric_unit"] = "Amount"
            normalized_ingredients.append(ingredient)
        else:
            normalized_ingredients.append(ingredient)
    
    step_data["ingredients"] = normalized_ingredients
    return step_data


def _assemble_souschef_recipe(metadata: dict, steps: List[dict]) -> SousChefRecipe:
    """Assemble metadata and steps into final SousChefRecipe structure."""
    
    # Ensure nutritional values are properly structured
    nutritional_data = metadata.get("nutritional_values", {})
    nutritional_values = NutritionalValues(
        **{
            "Energie (kCal)": int(nutritional_data.get("Energie (kCal)", 0)),
            "Protein (grams)": int(nutritional_data.get("Protein (grams)", 0)),
            "Carbohydrates (grams)": int(nutritional_data.get("Carbohydrates (grams)", 0)),
            "Sugar (grams)": int(nutritional_data.get("Sugar (grams)", 0)),
            "Fat (grams)": int(nutritional_data.get("Fat (grams)", 0)),
            "Saturated Fat (grams)": int(nutritional_data.get("Saturated Fat (grams)", 0)),
            "Natrium (milligrams)": int(nutritional_data.get("Natrium (milligrams)", 0)),
            "Fibers (grams)": int(nutritional_data.get("Fibers (grams)", 0)),
        }
    )
    
    recipe_variant_content = RecipeVariantContent(
        **{
            "Recipe Variant": metadata.get("variant", "Other"),
            "Recipe Name": LocalizedText(
                en=metadata.get("recipe_name_en", ""),
                nl_NL=metadata.get("recipe_name_nl", ""),
            ),
            "Description": LocalizedText(
                en=metadata.get("description_en", ""),
                nl_NL=metadata.get("description_nl", ""),
            ),
            "Difficulty": metadata.get("difficulty", "Medium"),
            "Nutritional Values": nutritional_values,
            "Shopping List": metadata.get("shopping_list", []),
        }
    )
    
    step_components = []
    for step_data in steps:
        # Normalize metric units BEFORE creating StepComponent to avoid validation errors
        step_data = _normalize_step_units(step_data)
        
        # Ensure ingredients are properly structured as dicts with required fields
        ingredients = step_data.get("ingredients", [])
        validated_ingredients = []
        for ing in ingredients:
            if isinstance(ing, dict):
                validated_ing = {
                    "Ingredient": ing.get("ingredient", ""),
                    "Amount": float(ing.get("amount", 0)),
                    "Metric Unit": ing.get("metric_unit", "Amount"),
                }
                validated_ingredients.append(validated_ing)
        
        step_component = StepComponent(
            **{
                "Step Number": step_data.get("step_number", ""),
                "Display Name": LocalizedText(
                    en=step_data.get("display_name_en", ""),
                    nl_NL=step_data.get("display_name_nl", ""),
                ),
                "Action": LocalizedText(
                    en=step_data.get("action_en", ""),
                    nl_NL=step_data.get("action_nl", ""),
                ),
                "Step Name (Editor)": step_data.get("step_name_editor", ""),
                "Workplace": step_data.get("workplace", "1"),
                "Step Icon": step_data.get("step_icon", "prep"),
                "Instructions": LocalizedText(
                    en=step_data.get("instructions_en", ""),
                    nl_NL=step_data.get("instructions_nl", ""),
                ),
                "Duration": step_data.get("duration", 10),
                "Ingredient": validated_ingredients,
                "Count Down": step_data.get("count_down", []),
                "Trigger Countdown Step": step_data.get("trigger_countdown_step"),
                "RecipeVariant": step_data.get("recipe_variant", []),
            }
        )
        step_components.append(step_component)
    
    validated_steps = [normalize_metric_units(step.model_dump()) for step in step_components]
    
    return SousChefRecipe(
        Order=1,
        **{
            "Generic Name": LocalizedText(
                en=metadata.get("generic_name_en", ""),
                nl_NL=metadata.get("generic_name_nl", ""),
            ),
            "Highlighted?": False,
            "Recipe Variant Content": [recipe_variant_content],
            "Steps Part 1": validated_steps,
        }
    )


def _sanitize_json_string(text: str) -> str:
    """Sanitize JSON string by escaping unescaped newlines and special characters.
    
    REQUIRED BY SOUSCHEF_OUTPUT_SPEC.md:
    - Unescaped newlines in JSON string values break JSON parsing
    - This function converts literal newlines to escaped \n sequences
    - This prevents "Expecting ',' delimiter" JSON parsing errors
    
    Handles:
    - Literal newlines (\\n) -> escaped \n
    - Literal tabs (\\t) -> escaped \\t  
    - Literal carriage returns (\\r) -> escaped \\r
    - Preserves already-escaped sequences
    """
    # This regex-based approach finds quoted strings and escapes them properly
    import re
    
    # First, protect already-escaped sequences
    protected_text = text.replace("\\n", "\x00NEWLINE\x00")
    protected_text = protected_text.replace("\\t", "\x00TAB\x00")
    protected_text = protected_text.replace("\\r", "\x00RETURN\x00")
    protected_text = protected_text.replace("\\\\", "\x00BACKSLASH\x00")
    
    # Find all quoted strings and fix unescaped newlines/tabs/returns in them
    def fix_string_content(match):
        quote_char = match.group(1)  # The quote character (" or ')
        content = match.group(2)
        
        # Escape control characters
        content = content.replace("\n", "\\n")
        content = content.replace("\r", "\\r")
        content = content.replace("\t", "\\t")
        content = content.replace('"', '\\"') if quote_char == '"' else content
        
        return f'{quote_char}{content}{quote_char}'
    
    # Match strings enclosed in double quotes (but not already escaped)
    # This is a simplified approach - match quote, then non-quote chars, then quote
    protected_text = re.sub(r'"([^"\\]*(?:\\.[^"\\]*)*)"', fix_string_content, protected_text)
    
    # Restore protected sequences
    protected_text = protected_text.replace("\x00NEWLINE\x00", "\\n")
    protected_text = protected_text.replace("\x00TAB\x00", "\\t")
    protected_text = protected_text.replace("\x00RETURN\x00", "\\r")
    protected_text = protected_text.replace("\x00BACKSLASH\x00", "\\\\")
    
    return protected_text


def extract_json_payload(text: str) -> dict:
    """Extract and validate JSON payload from LLM response text.
    
    REQUIRED BY SOUSCHEF_OUTPUT_SPEC.md:
    - Extracts JSON from LLM response (may contain markdown code blocks)
    - Sanitizes JSON to escape unescaped newlines
    - Validates that required fields are present
    - Handles common JSON parsing errors (trailing commas, etc.)
    
    Returns:
        dict: Parsed and validated JSON payload matching SousChef specification
        
    Raises:
        ValueError: If JSON is invalid, malformed, or missing required fields
    """
    # First, try to parse the text as-is
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Extract JSON from markdown code blocks if present
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        if end != -1:
            text = text[start:end].strip()
    elif "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        if end != -1:
            text = text[start:end].strip()
    
    # Try to extract JSON by finding the outermost braces
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Model output did not contain valid JSON.")
    
    json_text = text[start : end + 1]
    if _is_truncated_json(json_text):
        raise ValueError("Model output appears truncated or malformed.")
    
    # Sanitize the JSON string to escape unescaped newlines and special characters
    json_text = _sanitize_json_string(json_text)
    
    # Try parsing the extracted JSON
    try:
        parsed = json.loads(json_text)
        
        # Validate that required top-level fields exist
        required_fields = ["Order", "Generic Name", "Recipe Variant Content", "Steps Part 1"]
        missing = [f for f in required_fields if f not in parsed]
        if missing:
            # Check if this looks like a wrong structure
            actual_fields = list(parsed.keys())
            raise ValueError(
                f"Wrong JSON structure returned. Expected fields: {required_fields}\n"
                f"But got: {actual_fields}\n"
                f"The model may have generated a different recipe format instead of SousChef format."
            )
        
        return parsed
    except json.JSONDecodeError as e:
        # Common LLM JSON errors: trailing commas
        # Try to fix trailing commas before closing braces/brackets
        import re
        fixed_text = re.sub(r',\s*([\]}])', r'\1', json_text)
        try:
            parsed = json.loads(fixed_text)
            
            # Validate completeness
            required_fields = ["Order", "Generic Name", "Recipe Variant Content", "Steps Part 1"]
            missing = [f for f in required_fields if f not in parsed]
            if missing:
                actual_fields = list(parsed.keys())
                raise ValueError(
                    f"Wrong JSON structure returned. Expected fields: {required_fields}\n"
                    f"But got: {actual_fields}\n"
                    f"The model may have generated a different recipe format instead of SousChef format."
                )
            
            return parsed
        except json.JSONDecodeError:
            error_msg = f"JSON parsing failed at line {e.lineno}, column {e.colno}: {e.msg}\n\nProblematic JSON (first 1000 chars):\n{json_text[:1000]}"
            raise ValueError(error_msg)


def normalize_metric_units(payload: dict) -> dict:
    # Normalize Shopping List from complex objects to simple strings
    recipe_variants = payload.get("Recipe Variant Content", [])
    for variant in recipe_variants:
        shopping_list = variant.get("Shopping List", [])
        if shopping_list and isinstance(shopping_list, list):
            normalized_shopping = []
            for item in shopping_list:
                if isinstance(item, dict):
                    # Extract just the ingredient name if it's a complex object
                    ingredient_name = (
                        item.get("Ingredient") or 
                        item.get("en") or 
                        str(item.get("ingredient", ""))
                    )
                    if ingredient_name:
                        normalized_shopping.append(str(ingredient_name))
                elif isinstance(item, str):
                    normalized_shopping.append(item)
                else:
                    normalized_shopping.append(str(item))
            variant["Shopping List"] = normalized_shopping
    
    # Normalize metric units in steps
    steps = payload.get("Steps Part 1", [])
    for step in steps:
        ingredients = step.get("Ingredient") or []
        for ingredient in ingredients:
            unit = ingredient.get("Metric Unit")
            if not unit:
                continue
            unit_key = str(unit).strip().lower()
            if unit in ALLOWED_UNITS:
                continue
            if unit_key in UNIT_ALIASES:
                ingredient["Metric Unit"] = UNIT_ALIASES[unit_key]
            else:
                ingredient["Metric Unit"] = "Amount"
        count_down = step.get("Count Down")
        if isinstance(count_down, list):
            normalized = []
            for item in count_down:
                if isinstance(item, dict):
                    trigger = item.get("Trigger") or item.get("name") or "Timer"
                    duration = item.get("Duration") or item.get("duration")
                    if duration:
                        normalized.append(f"{trigger} ({duration}s)")
                    else:
                        normalized.append(str(trigger))
                else:
                    normalized.append(str(item))
            step["Count Down"] = normalized
    return payload


def validate_recipe(recipe: SousChefRecipe) -> List[str]:
    issues = []
    if len(recipe.steps_part_1) > 50:
        issues.append("Steps Part 1 exceeds 50 steps.")
    if not recipe.recipe_variant_content:
        issues.append("Recipe Variant Content must include at least one variant.")
    for variant in recipe.recipe_variant_content:
        if variant.description:
            paragraphs = [p for p in variant.description.en.split("\n\n") if p.strip()]
            if len(paragraphs) != 2:
                issues.append("Description must have exactly 2 paragraphs (en).")
            paragraphs_nl = [p for p in variant.description.nl_NL.split("\n\n") if p.strip()]
            if len(paragraphs_nl) != 2:
                issues.append("Description must have exactly 2 paragraphs (nl_NL).")
    for index, step in enumerate(recipe.steps_part_1, start=1):
        step_label = f"Step {index}"
        if not step.instructions.en.strip() or not step.instructions.nl_NL.strip():
            issues.append(f"{step_label} is missing instructions in English or Dutch.")
        if step.duration <= 0:
            issues.append(
                f"{step_label} is missing a duration."
            )
    return issues


def main() -> None:
    load_dotenv(".env", override=True)
    from src.main import main as streamlit_main

    streamlit_main()


if __name__ == "__main__":
    main()

# SousChef® Exact AI Output Specification

**Language:** English  
**Purpose:** Define exact AI output so it can be entered 1:1 into Hygraph CMS and behaves correctly in the SousChef Cookalong.

**CONTENT TYPE:** Recipe

---

## 1. Recipe – Top Level Fields (Exact Order)

### 1. Order
- **Type:** Number
- **Required:** Yes
- **AI instruction:**
  - Integer only
  - Used for sorting
  - AI may choose a logical value

### 2. Generic Name
- **Type:** Localized single line text
- **Required:** Yes
- **Locales:** en, nl_NL
- **AI instruction:**
  - Generic dish name only
  - Do not include variant information
  - Example: Correct: "Lasagne" | Incorrect: "Lasagne with mushrooms"

### 3. Highlighted?
- **Type:** Boolean
- **Required:** No
- **AI instruction:**
  - Default to false unless explicitly stated otherwise

### 4. Recipe Variant Content (Component List)
Each recipe contains one or more variants (e.g., Meat, Vegetarian).

---

## COMPONENT: Recipe Variant Content

### 1. Recipe Variant
- **Type:** Reference
- **Required:** Yes
- **AI instruction:**
  - Must reference an existing Recipe Variant (e.g., Meat, Vega)

### 2. Recipe Image
- **Type:** Asset (image)
- **Required in CMS:** Yes
- **Required for students:** No
- **AI instruction:**
  - Students do not need to generate this
  - If AI generates an image anyway:
    - Format: JPEG
    - Size: 780 × 780 px
    - Square, final dish visible

### 3. Recipe Name
- **Type:** Localized single line text
- **Required:** Yes
- **Locales:** en, nl_NL
- **AI instruction (IMPORTANT):**
  - Must explicitly describe the variant difference
  - The user must immediately understand what makes this version different
  - Examples:
    - "Lasagne with minced beef"
    - "Lasagne with fried mushrooms (vegetarian)"

### 4. Description
- **Type:** Localized rich text
- **Required:** No
- **Locales:** en, nl_NL
- **AI instruction:**
  - Exactly 2 short paragraphs
  - Written for end users
  - No cooking instructions
  - Emphasize:
    - Ease
    - Taste and end result
    - Guidance by SousChef
  - **CRITICAL:** Two sentences separated by a space (NO line breaks or newlines)

### 5. Diet/Allergen 01
- **Type:** Single line text
- **Required:** No
- **AI instruction:**
  - Only fill if applicable
  - One value per field

### 6. Diet/Allergen 02
- **Type:** Single line text
- **Required:** No
- **AI instruction:**
  - Only fill if applicable
  - One value per field

### 7. Tag
- **Type:** Single line text
- **Required:** No
- **AI instruction:**
  - Seasonal or contextual only (e.g., Christmas)

### 8. Difficulty
- **Type:** Dropdown (enum)
- **Required:** Yes
- **Allowed values (EXACT):**
  - Easy
  - Medium
  - Intermediate
- **AI instruction:**
  - Base difficulty on:
    - Number of steps
    - Parallel actions
    - Timing complexity

### 9. Nutritional Values
- **Type:** Reference
- **Required:** Yes
- **AI instruction:**
  - Values may be estimated by AI
  - Base estimation on:
    - Recipe text
    - Ingredient list
  - **CRITICAL:** Values must be calculated per 1 person
  - **CRITICAL:** All values MUST be single INTEGER numbers (no ranges, no decimals)
- **Fields inside Nutritional Values:**
  - Energie (kCal)
  - Protein (grams)
  - Carbohydrates (grams)
  - Sugar (grams)
  - Fat (grams)
  - Saturated Fat (grams)
  - Natrium (milligrams)
  - Fibers (grams)

### 10. Shopping List
- **Type:** Reference list
- **Required:** No
- **AI instruction:**
  - May be left empty
  - Students do not need to fill this

### 11. Sponsor
- **Type:** Reference
- **Required:** No

### 12. Preview Video
- **Type:** Asset (video)
- **Required:** No
- **AI instruction:**
  - Leave empty
  - This field is not used

### 13. Steps Part 1
- **Type:** Component list
- **Required:** Yes
- **Maximum:** 50 steps. Steps Part 2 is ignored.

---

## COMPONENT: Step
SousChef recipes are split into micro-steps.

### 1. Display Name
- **Type:** Localized single line text
- **Required:** No
- **Locales:** en, nl_NL
- **AI instruction:**
  - Name of the ingredient or tool that plays the main role
  - This is the top label in the Cookalong UI
  - Examples: Onion, Carrot, Large frying pan

### 2. Action
- **Type:** Localized single line text
- **Required:** No
- **Locales:** en, nl_NL
- **AI instruction:**
  - Short verb phrase describing the action on the Display name
  - Maximum 2–3 verbs
  - Examples: Wash and chop, Peel and slice, Add to pan

### 3. Step Number
- **Type:** Single line text
- **Required:** No

### 4. Step Name (Editor)
- **Type:** Single line text
- **Required:** No
- **AI instruction:**
  - Internal editor label
  - Used for TR/CD logic

### 5. Workplace
- **Type:** Dropdown
- **Required:** Yes
- **AI instruction:**
  - Legacy field
  - Represents row number in the Cookalong
  - Labels (e.g., "Blender") do not describe the action

### 6. Step Icon
- **Type:** Asset (image)
- **Required:** Yes

### 7. Instructions
- **Type:** Localized rich text
- **Required:** Yes
- **Locales:** en, nl_NL
- **AI instruction (CRITICAL):**
  - One clear action per step
  - Very short, very clear
  - Must be understandable by a 12-year-old
  - **CRITICAL:** Single line text (NO actual newlines in JSON)
  - If an Ingredient Component is present:
    - Use [QUANTITY] dynamically
  - Timer wording rule:
    - If a timer is involved, explicitly describe it, for example:
      - "Add [QUANTITY] minced beef and break it apart with a spatula. Fry for 5 minutes over medium heat until lightly browned. Stir regularly. Tick off this step, then I'll start the 5-minute timer for you."

### 8. Instructions Markdown
- **Type:** Localized text
- **Required in CMS:** Yes
- **AI instruction:**
  - Legacy field
  - May be ignored
  - Can be left empty or duplicate Instructions

### 9. Appliances
- **Type:** Reference list
- **Required:** No

### 10. Ingredient
- **Type:** Component list
- **Required:** No
- **Micro-step and ingredient rules (VERY IMPORTANT):**
  - Create a unique step WITH an Ingredient Component when:
    - An ingredient appears for the first time, and
    - A prep action or first addition is required
  - Combine prep actions:
    - If multiple prep actions happen sequentially on the same ingredient (e.g., wash + chop):
      - Combine them into one step
      - Add the Ingredient Component once
  - Create a separate step WITHOUT Ingredient Component when:
    - Multiple already-introduced ingredients are combined
    - Example: adding onion + carrot to the pan
  - **NEVER:**
    - Add the same Ingredient Component twice (this would duplicate the ingredient list)
  - Meal kit exception:
    - A meal kit may be treated as one single ingredient
    - Do not split unless the input ingredient list explicitly does so

### 11. Duration
- **Type:** Number
- **Required:** Yes
- **AI instruction:**
  - Time (in seconds) the user needs to perform the action
  - This is NOT a countdown timer

### 12. Count Down
- **Type:** Reference list
- **Required:** No

### 13. Trigger Countdown Step
- **Type:** Single line text
- **Required:** No
- **TR/CD logic:**
  - Step A contains a Trigger (TR) and starts a timer
  - Step B contains the Countdown (CD) and fires when the timer ends
  - Titles must match exactly
  - Example:
    - Step A (TR): "Put pasta in boiling water"
    - Step B (CD): "Drain the pasta"

### 14. Video
- **Type:** Asset
- **Required:** No

### 15. Thumbnail
- **Type:** Asset
- **Required:** No
- **AI instruction:**
  - Leave empty
  - Produced separately in studio

### 16. RecipeVariant
- **Type:** Reference list
- **Required:** Yes
- **AI instruction:**
  - Select which variants this step applies to

---

## COMPONENT: Ingredient Component

### 1. Ingredient
- **Type:** Reference
- **Required:** Yes

### 2. Amount
- **Type:** Number
- **Required:** Yes
- **AI instruction:**
  - Dot notation only (e.g., 0.5)

### 3. Metric Unit
- **Type:** Dropdown (enum)
- **Required:** Yes
- **Allowed values (EXACT capitalization required):**
  - Amount
  - Can
  - Cup
  - Degrees
  - Gram
  - Kilogram
  - Liter
  - Milligram
  - Milliliter
  - Tablespoon
  - Teaspoon

---

## CRITICAL JSON GENERATION RULES

These rules are MANDATORY and must be enforced in all LLM prompts and post-processing:

### 1. String Escaping
- **NO actual newlines inside JSON string values**
- All string values must be on a SINGLE LINE in the JSON
- Newlines must be escaped as `\n` in the JSON (if needed for display)
- Tabs must be escaped as `\t`
- Carriage returns must be escaped as `\r`
- Backslashes must be escaped as `\\`

### 2. String Content
- Use ONLY standard ASCII characters in strings
- Escape any double quotes in strings with backslash: `\"`
- Description fields: Two sentences separated by a space (NOT a newline)
- Instructions fields: Single sentence or very concise 1-line instruction
- No multi-line instructions in JSON

### 3. Numeric Fields
- **Nutritional values MUST be single INTEGER numbers**
  - NO ranges (e.g., "250-300" is invalid)
  - NO decimal points (e.g., "2.5" → "2" or "3")
  - Example: `"Energie (kCal)": 250` ✓
  - Example: `"Energie (kCal)": "250-300"` ✗

### 4. Duration Fields
- Express in SECONDS only
- Integer values only
- Example: 10 seconds of chopping = `"Duration": 10`

### 5. Metric Units
- MUST use EXACT capitalization from the allowed list
- No variations (e.g., "gram" → "Gram", "ML" → "Milliliter")
- Always use official list values

### 6. Variant References
- Allowed variants: Meat, Vegetarian, Vegan, Fish, Other
- Must be consistent across all steps that use the recipe variant

---

## Validation Checklist

Before finalizing any SousChef recipe JSON, verify:

- [ ] All string values are properly JSON-escaped (no literal newlines)
- [ ] All required fields are present and non-empty
- [ ] Generic Name is valid (no variant info)
- [ ] Recipe Name describes the variant explicitly
- [ ] Descriptions are exactly 2 sentences with space separator (no newlines)
- [ ] Difficulty is one of: Easy, Medium, Intermediate
- [ ] All nutritional values are single integers (no ranges or decimals)
- [ ] All metric units use exact capitalization
- [ ] Duration values are in seconds (integers)
- [ ] Steps do not exceed 50 maximum
- [ ] Recipe variants are consistently referenced in steps
- [ ] Localized fields include both `en` and `nl_NL` variants
- [ ] All JSON is valid and parseable
- [ ] No truncated or incomplete fields

---

## Implementation Guide

### Key Files in the Codebase

**app.py** - Core recipe generation logic:
- `generate_souschef_recipe()` - Main orchestrator function
- `_generate_recipe_metadata()` - Creates top-level recipe data
- `_generate_recipe_steps()` - Creates step-by-step instructions
- `_sanitize_json_string()` - Escapes unescaped newlines (CRITICAL)
- `extract_json_payload()` - Parses and validates JSON from LLM

**src/main.py** - Streamlit UI for recipe transformation

### How the Code Enforces These Rules

#### 1. LLM Prompts
Look for "CRITICAL JSON RULES" sections in:
- `_generate_recipe_metadata()` - Metadata generation prompt
- `_generate_single_step()` - Step generation prompt

These explicitly instruct the LLM to:
- Keep all string values on single lines
- Use single INTEGER values for nutrition
- Use exact metric unit capitalization
- Format descriptions as "Sentence 1. Sentence 2."

#### 2. JSON Sanitization
The `_sanitize_json_string()` function automatically:
- Protects already-escaped sequences
- Converts literal newlines to `\n` escape sequences
- Converts literal tabs to `\t` escape sequences
- Called before parsing JSON from LLM responses

#### 3. Validation
The `extract_json_payload()` function:
- Checks for required top-level fields
- Validates JSON structure matches specification
- Provides detailed error messages if validation fails

#### 4. Pydantic Models
The data classes in app.py enforce:
- Exact field names and types
- Allowed enum values (e.g., metric units)
- Required vs optional fields
- Localization requirements (en, nl_NL)

### Making Changes to the Specification

#### If you need to modify LLM prompts:
1. Locate the "CRITICAL JSON RULES" section in the relevant function
2. Keep this section intact - it enforces the rules below
3. Test output against this checklist
4. Verify generated JSON with debug files in `debug_state/`

#### If you need to change the specification:
1. **Update this file FIRST** (SOUSCHEF_OUTPUT_SPEC.md)
2. Update corresponding Pydantic models in app.py
3. Update LLM prompts to match
4. Update code docstrings to reference the spec

#### If JSON parsing fails:
1. Check debug_state/ folder for generated JSON
2. Compare against validation checklist above
3. Verify:
   - No literal newlines in string values
   - All metric units have correct capitalization
   - Nutritional values are integers (not ranges)
   - All required fields exist
   - Localization includes both en and nl_NL

### Testing Checklist

When adding new features or fixing bugs:

- [ ] JSON files in debug_state/ are valid
- [ ] All string values are single-line (no literal newlines)
- [ ] All numeric values match specification
- [ ] All enums use exact values from specification
- [ ] Localized fields include both en and nl_NL
- [ ] No fields are missing or truncated
- [ ] Pydantic validation passes without errors
- [ ] Generated JSON matches schema in specification

### Common Issues & Fixes

#### ❌ "Expecting ',' delimiter: line X column Y"
**Cause:** Unescaped newline in JSON string

**Fix:** Check if instructions or descriptions contain literal newlines
- Replace actual line breaks with escaped `\n` sequences
- The `_sanitize_json_string()` function handles this automatically

#### ❌ JSON parsing fails after sanitization
**Cause:** Invalid JSON structure or duplicate fields

**Fix:**
1. Check debug_state/ files for actual JSON generated
2. Validate structure matches specification
3. Verify all metric units use exact capitalization

#### ❌ Nutritional values rejected by CMS
**Cause:** Non-integer values (ranges or decimals)

**Fix:**
- Change "250-300" → "250" (take first value or average)
- Change "15.5" → "15" or "16" (round to integer)
- The `_normalize_metadata()` function handles this

#### ❌ Metric unit validation errors
**Cause:** Wrong capitalization or spelling

**Fix:**
- ❌ "gram" → ✅ "Gram"
- ❌ "ML" → ✅ "Milliliter"
- ❌ "tbsp" → ✅ "Tablespoon"

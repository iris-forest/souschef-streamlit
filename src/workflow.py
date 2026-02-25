from __future__ import annotations

import copy
import json
from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from app import (
    ALLOWED_UNITS,
    DEFAULT_RECIPE_CHAR_LIMIT,
    LocalizedText,
    NutritionalValues,
    RecipeVariantContent,
    StepComponent,
    SousChefRecipe,
    analyze_recipe,
    build_llm,
    condense_recipe_text,
    export_outputs,
    extract_json_payload,
    generate_souschef_recipe,
    normalize_metric_units,
    validate_recipe,
)


class RecipeWorkflowState(TypedDict, total=False):
    recipe_text: str
    condensed_recipe_text: str
    model_name: str
    temperature: float
    max_tokens: int
    analysis: object
    generated_json: dict | None
    souschef_recipe: dict | None
    validation_errors: list[str]
    quality_issues: list[str]
    repair_iteration: int
    max_repair_iterations: int
    final_status: str
    error_message: str | None
    export_paths: dict | None


def _resolve_llm(state: RecipeWorkflowState):
    model_name = state.get("model_name")
    temperature = state.get("temperature")
    max_tokens = state.get("max_tokens")
    if model_name and temperature is not None:
        return build_llm(
            model_name=model_name,
            temperature=float(temperature),
            max_tokens=max_tokens
        )
    return None


def _condense_node(state: RecipeWorkflowState) -> RecipeWorkflowState:
    """Condense recipe text to fit within character limits."""
    recipe_text = (state.get("recipe_text") or "").strip()
    if not recipe_text:
        return {
            **state,
            "final_status": "failed",
            "error_message": "Missing recipe_text input.",
            "validation_errors": ["recipe_text is required"],
        }
    
    llm = _resolve_llm(state)
    if llm is None:
        raise ValueError("LLM configuration is required for condensing recipe text.")
    
    try:
        condensed_text = condense_recipe_text(llm, recipe_text, DEFAULT_RECIPE_CHAR_LIMIT)
        return {
            **state,
            "condensed_recipe_text": condensed_text,
        }
    except Exception as exc:
        return {
            **state,
            "final_status": "failed",
            "error_message": f"Condensing failed: {exc}",
            "validation_errors": [str(exc)],
        }


def _generate_node(state: RecipeWorkflowState) -> RecipeWorkflowState:
    # Generate a SousChef recipe (LLM when available, fallback otherwise).
    recipe_text = (state.get("condensed_recipe_text") or state.get("recipe_text") or "").strip()
    if not recipe_text:
        return {
            **state,
            "final_status": "failed",
            "error_message": "Missing recipe_text input.",
            "validation_errors": ["recipe_text is required"],
        }

    llm = _resolve_llm(state)
    if llm is None:
        raise ValueError("LLM configuration is required for generation in this workflow.")

    try:
        analysis = state.get("analysis")
        if analysis is None:
            analysis = analyze_recipe(llm, recipe_text)
        recipe = generate_souschef_recipe(
            llm,
            recipe_text,
            analysis,
            max_tokens=int(state.get("max_tokens")),
        )
    except Exception as exc:
        return {
            **state,
            "final_status": "failed",
            "error_message": f"Generation failed: {exc}",
            "validation_errors": [str(exc)],
        }
    return {
        **state,
        "analysis": analysis,
        "generated_json": recipe.model_dump(by_alias=True),
        "souschef_recipe": recipe,
        "validation_errors": [],
    }


def _validate_schema_node(state: RecipeWorkflowState) -> RecipeWorkflowState:
    # Validate against the SousChef schema and capture any failures.
    if state.get("validation_errors"):
        return state
    generated = state.get("generated_json") or {}
    try:
        if isinstance(generated, SousChefRecipe):
            recipe = generated
        else:
            recipe = SousChefRecipe.model_validate(generated)
    except Exception as exc:
        return {
            **state,
            "validation_errors": [str(exc)],
            "final_status": "schema_failed",
            "error_message": "Schema validation failed.",
        }
    return {
        **state,
        "souschef_recipe": recipe,
        "validation_errors": [],
    }


def _quality_check_node(state: RecipeWorkflowState) -> RecipeWorkflowState:
    # Enforce domain checks beyond schema (units, required text, durations).
    issues: list[str] = []
    recipe = state.get("souschef_recipe")
    if recipe is None:
        return {
            **state,
            "quality_issues": ["Missing parsed recipe for quality checks."],
        }

    issues.extend(validate_recipe(recipe))
    for step_index, step in enumerate(recipe.steps_part_1, start=1):
        for ingredient in step.ingredient or []:
            if ingredient.metric_unit not in ALLOWED_UNITS:
                issues.append(
                    f"Step {step_index}: invalid unit '{ingredient.metric_unit}' for {ingredient.ingredient}"
                )

    return {**state, "quality_issues": issues}


def _repair_node(state: RecipeWorkflowState) -> RecipeWorkflowState:
    # Attempt to repair quality issues with LLM or deterministic fixes.
    iteration = state.get("repair_iteration", 0)
    max_iterations = state.get("max_repair_iterations", 2)
    if iteration >= max_iterations:
        return {
            **state,
            "final_status": "failed",
            "error_message": "Repair attempts exhausted.",
        }

    issues = state.get("quality_issues") or []
    payload = state.get("generated_json") or {}
    llm = _resolve_llm(state)

    if llm is None:
        repaired_payload = _auto_repair_payload(payload)
    else:
        repaired_payload = _llm_repair_payload(llm, payload, issues)

    return {
        **state,
        "generated_json": repaired_payload,
        "repair_iteration": iteration + 1,
        "quality_issues": [],
    }


def _auto_repair_payload(payload: dict) -> dict:
    # Deterministic repairs used when no LLM is configured.
    repaired = copy.deepcopy(payload)
    try:
        repaired = normalize_metric_units(repaired)
    except Exception:
        pass

    steps = repaired.get("Steps Part 1", [])
    for step in steps:
        if not isinstance(step, dict):
            continue
        duration = step.get("Duration", 0)
        if not isinstance(duration, int) or duration <= 0:
            step["Duration"] = 60
        instructions = step.get("Instructions")
        if not isinstance(instructions, dict):
            instructions = {}
        if not instructions.get("en"):
            instructions["en"] = (
                "Follow the recipe text step by step. Tick off this step when you finish it."
            )
        if not instructions.get("nl_NL"):
            instructions["nl_NL"] = (
                "Volg de recepttekst stap voor stap. Vink deze stap af als je klaar bent."
            )
        step["Instructions"] = instructions
    return repaired


def _llm_repair_payload(llm, payload: dict, issues: list[str]) -> dict:
    # LLM-backed repair to fix validation issues while preserving schema.
    issue_text = "\n".join(f"- {issue}" for issue in issues) or "- No issues provided"
    prompt = """
You are repairing a SousChef JSON payload.

Issues to fix:
{issues}

Current JSON payload:
{payload}

Return ONLY valid JSON with the same schema. Fix the issues, do not add extra text.
""".strip()
    try:
        response = llm.invoke(
            prompt.format(issues=issue_text, payload=json.dumps(payload, indent=2))
        )
        content = response.content if isinstance(response.content, str) else str(response.content)
        repaired = extract_json_payload(content)
        return normalize_metric_units(repaired)
    except Exception:
        return _auto_repair_payload(payload)


def _export_node(state: RecipeWorkflowState) -> RecipeWorkflowState:
    # Write JSON and CSV outputs to the export folder.
    recipe = state.get("souschef_recipe")
    if recipe is None:
        raise ValueError("Missing parsed recipe for export. Cannot export without a valid recipe.")
    
    try:
        paths = export_outputs(recipe)
    except Exception as exc:
        raise ValueError(f"Export failed: {exc}") from exc
    
    return {
        **state,
        "final_status": "success",
        "error_message": None,
        "export_paths": paths,
    }


def _route_after_validation(state: RecipeWorkflowState) -> str:
    return "end" if state.get("validation_errors") else "quality"


def _route_after_quality(state: RecipeWorkflowState) -> str:
    return "export" if not state.get("quality_issues") else "repair"


def _route_after_repair(state: RecipeWorkflowState) -> str:
    return "end" if state.get("final_status") == "failed" else "validate"


def create_workflow():
    """Create a LangGraph workflow for recipe validation and repair."""
    graph = StateGraph(RecipeWorkflowState)
    graph.add_node("condense", _condense_node)
    graph.add_node("generate", _generate_node)
    graph.add_node("validate", _validate_schema_node)
    graph.add_node("quality", _quality_check_node)
    graph.add_node("repair", _repair_node)
    graph.add_node("export", _export_node)

    graph.add_edge(START, "condense")
    graph.add_edge("condense", "generate")
    graph.add_edge("generate", "validate")
    graph.add_conditional_edges(
        "validate",
        _route_after_validation,
        {"quality": "quality", "end": END},
    )
    graph.add_conditional_edges(
        "quality",
        _route_after_quality,
        {"export": "export", "repair": "repair"},
    )
    graph.add_conditional_edges(
        "repair",
        _route_after_repair,
        {"validate": "validate", "end": END},
    )
    graph.add_edge("export", END)
    return graph.compile()

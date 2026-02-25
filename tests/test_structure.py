from __future__ import annotations

import os
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_module(path: Path, name: str):
    spec = spec_from_file_location(name, path)
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_entrypoint_exists() -> None:
    module = load_module(ROOT / "src" / "main.py", "main")
    assert hasattr(module, "main")


def test_workflow_requires_llm() -> None:
    """Test that workflow raises an error when LLM is not configured (error-first philosophy)."""
    module = load_module(ROOT / "src" / "workflow.py", "workflow")
    assert hasattr(module, "create_workflow")
    workflow = module.create_workflow()
    assert hasattr(workflow, "invoke")
    
    # Workflow should raise ValueError when LLM is not configured
    try:
        result = workflow.invoke({"recipe_text": "test"})
        assert False, "Expected ValueError when LLM config is missing"
    except ValueError as e:
        assert "LLM configuration is required" in str(e)


def test_utils_load_sample_recipe() -> None:
    module = load_module(ROOT / "src" / "utils.py", "utils")
    assert hasattr(module, "load_sample_recipe")
    assert isinstance(module.load_sample_recipe(), str)


def test_prompt_limit_raises() -> None:
    module = load_module(ROOT / "app.py", "app")
    with pytest.raises(ValueError, match="Prompt size exceeds configured limit"):
        module._ensure_prompt_within_limit("abcdef", 5)


def test_retry_on_throttle(monkeypatch) -> None:
    module = load_module(ROOT / "app.py", "app")
    attempts = {"count": 0}

    def flaky_call():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("Rate limit exceeded")
        return "ok"

    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    assert module._run_with_retry(flaky_call, max_retries=3) == "ok"


def test_recipe_plan_model_validates() -> None:
    module = load_module(ROOT / "app.py", "app")
    payload = {
        "generic_name_en": "Gyoza",
        "generic_name_nl": "Gyoza",
        "variant": "Meat",
        "recipe_name_en": "Japanese Gyoza",
        "recipe_name_nl": "Japanse Gyoza",
        "description_en": "A.\n\nB.",
        "description_nl": "A.\n\nB.",
        "difficulty": "Easy",
        "nutritional_values": {
            "Energie (kCal)": 0,
            "Protein (grams)": 0,
            "Carbohydrates (grams)": 0,
            "Sugar (grams)": 0,
            "Fat (grams)": 0,
            "Saturated Fat (grams)": 0,
            "Natrium (milligrams)": 0,
            "Fibers (grams)": 0,
        },
        "shopping_list": ["cabbage"],
        "steps": [
            {
                "display_name_en": "Prep",
                "display_name_nl": "Voorbereiden",
                "action_en": "Prepare",
                "action_nl": "Voorbereid",
                "step_name_editor": "Prep",
                "workplace": "1",
                "step_icon": "prep",
                "instructions_en": "Do it.",
                "instructions_nl": "Doe het.",
                "duration": 60,
                "ingredients": [
                    {
                        "ingredient": "cabbage",
                        "amount": 1,
                        "metric_unit": "Amount",
                    }
                ],
                "count_down": [],
                "trigger_countdown_step": None,
            }
        ],
    }
    plan = module.RecipePlan.model_validate(payload)
    assert plan.generic_name_en == "Gyoza"


def test_extract_json_payload_handles_trailing_commas() -> None:
    module = load_module(ROOT / "app.py", "app")
    raw = "{\"Order\": 1, \"Generic Name\": {\"en\": \"Test\", \"nl_NL\": \"Test\"}, \"Recipe Variant Content\": [], \"Steps Part 1\": [], }"
    parsed = module.extract_json_payload(raw)
    assert parsed["Order"] == 1


def test_extract_json_payload_from_codeblock() -> None:
    module = load_module(ROOT / "app.py", "app")
    raw = """```json
    {"Order": 1, "Generic Name": {"en": "Test", "nl_NL": "Test"}, "Recipe Variant Content": [], "Steps Part 1": []}
    ```"""
    parsed = module.extract_json_payload(raw)
    assert parsed["Order"] == 1


def test_truncation_detection() -> None:
    module = load_module(ROOT / "app.py", "app")
    assert module._is_truncated_json('{"a": "b"') is True
    assert module._is_truncated_json('{"a": "b"}') is False
    assert module._is_truncated_json('{"a": [1, 2}') is True

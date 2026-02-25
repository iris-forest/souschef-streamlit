from __future__ import annotations

import os


BASE_DIR = os.path.dirname(os.path.dirname(__file__))


def load_sample_recipe() -> str:
    sample_path = os.path.join(BASE_DIR, "import", "recipe.txt")
    if os.path.exists(sample_path):
        with open(sample_path, "r", encoding="utf-8") as handle:
            return handle.read()
    return ""

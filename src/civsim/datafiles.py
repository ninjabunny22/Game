"""Access to the JSON game data shipped in civsim/data."""

import json
from importlib import resources
from typing import Any


def load_json(name: str) -> Any:
    path = resources.files("civsim").joinpath("data", name)
    return json.loads(path.read_text(encoding="utf-8"))

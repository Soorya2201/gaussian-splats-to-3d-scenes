"""Save/load scene graph JSON to disk (backend/scenes/)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from schemas import SceneGraphModel

SCENES_DIR = Path(__file__).parent / "scenes"
SCENES_DIR.mkdir(exist_ok=True)


def _safe(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name) or "scene"


def save_scene(name: str, graph: SceneGraphModel) -> Path:
    path = SCENES_DIR / f"{_safe(name)}.json"
    path.write_text(graph.model_dump_json(indent=2, by_alias=True))
    return path


def load_scene(name: str) -> SceneGraphModel:
    path = SCENES_DIR / f"{_safe(name)}.json"
    if not path.exists():
        raise FileNotFoundError(f"No saved scene named '{name}'.")
    data = json.loads(path.read_text())
    return SceneGraphModel(**data)


def list_scenes() -> list[str]:
    return sorted(p.stem for p in SCENES_DIR.glob("*.json"))


def delete_scene(name: str) -> None:
    path = SCENES_DIR / f"{_safe(name)}.json"
    if not path.exists():
        raise FileNotFoundError(f"No saved scene named '{name}'.")
    path.unlink()

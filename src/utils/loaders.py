from __future__ import annotations
from pathlib import Path
import yaml

def load_yaml(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))

def load_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")

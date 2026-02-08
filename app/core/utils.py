from __future__ import annotations
from pathlib import Path
from typing import Iterable, List

def expand_user(path: str) -> Path:
    return Path(path).expanduser().resolve()

def is_under_any_root(path: Path, roots: Iterable[Path]) -> bool:
    path = path.resolve()
    for r in roots:
        try:
            path.relative_to(r)
            return True
        except Exception:
            continue
    return False

def safe_join_dir(dir_path: Path, filename: str) -> Path:
    # Prevent path traversal in new names
    filename = filename.replace("/", "_").replace("\\", "_")
    return (dir_path / filename).resolve()

def is_hidden(p: Path) -> bool:
    return p.name.startswith(".")

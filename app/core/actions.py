from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional, List, Literal

ActionType = Literal[
    "ensure_folder",
    "move",
    "rename",
    "open_app",
    "open_path",
    "play_music",
]

@dataclass
class Action:
    type: ActionType
    # Common fields kept flexible
    src: Optional[str] = None
    dst_dir: Optional[str] = None
    path: Optional[str] = None
    new_name: Optional[str] = None
    name: Optional[str] = None

    # metadata
    risk: str = "low"  # low | medium | high
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Remove None fields for cleanliness
        return {k: v for k, v in d.items() if v is not None}

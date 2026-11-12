"""Application settings.

All settings come from environment variables prefixed ``URTISCAN_`` so the same code runs
on a laptop, in CI and in a pilot deployment without edits.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _env(name: str, default: str) -> str:
    return os.environ.get(f"URTISCAN_{name}", default)


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", str(_REPO_ROOT / "data"))))
    database_url: str = ""
    detector: str = field(default_factory=lambda: _env("DETECTOR", "heuristic"))
    yolo_weights: str = field(default_factory=lambda: _env("YOLO_WEIGHTS", ""))
    marker_mm: float = field(default_factory=lambda: float(_env("MARKER_MM", "20")))
    confidence_threshold: float = field(
        default_factory=lambda: float(_env("CONFIDENCE_THRESHOLD", "0.5"))
    )
    # Long edge of the working copy used for analysis. Originals are kept untouched.
    working_long_edge: int = field(default_factory=lambda: int(_env("WORKING_LONG_EDGE", "2048")))

    def __post_init__(self) -> None:
        if not self.database_url:
            url = _env("DATABASE_URL", f"sqlite:///{self.data_dir / 'urtiscan.db'}")
            object.__setattr__(self, "database_url", url)

    @property
    def photos_dir(self) -> Path:
        return self.data_dir / "photos"


settings = Settings()

"""Stage 4: wheal detection. Detectors are interchangeable behind ``WhealDetector``."""
from __future__ import annotations

from typing import Optional, Protocol

import numpy as np

from ..types import AnalysisContext, Calibration, LesionCandidate


class WhealDetector(Protocol):
    name: str
    version: str

    def detect(
        self,
        image_bgr: np.ndarray,
        lab: np.ndarray,
        skin_mask: np.ndarray,
        calibration: Optional[Calibration],
    ) -> list[LesionCandidate]:
        """Return one candidate per individual wheal (or confluent plaque)."""
        ...


class DetectorStage:
    """Adapts any ``WhealDetector`` to the pipeline ``Stage`` interface."""

    name = "detector"

    def __init__(self, detector: WhealDetector):
        self.detector = detector
        self.version = f"{detector.name}@{detector.version}"

    def run(self, ctx: AnalysisContext) -> None:
        assert ctx.skin_mask is not None, "skin stage must run before detection"
        ctx.candidates = self.detector.detect(ctx.image_bgr, ctx.lab, ctx.skin_mask, ctx.calibration)


def build_detector(kind: str, yolo_weights: str = "") -> WhealDetector:
    """Factory used by the app. Add new detector types here."""
    if kind == "heuristic":
        from .heuristic import HeuristicWhealDetector

        return HeuristicWhealDetector()
    if kind == "yolo":
        from .yolo import YoloSegWhealDetector

        if not yolo_weights:
            raise ValueError("URTISCAN_YOLO_WEIGHTS must point to trained YOLO-seg weights")
        return YoloSegWhealDetector(yolo_weights)
    raise ValueError(f"Unknown detector '{kind}'. Use 'heuristic' or 'yolo'.")

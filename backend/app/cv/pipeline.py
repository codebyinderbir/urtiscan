"""Composes the stages into one analysis run.

The default pipeline is::

    quality -> calibration -> skin -> detector -> measure -> summary

If a stage asks to abstain (e.g. the photo is too blurry), detection and measurement are
skipped but a summary is still produced, with status ``insufficient_evidence``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from .calibration import CalibrationStage
from .detectors import DetectorStage, WhealDetector, build_detector
from .measure import MeasurementStage
from .quality import QualityStage
from .skin import SkinMaskStage
from .summary import SummaryStage
from .types import AnalysisContext, Stage

PIPELINE_VERSION = "mvp-1"
_SKIP_WHEN_ABSTAINING = {"detector", "measure"}


@dataclass
class Pipeline:
    stages: Sequence[Stage]
    marker_mm: float = 20.0
    confidence_threshold: float = 0.5

    @property
    def versions(self) -> dict[str, str]:
        return {"pipeline": PIPELINE_VERSION, **{s.name: s.version for s in self.stages}}

    def run(self, image_bgr: np.ndarray) -> AnalysisContext:
        ctx = AnalysisContext(
            image_bgr=image_bgr,
            marker_mm=self.marker_mm,
            confidence_threshold=self.confidence_threshold,
        )
        for stage in self.stages:
            if ctx.abstain_reasons and stage.name in _SKIP_WHEN_ABSTAINING:
                continue
            stage.run(ctx)
        return ctx


def default_pipeline(
    detector: Optional[WhealDetector] = None,
    detector_kind: str = "heuristic",
    yolo_weights: str = "",
    marker_mm: float = 20.0,
    confidence_threshold: float = 0.5,
) -> Pipeline:
    det = detector or build_detector(detector_kind, yolo_weights)
    return Pipeline(
        stages=[
            QualityStage(),
            CalibrationStage(),
            SkinMaskStage(),
            DetectorStage(det),
            MeasurementStage(),
            SummaryStage(),
        ],
        marker_mm=marker_mm,
        confidence_threshold=confidence_threshold,
    )

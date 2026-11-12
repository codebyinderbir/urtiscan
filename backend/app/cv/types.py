"""Shared data types passed between pipeline stages."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Protocol

import cv2
import numpy as np

Verdict = Literal["ok", "warn", "fail"]
SizeClass = Literal["small", "medium", "large"]


@dataclass
class QualityReport:
    """Image-quality metrics. ``verdict == 'fail'`` stops the analysis."""

    width: int
    height: int
    blur_score: float  # variance of the Laplacian on a normalised grey image; higher = sharper
    brightness: float  # mean L* (0-100)
    clipped_dark_pct: float
    clipped_bright_pct: float
    glare_pct: float  # bright, desaturated pixels (flash reflections)
    verdict: Verdict
    warnings: list[str] = field(default_factory=list)


@dataclass
class Calibration:
    """Physical scale for the image, if a reference marker was found."""

    mm_per_px: Optional[float]
    marker_detected: bool
    method: str  # "aruco" | "none"
    marker_corners: Optional[list[list[float]]] = None


@dataclass
class LesionCandidate:
    """A raw detection from a detector, before measurement."""

    polygon: np.ndarray  # (N, 2) int32, working-image pixel coordinates
    score: float  # detector confidence 0-1
    source: str = "ai"


@dataclass
class LesionMeasurement:
    """A measured lesion. Millimetre fields are ``None`` when the image is uncalibrated."""

    polygon: list[list[int]]
    confidence: float
    source: str
    area_px: int
    equiv_diameter_px: float
    max_feret_px: float
    solidity: float
    centroid: tuple[float, float]
    area_mm2: Optional[float] = None
    equiv_diameter_mm: Optional[float] = None
    max_feret_mm: Optional[float] = None
    size_class: Optional[SizeClass] = None
    is_confluent: bool = False
    delta_a_star: Optional[float] = None


@dataclass
class AnalysisSummary:
    status: Literal["done", "insufficient_evidence"]
    visible_count: int
    expected_count: float
    count_low: int
    count_high: int
    image_confidence: float
    confluent_present: bool
    confluent_area_pct: float  # % of affected area that is confluent
    skin_area_px: int
    affected_area_px: int
    affected_pct_of_photographed_skin: float
    suggested_score_band: list[int]  # possible 0-3 wheal scores for THIS photo only
    insufficient_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ita_degrees: Optional[float] = None  # individual typology angle of unaffected skin
    median_delta_a_star: Optional[float] = None


@dataclass
class AnalysisContext:
    """Mutable state handed from stage to stage."""

    image_bgr: np.ndarray  # uint8 working copy
    marker_mm: float = 20.0
    confidence_threshold: float = 0.5
    quality: Optional[QualityReport] = None
    calibration: Optional[Calibration] = None
    skin_mask: Optional[np.ndarray] = None  # uint8 0/255
    candidates: list[LesionCandidate] = field(default_factory=list)
    lesions: list[LesionMeasurement] = field(default_factory=list)
    summary: Optional[AnalysisSummary] = None
    warnings: list[str] = field(default_factory=list)
    abstain_reasons: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)
    _lab: Optional[np.ndarray] = None

    @property
    def lab(self) -> np.ndarray:
        """Image in true CIELAB units: L* 0-100, a*/b* roughly -128..127 (float32)."""
        if self._lab is None:
            rgb01 = self.image_bgr.astype(np.float32) / 255.0
            self._lab = cv2.cvtColor(rgb01, cv2.COLOR_BGR2LAB)
        return self._lab

    @property
    def height(self) -> int:
        return int(self.image_bgr.shape[0])

    @property
    def width(self) -> int:
        return int(self.image_bgr.shape[1])


class Stage(Protocol):
    """Every pipeline step implements this. ``version`` is stored with each result."""

    name: str
    version: str

    def run(self, ctx: AnalysisContext) -> None:
        """Read from and write to ``ctx``. Append to ``ctx.abstain_reasons`` to stop the run."""
        ...

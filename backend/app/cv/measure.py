"""Stage 5: per-lesion measurements, size classes, confluence and erythema (Δa*).

All geometry is computed on bounding-box-local rasters so memory stays small even with
hundreds of lesions on a large photo.
"""
from __future__ import annotations

import math
from typing import Optional, Sequence

import cv2
import numpy as np

from .types import AnalysisContext, LesionCandidate, LesionMeasurement

# Size classes by equivalent diameter (mm). Provisional: confirm with a dermatologist.
SMALL_MAX_MM = 5.0
MEDIUM_MAX_MM = 15.0
# Confluence rules (see design doc, "How detection, counting and measurement work").
CONFLUENT_SOLIDITY = 0.80
CONFLUENT_AREA_RATIO = 3.0
RING_MM = 4.0  # width of perilesional "normal skin" ring for Δa*


def _local_raster(poly: np.ndarray, pad: int, shape: tuple[int, int]):
    h, w = shape
    x, y, bw, bh = cv2.boundingRect(poly.reshape(-1, 1, 2).astype(np.int32))
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(w, x + bw + pad), min(h, y + bh + pad)
    m = np.zeros((y1 - y0, x1 - x0), np.uint8)
    cv2.fillPoly(m, [(poly - [x0, y0]).reshape(-1, 1, 2).astype(np.int32)], 255)
    return m, (x0, y0, x1, y1)


def union_mask(polys: Sequence[np.ndarray], shape: tuple[int, int]) -> np.ndarray:
    m = np.zeros(shape, np.uint8)
    if polys:
        cv2.fillPoly(m, [p.reshape(-1, 1, 2).astype(np.int32) for p in polys], 255)
    return m


def measure_polygon(
    poly: np.ndarray,
    confidence: float,
    source: str,
    lab: np.ndarray,
    skin_mask: np.ndarray,
    all_lesions: np.ndarray,
    mm_per_px: Optional[float],
) -> Optional[LesionMeasurement]:
    """Measure one lesion. ``all_lesions`` is the union mask (excluded from the ring)."""
    poly = np.asarray(poly, np.int32).reshape(-1, 2)
    if len(poly) < 3:
        return None
    ring_px = int(round(RING_MM / mm_per_px)) if mm_per_px else 0
    m, (x0, y0, x1, y1) = _local_raster(poly, pad=0, shape=skin_mask.shape)
    area = int(np.count_nonzero(m))
    if area == 0:
        return None

    hull = cv2.convexHull(poly.reshape(-1, 1, 2)).reshape(-1, 2).astype(np.float64)
    hull_area = cv2.contourArea(hull.astype(np.float32))
    solidity = float(min(1.0, cv2.contourArea(poly.astype(np.float32)) / hull_area)) if hull_area > 0 else 1.0
    diffs = hull[:, None, :] - hull[None, :, :]
    feret = float(np.sqrt((diffs**2).sum(-1)).max()) if len(hull) > 1 else 0.0
    eqd = 2 * math.sqrt(area / math.pi)
    ys, xs = np.nonzero(m)
    centroid = (float(xs.mean() + x0), float(ys.mean() + y0))

    # Erythema: mean a* inside minus mean a* of nearby unaffected skin.
    if not ring_px:
        ring_px = int(np.clip(eqd * 0.5, 4, 40))
    rm, (rx0, ry0, rx1, ry1) = _local_raster(poly, pad=ring_px, shape=skin_mask.shape)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * ring_px + 1, 2 * ring_px + 1))
    ring = (cv2.dilate(rm, k) > 0) & (rm == 0)
    ring &= skin_mask[ry0:ry1, rx0:rx1] > 0
    ring &= all_lesions[ry0:ry1, rx0:rx1] == 0
    a = lab[..., 1]
    inside_a = float(a[y0:y1, x0:x1][m > 0].mean())
    delta_a = round(inside_a - float(a[ry0:ry1, rx0:rx1][ring].mean()), 2) if ring.sum() >= 20 else None

    lm = LesionMeasurement(
        polygon=poly.tolist(),
        confidence=round(float(confidence), 3),
        source=source,
        area_px=area,
        equiv_diameter_px=round(eqd, 2),
        max_feret_px=round(feret, 2),
        solidity=round(solidity, 3),
        centroid=(round(centroid[0], 1), round(centroid[1], 1)),
        delta_a_star=delta_a,
    )
    if mm_per_px:
        lm.area_mm2 = round(area * mm_per_px**2, 2)
        lm.equiv_diameter_mm = round(eqd * mm_per_px, 2)
        lm.max_feret_mm = round(feret * mm_per_px, 2)
        d = lm.equiv_diameter_mm
        lm.size_class = "small" if d < SMALL_MAX_MM else ("medium" if d <= MEDIUM_MAX_MM else "large")
    return lm


def flag_confluence(lesions: list[LesionMeasurement]) -> None:
    """Mark lesions that look like merged wheals (irregular, or much larger than typical)."""
    if not lesions:
        return
    median_area = float(np.median([l.area_px for l in lesions]))
    for l in lesions:
        irregular = l.solidity < CONFLUENT_SOLIDITY and (l.area_px > 1.5 * median_area or l.solidity < 0.7)
        oversized = len(lesions) >= 3 and l.area_px > CONFLUENT_AREA_RATIO * median_area and l.solidity < 0.9
        l.is_confluent = bool(irregular or oversized)


def measure_all(
    candidates: Sequence[LesionCandidate],
    lab: np.ndarray,
    skin_mask: np.ndarray,
    mm_per_px: Optional[float],
) -> list[LesionMeasurement]:
    union = union_mask([c.polygon for c in candidates], skin_mask.shape)
    out = []
    for c in candidates:
        lm = measure_polygon(c.polygon, c.score, c.source, lab, skin_mask, union, mm_per_px)
        if lm is not None:
            out.append(lm)
    flag_confluence(out)
    return out


class MeasurementStage:
    name = "measure"
    version = "0.1.0"

    def run(self, ctx: AnalysisContext) -> None:
        assert ctx.skin_mask is not None
        mmpp = ctx.calibration.mm_per_px if ctx.calibration else None
        ctx.lesions = measure_all(ctx.candidates, ctx.lab, ctx.skin_mask, mmpp)

"""YOLO-seg detector (Phase 1b onward, once a model is trained).

Install with ``pip install -r requirements-ml.txt`` and set
``URTISCAN_DETECTOR=yolo URTISCAN_YOLO_WEIGHTS=/path/best.pt``.

Inference runs on overlapping tiles so small wheals are not lost when a large photo is
downscaled to the network's input size. Detections from neighbouring tiles are merged with
mask-IoU non-maximum suppression.
"""
from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from ..types import Calibration, LesionCandidate

TILE = 1024
OVERLAP = 0.2
NMS_IOU = 0.5
MIN_SCORE = 0.15  # keep low-confidence detections; the UI shows them for review


class YoloSegWhealDetector:
    name = "yolo-seg"

    def __init__(self, weights: str):
        from ultralytics import YOLO  # imported lazily: optional dependency

        self.model = YOLO(weights)
        self.version = weights.rsplit("/", 1)[-1]

    def detect(
        self,
        image_bgr: np.ndarray,
        lab: np.ndarray,
        skin_mask: np.ndarray,
        calibration: Optional[Calibration],
    ) -> list[LesionCandidate]:
        h, w = image_bgr.shape[:2]
        found: list[LesionCandidate] = []
        for x0, y0, x1, y1 in tile_boxes(w, h, TILE, OVERLAP):
            tile = image_bgr[y0:y1, x0:x1]
            result = self.model.predict(tile, imgsz=TILE, conf=MIN_SCORE, verbose=False)[0]
            if result.masks is None:
                continue
            for poly, score in zip(result.masks.xy, result.boxes.conf.tolist()):
                if len(poly) < 3:
                    continue
                pts = (np.asarray(poly) + [x0, y0]).round().astype(np.int32)
                found.append(LesionCandidate(polygon=pts, score=float(score)))

        # Drop detections that fall mostly outside skin (background false positives).
        found = [c for c in found if _fraction_inside(c.polygon, skin_mask) >= 0.5]
        return mask_nms(found, (h, w), NMS_IOU)


def tile_boxes(w: int, h: int, tile: int, overlap: float) -> list[tuple[int, int, int, int]]:
    """Overlapping tile rectangles covering the whole image."""
    step = max(1, int(tile * (1 - overlap)))
    xs = list(range(0, max(1, w - tile) + 1, step)) or [0]
    ys = list(range(0, max(1, h - tile) + 1, step)) or [0]
    if xs[-1] + tile < w:
        xs.append(w - tile)
    if ys[-1] + tile < h:
        ys.append(h - tile)
    return [(x, y, min(w, x + tile), min(h, y + tile)) for y in ys for x in xs]


def _raster(poly: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    m = np.zeros(shape, np.uint8)
    cv2.fillPoly(m, [poly.reshape(-1, 1, 2)], 1)
    return m


def _fraction_inside(poly: np.ndarray, mask: np.ndarray) -> float:
    m = _raster(poly, mask.shape)
    total = m.sum()
    return float((m & (mask > 0)).sum() / total) if total else 0.0


def mask_nms(
    cands: list[LesionCandidate], shape: tuple[int, int], iou_thr: float
) -> list[LesionCandidate]:
    """Greedy NMS on polygon masks (highest score wins)."""
    cands = sorted(cands, key=lambda c: c.score, reverse=True)
    kept: list[tuple[LesionCandidate, np.ndarray]] = []
    for c in cands:
        m = _raster(c.polygon, shape)
        if not m.any():
            continue
        duplicate = False
        for _, km in kept:
            inter = np.logical_and(m, km).sum()
            union = np.logical_or(m, km).sum()
            # Also treat "one mask mostly inside another" as a duplicate (tile-edge crops).
            if inter / union > iou_thr or inter / min(m.sum(), km.sum()) > 0.8:
                duplicate = True
                break
        if not duplicate:
            kept.append((c, m))
    return [c for c, _ in kept]

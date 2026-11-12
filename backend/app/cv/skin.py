"""Stage 3: skin mask (the denominator for "% of photographed skin affected").

MVP: a broad colour-range heuristic in HSV, deliberately permissive so it includes light and
dark skin. It removes obvious background (clothes, walls, the scale marker) but is NOT a
substitute for a trained skin-segmentation model (U-Net / SegFormer, Phase 3). Swap this stage
for a learned one by implementing the same ``run`` method.
"""
from __future__ import annotations

import cv2
import numpy as np

from .types import AnalysisContext

MIN_COVERAGE = 0.15  # below this we fall back to the full frame and warn


def heuristic_skin_mask(image_bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(image_bgr.astype(np.float32) / 255.0, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    hue_ok = (h <= 50) | (h >= 330)  # red-orange-yellow covers skin of all tones
    mask = (hue_ok & (s >= 0.06) & (s <= 0.85) & (v >= 0.10)).astype(np.uint8) * 255

    k = max(3, int(round(min(mask.shape) / 150)) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    # Keep large regions only, and fill holes inside them.
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    min_area = 0.02 * mask.size
    keep = np.zeros_like(mask)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            keep[labels == i] = 255
    contours, _ = cv2.findContours(keep, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(keep)
    cv2.drawContours(filled, contours, -1, 255, thickness=cv2.FILLED)
    return filled


class SkinMaskStage:
    name = "skin"
    version = "hsv-heuristic-0.1.0"

    def run(self, ctx: AnalysisContext) -> None:
        mask = heuristic_skin_mask(ctx.image_bgr)
        if mask.mean() / 255 < MIN_COVERAGE:
            ctx.warnings.append(
                "Could not separate skin from background; the whole photo is treated as skin."
            )
            mask = np.full(ctx.image_bgr.shape[:2], 255, np.uint8)

        # Never count the scale marker as skin.
        cal = ctx.calibration
        if cal and cal.marker_corners:
            pts = np.array(cal.marker_corners, np.float32)
            centre = pts.mean(axis=0)
            grown = ((pts - centre) * 1.4 + centre).astype(np.int32)  # include the white border
            cv2.fillPoly(mask, [grown], 0)

        ctx.skin_mask = mask

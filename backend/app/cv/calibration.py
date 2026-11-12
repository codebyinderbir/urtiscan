"""Stage 2: physical scale from a printed ArUco marker.

The marker is a 4x4 ArUco tag (dictionary DICT_4X4_50) printed at a known size (default 20 mm,
see ``tools/make_marker.py``). Without a marker we report sizes in pixels only and never guess
millimetres.

Colour-card correction is planned for Phase 3 and will live here too.
"""
from __future__ import annotations

import cv2
import numpy as np

from .types import AnalysisContext, Calibration

_DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)


def detect_marker(image_bgr: np.ndarray, marker_mm: float) -> Calibration:
    grey = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    detector = cv2.aruco.ArucoDetector(_DICT, cv2.aruco.DetectorParameters())
    corners, ids, _ = detector.detectMarkers(grey)
    if ids is None or len(ids) == 0:
        return Calibration(mm_per_px=None, marker_detected=False, method="none")

    # Use the largest marker (closest to camera / least foreshortened).
    best = max(corners, key=lambda c: cv2.contourArea(c.reshape(-1, 2).astype(np.float32)))
    pts = best.reshape(4, 2).astype(np.float64)
    sides = [np.linalg.norm(pts[i] - pts[(i + 1) % 4]) for i in range(4)]
    side_px = float(np.mean(sides))
    if side_px < 10:
        return Calibration(mm_per_px=None, marker_detected=False, method="none")
    return Calibration(
        mm_per_px=marker_mm / side_px,
        marker_detected=True,
        method="aruco",
        marker_corners=pts.round(1).tolist(),
    )


class CalibrationStage:
    name = "calibration"
    version = "aruco-0.1.0"

    def run(self, ctx: AnalysisContext) -> None:
        ctx.calibration = detect_marker(ctx.image_bgr, ctx.marker_mm)
        if not ctx.calibration.marker_detected:
            ctx.warnings.append(
                "No scale marker found: sizes are shown in pixels, not millimetres."
            )

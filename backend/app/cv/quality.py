"""Stage 1: image-quality gate.

Classical metrics only; cheap, explainable and independent of skin tone. Thresholds are
starting points and should be re-tuned once real photos are collected.
"""
from __future__ import annotations

import cv2
import numpy as np

from .types import AnalysisContext, QualityReport

# Thresholds (see README). "fail" stops analysis; "warn" lowers confidence.
MIN_SIDE_FAIL = 480
MIN_SIDE_WARN = 900
BLUR_FAIL = 6.0
BLUR_WARN = 20.0
DARK_FAIL, DARK_WARN = 20.0, 35.0  # mean L*
BRIGHT_WARN = 90.0
CLIP_BRIGHT_WARN, CLIP_BRIGHT_FAIL = 15.0, 40.0  # % pixels
CLIP_DARK_WARN = 30.0
GLARE_WARN = 2.0  # % pixels


def assess_quality(image_bgr: np.ndarray, lab: np.ndarray) -> QualityReport:
    h, w = image_bgr.shape[:2]
    warnings: list[str] = []
    fail = False

    # Sharpness on a fixed-size grey image so the score does not depend on resolution.
    scale = 1024 / max(h, w)
    small = cv2.resize(image_bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else image_bgr
    grey = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    blur_score = float(cv2.Laplacian(grey, cv2.CV_64F).var())

    L = lab[..., 0]
    chroma = np.hypot(lab[..., 1], lab[..., 2])
    brightness = float(L.mean())
    clipped_bright = float((L > 98).mean() * 100)
    clipped_dark = float((L < 3).mean() * 100)
    glare = float(((L > 92) & (chroma < 8)).mean() * 100)

    if min(h, w) < MIN_SIDE_FAIL:
        fail = True
        warnings.append(f"Resolution too low ({w}x{h}). Use the full camera resolution.")
    elif min(h, w) < MIN_SIDE_WARN:
        warnings.append("Low resolution; small wheals may be missed.")

    if blur_score < BLUR_FAIL:
        fail = True
        warnings.append("Photo is too blurry to analyse. Hold the camera still and tap to focus.")
    elif blur_score < BLUR_WARN:
        warnings.append("Photo may be slightly blurry.")

    if brightness < DARK_FAIL:
        fail = True
        warnings.append("Photo is too dark. Use brighter, even lighting.")
    elif brightness < DARK_WARN:
        warnings.append("Photo is dark; detection may be less reliable.")
    elif brightness > BRIGHT_WARN:
        warnings.append("Photo is very bright; it may be overexposed.")

    if clipped_bright > CLIP_BRIGHT_FAIL:
        fail = True
        warnings.append("Large overexposed areas. Avoid direct light or flash.")
    elif clipped_bright > CLIP_BRIGHT_WARN:
        warnings.append("Some areas are overexposed.")
    if clipped_dark > CLIP_DARK_WARN:
        warnings.append("Large areas are in deep shadow.")
    if glare > GLARE_WARN:
        warnings.append("Flash glare or reflections detected. Turn off the flash and use diffuse light.")

    verdict = "fail" if fail else ("warn" if warnings else "ok")
    return QualityReport(
        width=w,
        height=h,
        blur_score=round(blur_score, 2),
        brightness=round(brightness, 2),
        clipped_dark_pct=round(clipped_dark, 2),
        clipped_bright_pct=round(clipped_bright, 2),
        glare_pct=round(glare, 2),
        verdict=verdict,
        warnings=warnings,
    )


class QualityStage:
    name = "quality"
    version = "classical-0.1.0"

    def run(self, ctx: AnalysisContext) -> None:
        ctx.quality = assess_quality(ctx.image_bgr, ctx.lab)
        ctx.warnings.extend(ctx.quality.warnings)
        if ctx.quality.verdict == "fail":
            ctx.abstain_reasons.append("Image quality is too poor for a reliable analysis.")

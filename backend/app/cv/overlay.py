"""Render an annotated copy of the photo (for export and the photo gallery).

The interactive review screen draws its own overlay in the browser; this PNG is the static
record of what the AI (and later the reviewer) marked.
"""
from __future__ import annotations

from typing import Optional, Sequence

import cv2
import numpy as np

from .types import LesionMeasurement

# BGR colours by size class; confluent lesions are drawn in magenta and hatched.
COLOURS = {
    "small": (255, 200, 0),
    "medium": (0, 200, 255),
    "large": (0, 90, 255),
    None: (255, 255, 0),
}
CONFLUENT = (200, 0, 200)


def render_overlay(
    image_bgr: np.ndarray,
    lesions: Sequence[LesionMeasurement],
    labels: Optional[Sequence[int]] = None,
) -> np.ndarray:
    out = image_bgr.copy()
    h, w = out.shape[:2]
    thick = max(2, round(min(h, w) / 600))
    font = max(0.4, min(h, w) / 1600)
    hatch = np.zeros((h, w), np.uint8)
    for y in range(-w, h, max(6, thick * 4)):
        cv2.line(hatch, (0, y), (w, y + w), 255, 1)

    for idx, l in enumerate(lesions, start=1):
        pts = np.asarray(l.polygon, np.int32).reshape(-1, 1, 2)
        colour = CONFLUENT if l.is_confluent else COLOURS.get(l.size_class, COLOURS[None])
        if l.is_confluent:
            m = np.zeros((h, w), np.uint8)
            cv2.fillPoly(m, [pts], 255)
            out[(m > 0) & (hatch > 0)] = colour
        cv2.polylines(out, [pts], True, colour, thick, cv2.LINE_AA)
        cx, cy = int(l.centroid[0]), int(l.centroid[1])
        label = str(labels[idx - 1] if labels else idx)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font, 1)
        cv2.rectangle(out, (cx - tw // 2 - 2, cy - th // 2 - 3), (cx + tw // 2 + 2, cy + th // 2 + 3), (0, 0, 0), -1)
        cv2.putText(out, label, (cx - tw // 2, cy + th // 2), cv2.FONT_HERSHEY_SIMPLEX, font, (255, 255, 255), 1, cv2.LINE_AA)
    return out

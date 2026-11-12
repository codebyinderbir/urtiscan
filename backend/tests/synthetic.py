"""Synthetic test photos with known ground truth.

These are NOT realistic urticaria images. They exist to test the plumbing (counting, splitting,
measurement units, calibration) deterministically. Real performance must be measured on
expert-labelled photos.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

SKIN_TONES = {  # RGB
    "light": (226, 186, 164),
    "medium": (196, 142, 108),
    "dark": (112, 74, 54),
}


@dataclass
class Wheal:
    cx: float
    cy: float
    rx: float
    ry: float
    angle: float = 0.0


@dataclass
class SyntheticPhoto:
    image_bgr: np.ndarray
    wheals: list[Wheal]
    px_per_mm: float
    separate_count: int  # wheals that do not overlap another wheal
    groups: list[list[int]] = field(default_factory=list)


def make_photo(
    seed: int = 0,
    n_isolated: int = 12,
    n_pairs: int = 2,
    tone: str = "light",
    size: tuple[int, int] = (2400, 1800),
    px_per_mm: float = 8.0,
    marker: bool = True,
    blur: float = 0.0,
    redness: float = 1.0,
) -> SyntheticPhoto:
    rng = np.random.default_rng(seed)
    w, h = size
    img = np.empty((h, w, 3), np.float32)
    img[:] = (150, 160, 170)[::-1]  # bluish-grey wall (BGR)

    # Skin region: a large rounded "forearm".
    skin = np.zeros((h, w), np.uint8)
    cv2.ellipse(skin, (w // 2, h // 2), (int(w * 0.46), int(h * 0.36)), 0, 0, 360, 255, -1)
    base = np.array(SKIN_TONES[tone][::-1], np.float32)
    shade = cv2.GaussianBlur(rng.normal(0, 1, (h // 20, w // 20)).astype(np.float32), (0, 0), 3)
    shade = cv2.resize(shade, (w, h)) * 6
    texture = rng.normal(0, 2.5, (h, w)).astype(np.float32)
    skin_px = base[None, None, :] + (shade + texture)[..., None]
    img[skin > 0] = skin_px[skin > 0]

    wheals: list[Wheal] = []

    def free_spot(r: float) -> tuple[float, float]:
        for _ in range(500):
            cx = rng.uniform(w * 0.12, w * 0.88)
            cy = rng.uniform(h * 0.22, h * 0.78)
            if ((cx - w / 2) / (w * 0.42)) ** 2 + ((cy - h / 2) / (h * 0.32)) ** 2 > 1:
                continue
            if all(np.hypot(cx - o.cx, cy - o.cy) > r + max(o.rx, o.ry) + 6 * px_per_mm for o in wheals):
                return cx, cy
        raise RuntimeError("no free spot")

    for _ in range(n_isolated):
        r = rng.uniform(2.5, 7) * px_per_mm  # 5-14 mm diameter
        cx, cy = free_spot(r)
        wheals.append(Wheal(cx, cy, r, r * rng.uniform(0.7, 1.0), rng.uniform(0, 180)))
    groups = []
    for _ in range(n_pairs):  # two wheals touching through a narrow neck
        r = rng.uniform(4, 6) * px_per_mm
        cx, cy = free_spot(2.2 * r)
        i = len(wheals)
        wheals.append(Wheal(cx - 0.95 * r, cy, r, r))
        wheals.append(Wheal(cx + 0.95 * r, cy, r, r))
        groups.append([i, i + 1])

    # Wheal appearance: redder (a* up), slightly paler centre, soft edge.
    red = np.zeros((h, w), np.float32)
    for wh in wheals:
        m = np.zeros((h, w), np.uint8)
        cv2.ellipse(m, (int(wh.cx), int(wh.cy)), (int(wh.rx), int(wh.ry)), wh.angle, 0, 360, 255, -1)
        red = np.maximum(red, cv2.GaussianBlur(m.astype(np.float32) / 255, (0, 0), 1.5))
    red *= skin > 0
    delta_bgr = np.array([-14, -30, 8], np.float32) * redness  # less green/blue, more red
    img += red[..., None] * delta_bgr[None, None, :]

    if marker:
        side = int(round(20 * px_per_mm))
        tag = cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50), 0, side)
        border = side // 4
        x0, y0 = int(w * 0.04), int(h * 0.04)
        img[y0 - border : y0 + side + border, x0 - border : x0 + side + border] = 255
        img[y0 : y0 + side, x0 : x0 + side] = tag[..., None]

    if blur:
        img = cv2.GaussianBlur(img, (0, 0), blur)
    out = np.clip(img, 0, 255).astype(np.uint8)
    return SyntheticPhoto(out, wheals, px_per_mm, n_isolated, groups)

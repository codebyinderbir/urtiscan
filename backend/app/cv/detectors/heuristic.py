"""Heuristic baseline detector (no training data required).

How it works
------------
1. Estimate each pixel's *local skin background* redness (a* in CIELAB) with a large,
   mask-aware blur, so normal variation in skin tone across the photo is removed.
2. Score every pixel by how much redder it is than its local background (Δa*), in units of the
   image's own robust noise level (z-score).
3. Hysteresis threshold: strong seeds (z > SEED_Z) grow into connected weaker pixels (z > GROW_Z),
   then each blob is trimmed to where its redness is at least half its peak (FWHM edge).
   A second pass re-estimates the background with the first-pass lesions excluded.
4. Split touching blobs at distance-transform peaks (power-diagram assignment); re-merge splits
   joined by a wide neck (those are one lesion, possibly confluent).
5. Confidence = capped logistic of mean z-score. It is NOT calibrated against expert labels.

Known limitations (shown in the UI)
-----------------------------------
* Relies on redness, so it under-detects wheals on darker skin and skin-coloured wheals.
* Cannot see elevation; flat erythema, scratches and dermographism lines may be detected.
* Replace with ``YoloSegWhealDetector`` once a labelled dataset exists.
"""
from __future__ import annotations

import math
from typing import Optional

import cv2
import numpy as np

from ..types import Calibration, LesionCandidate

SEED_Z = 3.5
GROW_Z = 2.0
MIN_DELTA_A = 3.0  # absolute Δa* floor: below this redness difference is barely perceptible
MIN_DIAMETER_MM = 2.0
CONFIDENCE_CAP = 0.85  # heuristic scores never claim more than this


def _masked_blur(img: np.ndarray, mask: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussian blur that ignores pixels outside ``mask`` (normalised convolution).

    Done at reduced resolution for speed; the background varies slowly anyway.
    """
    h, w = img.shape
    f = max(1, int(sigma // 8))
    small_img = cv2.resize(img * mask, (w // f, h // f), interpolation=cv2.INTER_AREA)
    small_mask = cv2.resize(mask, (w // f, h // f), interpolation=cv2.INTER_AREA)
    s = sigma / f
    num = cv2.GaussianBlur(small_img, (0, 0), s)
    den = cv2.GaussianBlur(small_mask, (0, 0), s)
    out = num / np.maximum(den, 1e-3)
    return cv2.resize(out, (w, h), interpolation=cv2.INTER_LINEAR)


def _hysteresis(z: np.ndarray, skin: np.ndarray, delta: np.ndarray) -> np.ndarray:
    weak = ((z > GROW_Z) & (delta > MIN_DELTA_A * 0.6) & skin).astype(np.uint8)
    strong = (z > SEED_Z) & (delta > MIN_DELTA_A) & skin
    n, labels = cv2.connectedComponents(weak, connectivity=8)
    if n <= 1:
        return np.zeros_like(weak)
    keep_ids = np.unique(labels[strong])
    keep_ids = keep_ids[keep_ids > 0]
    return np.isin(labels, keep_ids).astype(np.uint8) * 255


class HeuristicWhealDetector:
    name = "heuristic-lab-redness"
    version = "0.1.0"

    def detect(
        self,
        image_bgr: np.ndarray,
        lab: np.ndarray,
        skin_mask: np.ndarray,
        calibration: Optional[Calibration],
    ) -> list[LesionCandidate]:
        h, w = skin_mask.shape
        min_dim = min(h, w)
        skin = skin_mask > 0
        skin_f = skin.astype(np.float32)

        a = cv2.GaussianBlur(lab[..., 1], (0, 0), max(1.0, min_dim / 500))
        bg_sigma = min_dim / 12

        # Minimum lesion area in pixels.
        if calibration and calibration.mm_per_px:
            r_px = (MIN_DIAMETER_MM / 2) / calibration.mm_per_px
            min_area = max(12.0, math.pi * r_px * r_px)
        else:
            min_area = max(12.0, 3e-5 * h * w)

        lesion_mask = np.zeros((h, w), np.uint8)
        z = np.zeros_like(a)
        for _ in range(2):  # pass 2 excludes pass-1 lesions from the background estimate
            bg_mask = skin_f * (lesion_mask == 0)
            bg = _masked_blur(a, bg_mask, bg_sigma)
            delta = a - bg
            ref = delta[(bg_mask > 0)]
            if ref.size < 100:
                return []
            med = float(np.median(ref))
            mad = float(np.median(np.abs(ref - med))) * 1.4826
            sigma = max(mad, 1.0)
            delta = delta - med
            z = delta / sigma
            lesion_mask = _hysteresis(z, skin, delta)

        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        lesion_mask = cv2.morphologyEx(lesion_mask, cv2.MORPH_OPEN, k)
        lesion_mask = _half_max_boundary(lesion_mask, delta)
        lesion_mask = _fill_holes(lesion_mask)

        candidates: list[LesionCandidate] = []
        n, labels, stats, _ = cv2.connectedComponentsWithStats(lesion_mask, connectivity=8)
        for i in range(1, n):
            if stats[i, cv2.CC_STAT_AREA] < min_area:
                continue
            x, y, bw, bh = stats[i, :4]
            pad = 2
            x0, y0 = max(0, x - pad), max(0, y - pad)
            x1, y1 = min(w, x + bw + pad), min(h, y + bh + pad)
            comp = (labels[y0:y1, x0:x1] == i).astype(np.uint8) * 255
            for seg in _split_touching(comp, min_area):
                area = int(np.count_nonzero(seg))
                if area < min_area:
                    continue
                mean_z = float(z[y0:y1, x0:x1][seg > 0].mean())
                poly = _polygon(seg, (x0, y0))
                if poly is None:
                    continue
                size_factor = min(1.0, area / (3 * min_area)) ** 0.5
                conf = CONFIDENCE_CAP * _sigmoid((mean_z - SEED_Z) / 1.2) * (0.6 + 0.4 * size_factor)
                candidates.append(LesionCandidate(polygon=poly, score=round(float(conf), 3)))
        return candidates


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _half_max_boundary(mask: np.ndarray, delta: np.ndarray) -> np.ndarray:
    """Trim each blob to where redness is >= half its peak (full-width-at-half-maximum edge).

    Hysteresis alone lets blobs creep outward along soft edges, which inflates diameters.
    """
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    out = np.zeros_like(mask)
    for i in range(1, n):
        x, y, bw, bh = stats[i, :4]
        sl = (slice(y, y + bh), slice(x, x + bw))
        comp = labels[sl] == i
        peak = float(np.percentile(delta[sl][comp], 95))
        out[sl][comp & (delta[sl] >= 0.5 * peak)] = 255
    return out


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = np.zeros_like(mask)
    cv2.drawContours(out, contours, -1, 255, thickness=cv2.FILLED)
    return out


def _split_touching(comp: np.ndarray, min_area: float) -> list[np.ndarray]:
    """Split a blob of touching wheals; returns one mask per lesion.

    Each local maximum of the distance transform is treated as the centre of a roughly round
    wheal with radius = its distance value. Pixels are assigned to the centre with the smallest
    *power distance* |p - c|^2 - r^2. For two overlapping circles this boundary is exactly the
    line through their intersection points, so the split follows the visible "waist".
    """
    dist = cv2.distanceTransform(comp, cv2.DIST_L2, 5)
    r_min = max(2.0, math.sqrt(min_area / math.pi))
    max_d = float(dist.max())
    if max_d < 2 * r_min:  # too small to contain two lesions
        return [comp]

    ksize = int(2 * r_min) | 1
    dil = cv2.dilate(dist, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize)))
    peaks = ((dist >= dil - 1e-6) & (dist >= max(r_min, 0.35 * max_d))).astype(np.uint8)
    n_peaks, peak_lbl = cv2.connectedComponents(peaks, connectivity=8)
    if n_peaks <= 2:  # background label + one peak
        return [comp]

    centres, radii = [], []
    for lbl in range(1, n_peaks):
        ys, xs = np.nonzero(peak_lbl == lbl)
        centres.append((xs.mean(), ys.mean()))
        radii.append(float(dist[ys, xs].max()))
    c = np.array(centres, np.float32)
    r = np.array(radii, np.float32)

    ys, xs = np.nonzero(comp)
    pts = np.stack([xs, ys], axis=1).astype(np.float32)
    power = ((pts[:, None, :] - c[None, :, :]) ** 2).sum(-1) - r[None, :] ** 2
    owner = power.argmin(axis=1)

    segs = []
    for k in range(len(c)):
        seg = np.zeros_like(comp)
        sel = owner == k
        seg[ys[sel], xs[sel]] = 255
        if np.count_nonzero(seg):
            segs.append(seg)
    return _merge_wide_necks(segs, dist)


def _merge_wide_necks(segs: list[np.ndarray], dist: np.ndarray) -> list[np.ndarray]:
    """Re-join segments whose shared boundary is nearly as wide as the smaller segment."""
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    merged = True
    while merged and len(segs) > 1:
        merged = False
        for i in range(len(segs)):
            for j in range(i + 1, len(segs)):
                neck = (cv2.dilate(segs[i], k) & cv2.dilate(segs[j], k)) > 0
                if not neck.any():
                    continue
                # The distance-transform value at the saddle is half the neck width.
                neck_width = 2.0 * float(dist[neck].max())
                r_small = min(float(dist[segs[i] > 0].max()), float(dist[segs[j] > 0].max()))
                if neck_width > 0.8 * (2.0 * r_small):  # neck nearly as wide as the smaller lesion
                    segs[i] = segs[i] | segs[j]
                    del segs[j]
                    merged = True
                    break
            if merged:
                break
    return segs


def _polygon(seg: np.ndarray, offset: tuple[int, int]) -> Optional[np.ndarray]:
    contours, _ = cv2.findContours(seg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None
    c = max(contours, key=cv2.contourArea)
    eps = float(np.clip(0.008 * cv2.arcLength(c, True), 0.7, 2.5))
    c = cv2.approxPolyDP(c, eps, True).reshape(-1, 2)
    if len(c) < 3:
        return None
    return (c + np.array(offset)).astype(np.int32)

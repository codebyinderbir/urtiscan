"""Business logic: run the pipeline on a photo and apply review corrections.

Kept separate from the HTTP layer so it can later run inside a queue worker unchanged.
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from typing import Optional

import cv2
import numpy as np
from sqlalchemy.orm import Session

from ..config import settings
from ..cv.measure import flag_confluence, measure_polygon, union_mask
from ..cv.overlay import render_overlay
from ..cv.pipeline import Pipeline, default_pipeline
from ..cv.summary import summarize
from ..cv.types import AnalysisSummary, LesionMeasurement, QualityReport
from ..models import Analysis, Lesion, LesionCorrection, Photo
from ..storage import ingest, storage


class ReviewLockedError(Exception):
    """Raised when editing an analysis that has been confirmed (reopen it first)."""


@lru_cache(maxsize=1)
def get_pipeline() -> Pipeline:
    return default_pipeline(
        detector_kind=settings.detector,
        yolo_weights=settings.yolo_weights,
        marker_mm=settings.marker_mm,
        confidence_threshold=settings.confidence_threshold,
    )


def confidence_is_calibrated() -> bool:
    """Heuristic scores are never calibrated; a trained model must be calibrated explicitly."""
    return settings.detector != "heuristic" and bool(settings.yolo_weights)


# --------------------------------------------------------------------------- upload + analyse

def create_photo(
    db: Session, data: bytes, filename: Optional[str], region: str, taken_at: Optional[datetime]
) -> Photo:
    img = ingest(data, settings.working_long_edge)
    photo = Photo(
        region=region,
        taken_at=taken_at or img.exif_taken_at or datetime.now(timezone.utc),
        original_filename=filename,
        original_key="",
        working_key="",
        width=img.working_bgr.shape[1],
        height=img.working_bgr.shape[0],
        original_width=img.original_bgr.shape[1],
        original_height=img.original_bgr.shape[0],
        device_model=img.device_model,
    )
    db.add(photo)
    db.flush()  # assigns photo.id
    photo.original_key = storage.put_image(f"{photo.id}/original.jpg", img.original_bgr, 95)
    photo.working_key = storage.put_image(f"{photo.id}/working.jpg", img.working_bgr, 95)
    analyse_photo(db, photo, working=img.working_bgr)
    db.commit()
    db.refresh(photo)
    return photo


def analyse_photo(db: Session, photo: Photo, working: Optional[np.ndarray] = None) -> Analysis:
    image = working if working is not None else storage.get_image(photo.working_key)
    pipeline = get_pipeline()
    ctx = pipeline.run(image)
    assert ctx.summary is not None and ctx.skin_mask is not None

    for old in photo.analyses:
        old.is_current = False

    q = ctx.quality
    analysis = Analysis(
        photo_id=photo.id,
        status=ctx.summary.status,
        model_versions=pipeline.versions,
        quality=q.__dict__ if q else {},
        mm_per_px=ctx.calibration.mm_per_px if ctx.calibration else None,
        marker_corners=ctx.calibration.marker_corners if ctx.calibration else None,
    )
    db.add(analysis)
    db.flush()
    analysis.skin_mask_key = storage.put_image(f"{photo.id}/{analysis.id}/skin_mask.png", ctx.skin_mask)

    for i, lm in enumerate(ctx.lesions, start=1):
        analysis.lesions.append(_lesion_from_measurement(lm, label=i))
    _apply_summary(analysis, ctx.summary)
    _render_overlay(analysis, image)
    photo.analyses.append(analysis)
    return analysis


# --------------------------------------------------------------------------- review actions

def add_lesion(db: Session, analysis: Analysis, polygon: list[list[float]]) -> Lesion:
    _require_editable(analysis)
    image, skin, lab = _load_arrays(analysis)
    poly = np.asarray(polygon, np.float64).round().astype(np.int32)
    poly[:, 0] = poly[:, 0].clip(0, image.shape[1] - 1)
    poly[:, 1] = poly[:, 1].clip(0, image.shape[0] - 1)
    others = union_mask([np.asarray(l.polygon) for l in _active(analysis)], skin.shape)
    lm = measure_polygon(poly, 1.0, "user_added", lab, skin, others, analysis.mm_per_px)
    if lm is None:
        raise ValueError("Polygon has no area.")
    lesion = _lesion_from_measurement(lm, label=_next_label(analysis))
    analysis.lesions.append(lesion)
    db.flush()
    _log(analysis, "add", lesion.id, None, {"polygon": lesion.polygon})
    _recompute(analysis, image, skin, lab)
    db.commit()
    return lesion


def set_lesion_status(db: Session, analysis: Analysis, lesion_id: str, status: str) -> Lesion:
    _require_editable(analysis)
    lesion = _get_lesion(analysis, lesion_id)
    if status == "active" and lesion.status == "merged":
        raise ValueError("Merged lesions cannot be restored individually.")
    before = lesion.status
    lesion.status = status
    _log(analysis, "reject" if status == "rejected" else "restore", lesion.id, {"status": before}, {"status": status})
    _recompute(analysis)
    db.commit()
    return lesion


def merge_lesions(db: Session, analysis: Analysis, lesion_ids: list[str]) -> Lesion:
    """Combine several lesions into one (e.g. the detector split a single wheal)."""
    _require_editable(analysis)
    parts = [_get_lesion(analysis, lid) for lid in lesion_ids]
    if any(p.status != "active" for p in parts):
        raise ValueError("Only active lesions can be merged.")
    image, skin, lab = _load_arrays(analysis)
    m = union_mask([np.asarray(p.polygon) for p in parts], skin.shape)
    # Close small gaps so touching parts become one outline.
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k)
    contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if len(contours) != 1:
        raise ValueError("Lesions must touch or overlap to be merged.")
    poly = cv2.approxPolyDP(contours[0], 1.0, True).reshape(-1, 2)
    others = union_mask([np.asarray(l.polygon) for l in _active(analysis) if l not in parts], skin.shape)
    conf = max(p.confidence for p in parts)
    lm = measure_polygon(poly, conf, "user_merged", lab, skin, others, analysis.mm_per_px)
    assert lm is not None
    merged = _lesion_from_measurement(lm, label=min(p.label for p in parts))
    analysis.lesions.append(merged)
    db.flush()
    for p in parts:
        p.status = "merged"
        p.merged_into = merged.id
    _log(analysis, "merge", merged.id, {"lesion_ids": lesion_ids}, {"polygon": merged.polygon})
    _recompute(analysis, image, skin, lab)
    db.commit()
    return merged


def confirm_review(db: Session, analysis: Analysis) -> Analysis:
    edited = any(c.action in {"add", "reject", "restore", "merge"} for c in analysis.corrections)
    analysis.review_status = "confirmed"
    analysis.reviewed_at = datetime.now(timezone.utc)
    analysis.count_provenance = "patient_corrected" if edited else "patient_reviewed"
    _log(analysis, "confirm", None, None, {"count": len(_active(analysis))})
    _recompute(analysis)
    db.commit()
    return analysis


def reopen_review(db: Session, analysis: Analysis) -> Analysis:
    analysis.review_status = "pending"
    analysis.reviewed_at = None
    analysis.count_provenance = "ai_estimated"
    _log(analysis, "reopen", None, None, None)
    _recompute(analysis)
    db.commit()
    return analysis


def yolo_labels(analysis: Analysis) -> str:
    """Confirmed lesions in YOLO-seg format: ``class x1 y1 x2 y2 ...`` normalised to 0-1."""
    photo = analysis.photo
    lines = []
    for l in _active(analysis):
        coords = " ".join(f"{x / photo.width:.6f} {y / photo.height:.6f}" for x, y in l.polygon)
        lines.append(f"0 {coords}")
    return "\n".join(lines) + ("\n" if lines else "")


def delete_photo(db: Session, photo: Photo) -> None:
    storage.delete_prefix(photo.id)
    db.delete(photo)
    db.commit()


# --------------------------------------------------------------------------- helpers

def _active(analysis: Analysis) -> list[Lesion]:
    return [l for l in analysis.lesions if l.status == "active"]


def _next_label(analysis: Analysis) -> int:
    return max((l.label for l in analysis.lesions), default=0) + 1


def _get_lesion(analysis: Analysis, lesion_id: str) -> Lesion:
    for l in analysis.lesions:
        if l.id == lesion_id:
            return l
    raise KeyError(lesion_id)


def _require_editable(analysis: Analysis) -> None:
    if analysis.review_status == "confirmed":
        raise ReviewLockedError("This review is confirmed. Reopen it to make changes.")


def _log(analysis: Analysis, action: str, lesion_id: Optional[str], before, after) -> None:
    analysis.corrections.append(
        LesionCorrection(action=action, lesion_id=lesion_id, before=before, after=after)
    )


def _load_arrays(analysis: Analysis):
    image = storage.get_image(analysis.photo.working_key)
    skin = storage.get_image(analysis.skin_mask_key, cv2.IMREAD_GRAYSCALE)
    lab = cv2.cvtColor(image.astype(np.float32) / 255.0, cv2.COLOR_BGR2LAB)
    return image, skin, lab


def _to_measurement(l: Lesion) -> LesionMeasurement:
    return LesionMeasurement(
        polygon=l.polygon, confidence=l.confidence, source=l.source, area_px=l.area_px,
        equiv_diameter_px=l.equiv_diameter_px, max_feret_px=l.max_feret_px, solidity=l.solidity,
        centroid=(l.centroid_x, l.centroid_y), area_mm2=l.area_mm2,
        equiv_diameter_mm=l.equiv_diameter_mm, max_feret_mm=l.max_feret_mm,
        size_class=l.size_class, is_confluent=l.is_confluent, delta_a_star=l.delta_a_star,
    )


def _lesion_from_measurement(lm: LesionMeasurement, label: int) -> Lesion:
    return Lesion(
        label=label, polygon=lm.polygon, confidence=lm.confidence, source=lm.source,
        area_px=lm.area_px, area_mm2=lm.area_mm2, equiv_diameter_px=lm.equiv_diameter_px,
        equiv_diameter_mm=lm.equiv_diameter_mm, max_feret_px=lm.max_feret_px,
        max_feret_mm=lm.max_feret_mm, solidity=lm.solidity, centroid_x=lm.centroid[0],
        centroid_y=lm.centroid[1], size_class=lm.size_class, is_confluent=lm.is_confluent,
        delta_a_star=lm.delta_a_star,
    )


def _recompute(analysis: Analysis, image=None, skin=None, lab=None) -> None:
    """Re-derive confluence flags, the summary and the overlay from the active lesions."""
    if image is None:
        image, skin, lab = _load_arrays(analysis)
    active = _active(analysis)
    measurements = [_to_measurement(l) for l in active]
    flag_confluence(measurements)
    for l, m in zip(active, measurements):
        l.is_confluent = m.is_confluent
    q = analysis.quality or {}
    quality = QualityReport(**q) if q else None
    # Abstain reasons that came from the image itself (quality) still apply after review.
    image_reasons = [r for r in analysis.insufficient_reasons if "quality" in r.lower()]
    summary = summarize(
        measurements, skin, lab, quality, settings.confidence_threshold,
        confirmed=analysis.review_status == "confirmed",
        abstain_reasons=image_reasons,
        warnings=[w for w in analysis.warnings if "confluent" not in w.lower() and "darker skin" not in w.lower()],
    )
    _apply_summary(analysis, summary)
    _render_overlay(analysis, image)


def _apply_summary(analysis: Analysis, s: AnalysisSummary) -> None:
    analysis.status = s.status
    analysis.insufficient_reasons = s.insufficient_reasons
    analysis.warnings = s.warnings
    analysis.visible_count = s.visible_count
    analysis.expected_count = s.expected_count
    analysis.count_low = s.count_low
    analysis.count_high = s.count_high
    analysis.image_confidence = s.image_confidence
    analysis.confluent_present = s.confluent_present
    analysis.confluent_area_pct = s.confluent_area_pct
    analysis.skin_area_px = s.skin_area_px
    analysis.affected_area_px = s.affected_area_px
    analysis.affected_pct = s.affected_pct_of_photographed_skin
    analysis.suggested_score_band = s.suggested_score_band
    analysis.ita_degrees = s.ita_degrees
    analysis.median_delta_a_star = s.median_delta_a_star


def _render_overlay(analysis: Analysis, image: np.ndarray) -> None:
    active = sorted(_active(analysis), key=lambda l: l.label)
    overlay = render_overlay(image, [_to_measurement(l) for l in active], [l.label for l in active])
    analysis.overlay_key = storage.put_image(
        f"{analysis.photo_id}/{analysis.id}/overlay.jpg", overlay, 90
    )

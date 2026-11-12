"""HTTP endpoints. Thin layer: validation and HTTP errors only; logic lives in services/."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Analysis, Photo
from ..schemas import (
    BODY_REGIONS, AddLesionIn, AnalysisOut, CorrectionOut, HealthOut, MergeIn, PhotoOut, PhotoSummary,
)
from ..services import analysis as svc
from ..storage import storage

router = APIRouter(prefix="/api")

DISCLAIMER = (
    "Research prototype. Not a medical device. Counts are estimates and must be reviewed; "
    "do not use for diagnosis or treatment decisions."
)
MAX_UPLOAD_BYTES = 30 * 1024 * 1024


# --------------------------------------------------------------------------- serialisers

def _analysis_out(a: Analysis) -> AnalysisOut:
    out = AnalysisOut.model_validate(a)
    out.confidence_calibrated = svc.confidence_is_calibrated()
    return out


def _photo_out(p: Photo) -> PhotoOut:
    a = p.current_analysis
    return PhotoOut(
        id=p.id, region=p.region, taken_at=p.taken_at, uploaded_at=p.uploaded_at,
        width=p.width, height=p.height, device_model=p.device_model,
        image_url=f"/api/photos/{p.id}/image",
        overlay_url=f"/api/photos/{p.id}/image?variant=overlay&v={a.id}" if a else None,
        analysis=_analysis_out(a) if a else None,
    )


def _get_photo(db: Session, photo_id: str) -> Photo:
    p = db.get(Photo, photo_id)
    if not p:
        raise HTTPException(404, "Photo not found")
    return p


def _get_analysis(db: Session, analysis_id: str) -> Analysis:
    a = db.get(Analysis, analysis_id)
    if not a:
        raise HTTPException(404, "Analysis not found")
    return a


def _edit(fn, *args):
    """Run a review action, mapping domain errors to HTTP errors."""
    try:
        return fn(*args)
    except svc.ReviewLockedError as e:
        raise HTTPException(409, str(e))
    except KeyError:
        raise HTTPException(404, "Lesion not found")
    except ValueError as e:
        raise HTTPException(422, str(e))


# --------------------------------------------------------------------------- endpoints

@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    p = svc.get_pipeline()
    return HealthOut(
        status="ok", detector=p.versions.get("detector", "?"),
        confidence_calibrated=svc.confidence_is_calibrated(), disclaimer=DISCLAIMER,
        regions=BODY_REGIONS,
    )


@router.post("/photos", response_model=PhotoOut, status_code=201)
async def upload_photo(
    file: UploadFile = File(...),
    region: str = Form(...),
    taken_at: Optional[datetime] = Form(None),
    db: Session = Depends(get_db),
) -> PhotoOut:
    if region not in BODY_REGIONS:
        raise HTTPException(422, f"region must be one of {BODY_REGIONS}")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Image larger than 30 MB")
    try:
        photo = svc.create_photo(db, data, file.filename, region, taken_at)
    except ValueError as e:
        db.rollback()
        raise HTTPException(422, str(e))
    return _photo_out(photo)


@router.get("/photos", response_model=list[PhotoSummary])
def list_photos(db: Session = Depends(get_db)) -> list[PhotoSummary]:
    photos = db.scalars(select(Photo).order_by(Photo.taken_at.desc())).all()
    out = []
    for p in photos:
        a = p.current_analysis
        out.append(PhotoSummary(
            id=p.id, region=p.region, taken_at=p.taken_at, uploaded_at=p.uploaded_at,
            thumbnail_url=f"/api/photos/{p.id}/image",
            visible_count=a.visible_count if a else None,
            status=a.status if a else None,
            review_status=a.review_status if a else None,
        ))
    return out


@router.get("/photos/{photo_id}", response_model=PhotoOut)
def get_photo(photo_id: str, db: Session = Depends(get_db)) -> PhotoOut:
    return _photo_out(_get_photo(db, photo_id))


@router.get("/photos/{photo_id}/image")
def get_photo_image(
    photo_id: str,
    variant: str = Query("working", pattern="^(working|overlay)$"),
    db: Session = Depends(get_db),
):
    p = _get_photo(db, photo_id)
    key = p.working_key
    if variant == "overlay":
        a = p.current_analysis
        if not a or not a.overlay_key:
            raise HTTPException(404, "No overlay")
        key = a.overlay_key
    return FileResponse(storage.path(key), media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=60"})


@router.delete("/photos/{photo_id}", status_code=204)
def delete_photo(photo_id: str, db: Session = Depends(get_db)) -> None:
    svc.delete_photo(db, _get_photo(db, photo_id))


@router.post("/photos/{photo_id}/reanalyse", response_model=PhotoOut)
def reanalyse(photo_id: str, db: Session = Depends(get_db)) -> PhotoOut:
    """Run the current pipeline again (e.g. after a model update). Old results are kept."""
    p = _get_photo(db, photo_id)
    svc.analyse_photo(db, p)
    db.commit()
    db.refresh(p)
    return _photo_out(p)


@router.post("/analyses/{analysis_id}/lesions", response_model=AnalysisOut, status_code=201)
def add_lesion(analysis_id: str, body: AddLesionIn, db: Session = Depends(get_db)) -> AnalysisOut:
    a = _get_analysis(db, analysis_id)
    _edit(svc.add_lesion, db, a, body.polygon)
    return _analysis_out(a)


@router.post("/analyses/{analysis_id}/lesions/{lesion_id}/reject", response_model=AnalysisOut)
def reject_lesion(analysis_id: str, lesion_id: str, db: Session = Depends(get_db)) -> AnalysisOut:
    a = _get_analysis(db, analysis_id)
    _edit(svc.set_lesion_status, db, a, lesion_id, "rejected")
    return _analysis_out(a)


@router.post("/analyses/{analysis_id}/lesions/{lesion_id}/restore", response_model=AnalysisOut)
def restore_lesion(analysis_id: str, lesion_id: str, db: Session = Depends(get_db)) -> AnalysisOut:
    a = _get_analysis(db, analysis_id)
    _edit(svc.set_lesion_status, db, a, lesion_id, "active")
    return _analysis_out(a)


@router.post("/analyses/{analysis_id}/merge", response_model=AnalysisOut)
def merge(analysis_id: str, body: MergeIn, db: Session = Depends(get_db)) -> AnalysisOut:
    a = _get_analysis(db, analysis_id)
    _edit(svc.merge_lesions, db, a, body.lesion_ids)
    return _analysis_out(a)


@router.post("/analyses/{analysis_id}/confirm", response_model=AnalysisOut)
def confirm(analysis_id: str, db: Session = Depends(get_db)) -> AnalysisOut:
    a = _get_analysis(db, analysis_id)
    svc.confirm_review(db, a)
    return _analysis_out(a)


@router.post("/analyses/{analysis_id}/reopen", response_model=AnalysisOut)
def reopen(analysis_id: str, db: Session = Depends(get_db)) -> AnalysisOut:
    a = _get_analysis(db, analysis_id)
    svc.reopen_review(db, a)
    return _analysis_out(a)


@router.get("/analyses/{analysis_id}/corrections", response_model=list[CorrectionOut])
def corrections(analysis_id: str, db: Session = Depends(get_db)) -> list[CorrectionOut]:
    return [CorrectionOut.model_validate(c) for c in _get_analysis(db, analysis_id).corrections]


@router.get("/analyses/{analysis_id}/labels.txt", response_class=PlainTextResponse)
def labels(analysis_id: str, db: Session = Depends(get_db)) -> str:
    """Reviewed lesions as YOLO-seg training labels (only after the review is confirmed)."""
    a = _get_analysis(db, analysis_id)
    if a.review_status != "confirmed":
        raise HTTPException(409, "Confirm the review before exporting training labels.")
    return svc.yolo_labels(a)

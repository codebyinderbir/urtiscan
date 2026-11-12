"""ORM models: a subset of the schema in the design doc, enough for Milestone 1.

Raw evidence (photos), machine output (analyses, lesions) and human input (corrections) live in
separate tables so every number can be traced to its source and model version.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    region: Mapped[str] = mapped_column(String(32))
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    original_filename: Mapped[Optional[str]] = mapped_column(String(255))
    original_key: Mapped[str] = mapped_column(String(255))
    working_key: Mapped[str] = mapped_column(String(255))
    width: Mapped[int] = mapped_column(Integer)  # working copy size
    height: Mapped[int] = mapped_column(Integer)
    original_width: Mapped[int] = mapped_column(Integer)
    original_height: Mapped[int] = mapped_column(Integer)
    device_model: Mapped[Optional[str]] = mapped_column(String(128))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    analyses: Mapped[list["Analysis"]] = relationship(
        back_populates="photo", cascade="all, delete-orphan", order_by="Analysis.created_at"
    )

    @property
    def current_analysis(self) -> Optional["Analysis"]:
        current = [a for a in self.analyses if a.is_current]
        return current[-1] if current else None


class Analysis(Base):
    """One run of the CV pipeline on one photo (re-runs create new rows)."""

    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    photo_id: Mapped[str] = mapped_column(ForeignKey("photos.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(32))  # done | insufficient_evidence
    insufficient_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    model_versions: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    quality: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    mm_per_px: Mapped[Optional[float]] = mapped_column(Float)
    marker_corners: Mapped[Optional[list]] = mapped_column(JSON)
    skin_mask_key: Mapped[Optional[str]] = mapped_column(String(255))
    overlay_key: Mapped[Optional[str]] = mapped_column(String(255))

    visible_count: Mapped[int] = mapped_column(Integer, default=0)
    expected_count: Mapped[float] = mapped_column(Float, default=0)
    count_low: Mapped[int] = mapped_column(Integer, default=0)
    count_high: Mapped[int] = mapped_column(Integer, default=0)
    image_confidence: Mapped[float] = mapped_column(Float, default=0)
    confluent_present: Mapped[bool] = mapped_column(Boolean, default=False)
    confluent_area_pct: Mapped[float] = mapped_column(Float, default=0)
    skin_area_px: Mapped[int] = mapped_column(Integer, default=0)
    affected_area_px: Mapped[int] = mapped_column(Integer, default=0)
    affected_pct: Mapped[float] = mapped_column(Float, default=0)
    suggested_score_band: Mapped[list[int]] = mapped_column(JSON, default=list)
    ita_degrees: Mapped[Optional[float]] = mapped_column(Float)
    median_delta_a_star: Mapped[Optional[float]] = mapped_column(Float)

    # Review state. Provenance of the count: ai_estimated -> patient_reviewed / patient_corrected.
    review_status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | confirmed
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    count_provenance: Mapped[str] = mapped_column(String(32), default="ai_estimated")

    photo: Mapped[Photo] = relationship(back_populates="analyses")
    lesions: Mapped[list["Lesion"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan", order_by="Lesion.label"
    )
    corrections: Mapped[list["LesionCorrection"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan", order_by="LesionCorrection.id"
    )


class Lesion(Base):
    __tablename__ = "lesions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    label: Mapped[int] = mapped_column(Integer)  # number shown on the overlay; stable once assigned
    polygon: Mapped[list[list[int]]] = mapped_column(JSON)  # working-image pixels
    confidence: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(16))  # ai | user_added | user_merged
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | rejected | merged
    merged_into: Mapped[Optional[str]] = mapped_column(String(36))

    area_px: Mapped[int] = mapped_column(Integer)
    area_mm2: Mapped[Optional[float]] = mapped_column(Float)
    equiv_diameter_px: Mapped[float] = mapped_column(Float)
    equiv_diameter_mm: Mapped[Optional[float]] = mapped_column(Float)
    max_feret_px: Mapped[float] = mapped_column(Float)
    max_feret_mm: Mapped[Optional[float]] = mapped_column(Float)
    solidity: Mapped[float] = mapped_column(Float)
    centroid_x: Mapped[float] = mapped_column(Float)
    centroid_y: Mapped[float] = mapped_column(Float)
    size_class: Mapped[Optional[str]] = mapped_column(String(8))
    is_confluent: Mapped[bool] = mapped_column(Boolean, default=False)
    delta_a_star: Mapped[Optional[float]] = mapped_column(Float)

    analysis: Mapped[Analysis] = relationship(back_populates="lesions")


class LesionCorrection(Base):
    """Append-only log of every review edit (also future training signal)."""

    __tablename__ = "lesion_corrections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    lesion_id: Mapped[Optional[str]] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(16))  # add | reject | restore | merge | confirm | reopen
    before: Mapped[Optional[dict]] = mapped_column(JSON)
    after: Mapped[Optional[dict]] = mapped_column(JSON)
    actor: Mapped[str] = mapped_column(String(64), default="local-user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    analysis: Mapped[Analysis] = relationship(back_populates="corrections")

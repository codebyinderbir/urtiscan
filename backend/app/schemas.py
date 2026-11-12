"""API request and response models."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

BODY_REGIONS = [
    "torso_front", "torso_back", "arm_left", "arm_right", "leg_left", "leg_right",
    "face", "neck", "hand_left", "hand_right", "foot_left", "foot_right", "other",
]


class LesionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    label: int
    polygon: list[list[int]]
    confidence: float
    source: str
    status: str
    area_px: int
    area_mm2: Optional[float]
    equiv_diameter_px: float
    equiv_diameter_mm: Optional[float]
    max_feret_mm: Optional[float]
    solidity: float
    centroid_x: float
    centroid_y: float
    size_class: Optional[str]
    is_confluent: bool
    delta_a_star: Optional[float]


class CorrectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lesion_id: Optional[str]
    action: str
    actor: str
    created_at: datetime


class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    photo_id: str
    created_at: datetime
    status: str
    insufficient_reasons: list[str]
    warnings: list[str]
    model_versions: dict[str, str]
    quality: dict[str, Any]
    mm_per_px: Optional[float]
    visible_count: int
    expected_count: float
    count_low: int
    count_high: int
    image_confidence: float
    confluent_present: bool
    confluent_area_pct: float
    affected_pct: float
    suggested_score_band: list[int]
    ita_degrees: Optional[float]
    median_delta_a_star: Optional[float]
    review_status: str
    reviewed_at: Optional[datetime]
    count_provenance: str
    confidence_calibrated: bool = False
    lesions: list[LesionOut]


class PhotoSummary(BaseModel):
    id: str
    region: str
    taken_at: datetime
    uploaded_at: datetime
    thumbnail_url: str
    visible_count: Optional[int]
    status: Optional[str]
    review_status: Optional[str]


class PhotoOut(BaseModel):
    id: str
    region: str
    taken_at: datetime
    uploaded_at: datetime
    width: int
    height: int
    device_model: Optional[str]
    image_url: str
    overlay_url: Optional[str]
    analysis: Optional[AnalysisOut]


class AddLesionIn(BaseModel):
    polygon: list[list[float]] = Field(min_length=3, description="Working-image pixel coordinates")


class MergeIn(BaseModel):
    lesion_ids: list[str] = Field(min_length=2)


class HealthOut(BaseModel):
    status: Literal["ok"]
    detector: str
    confidence_calibrated: bool
    disclaimer: str
    regions: list[str]

// Mirrors backend/app/schemas.py

export type Point = [number, number];

export interface Lesion {
  id: string;
  label: number;
  polygon: Point[];
  confidence: number;
  source: "ai" | "user_added" | "user_merged";
  status: "active" | "rejected" | "merged";
  area_px: number;
  area_mm2: number | null;
  equiv_diameter_px: number;
  equiv_diameter_mm: number | null;
  max_feret_mm: number | null;
  solidity: number;
  centroid_x: number;
  centroid_y: number;
  size_class: "small" | "medium" | "large" | null;
  is_confluent: boolean;
  delta_a_star: number | null;
}

export interface Quality {
  verdict?: "ok" | "warn" | "fail";
  blur_score?: number;
  brightness?: number;
  warnings?: string[];
}

export interface Analysis {
  id: string;
  photo_id: string;
  created_at: string;
  status: "done" | "insufficient_evidence";
  insufficient_reasons: string[];
  warnings: string[];
  model_versions: Record<string, string>;
  quality: Quality;
  mm_per_px: number | null;
  visible_count: number;
  expected_count: number;
  count_low: number;
  count_high: number;
  image_confidence: number;
  confluent_present: boolean;
  confluent_area_pct: number;
  affected_pct: number;
  suggested_score_band: number[];
  ita_degrees: number | null;
  median_delta_a_star: number | null;
  review_status: "pending" | "confirmed";
  reviewed_at: string | null;
  count_provenance: "ai_estimated" | "patient_reviewed" | "patient_corrected";
  confidence_calibrated: boolean;
  lesions: Lesion[];
}

export interface Photo {
  id: string;
  region: string;
  taken_at: string;
  uploaded_at: string;
  width: number;
  height: number;
  device_model: string | null;
  image_url: string;
  overlay_url: string | null;
  analysis: Analysis | null;
}

export interface PhotoSummary {
  id: string;
  region: string;
  taken_at: string;
  uploaded_at: string;
  thumbnail_url: string;
  visible_count: number | null;
  status: string | null;
  review_status: string | null;
}

export interface Health {
  status: "ok";
  detector: string;
  confidence_calibrated: boolean;
  disclaimer: string;
  regions: string[];
}

export const REGION_LABELS: Record<string, string> = {
  torso_front: "Front of torso",
  torso_back: "Back of torso",
  arm_left: "Left arm",
  arm_right: "Right arm",
  leg_left: "Left leg",
  leg_right: "Right leg",
  face: "Face",
  neck: "Neck",
  hand_left: "Left hand",
  hand_right: "Right hand",
  foot_left: "Left foot",
  foot_right: "Right foot",
  other: "Other",
};

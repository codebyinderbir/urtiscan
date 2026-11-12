"""Stage 6: turn lesion measurements into a count with uncertainty, or abstain.

Counting model
--------------
Each lesion's confidence p is treated as the probability that it is a real wheal. The expected
number of real wheals is sum(p) and its variance sum(p(1-p)) (Poisson-binomial), which gives an
approximate 95% range. This is only meaningful once confidences are calibrated against expert
labels; for the heuristic detector the UI labels the range as approximate.

Once the user has reviewed and confirmed the lesions, every remaining lesion counts as p = 1 and
the range collapses to the confirmed count.

The photo-level wheal-score band is NOT the daily UAS7 wheal score: a photo shows one moment
and one body region. The daily score is always confirmed by the patient (Phase 2).
"""
from __future__ import annotations

import math
from typing import Optional, Sequence

import numpy as np

from .measure import union_mask
from .types import AnalysisContext, AnalysisSummary, LesionMeasurement, QualityReport

MIN_IMAGE_CONFIDENCE = 0.35
DARK_SKIN_ITA = 10.0  # ITA° below this = "brown"/"dark" categories (Chardon et al. 1991)
LARGE_CONFLUENT_PCT = 25.0


def wheal_score(count: int) -> int:
    """UAS7 wheal component mapping: 0 none, 1-19 mild, 20-50 moderate, >50 intense."""
    if count <= 0:
        return 0
    if count < 20:
        return 1
    if count <= 50:
        return 2
    return 3


def summarize(
    lesions: Sequence[LesionMeasurement],
    skin_mask: np.ndarray,
    lab: Optional[np.ndarray],
    quality: Optional[QualityReport],
    confidence_threshold: float,
    confirmed: bool = False,
    abstain_reasons: Sequence[str] = (),
    warnings: Sequence[str] = (),
) -> AnalysisSummary:
    warnings = list(warnings)
    reasons = list(abstain_reasons)

    probs = [1.0 if confirmed else l.confidence for l in lesions]
    counted = [l for l, p in zip(lesions, probs) if p >= confidence_threshold]
    visible = len(counted)
    expected = float(sum(probs))
    sd = math.sqrt(sum(p * (1 - p) for p in probs))
    low = max(0, min(visible, math.floor(expected - 1.96 * sd)))
    high = max(visible, math.ceil(expected + 1.96 * sd))

    skin_area = int(np.count_nonzero(skin_mask))
    union = union_mask([np.asarray(l.polygon) for l in counted], skin_mask.shape)
    affected = int(np.count_nonzero((union > 0) & (skin_mask > 0)))
    affected_pct = 100.0 * affected / skin_area if skin_area else 0.0
    confl_area = sum(l.area_px for l in counted if l.is_confluent)
    confl_pct = 100.0 * confl_area / affected if affected else 0.0
    confluent_present = any(l.is_confluent for l in counted)

    # Image-level confidence: how much to trust this photo's count as a whole.
    q_factor = {"ok": 1.0, "warn": 0.8, "fail": 0.0}[quality.verdict] if quality else 0.8
    if confirmed:
        image_conf = 1.0 if q_factor > 0 else 0.0
    elif counted:
        image_conf = float(np.mean([l.confidence for l in counted])) * q_factor
    else:
        # Nothing found: the detector may simply have missed faint wheals.
        image_conf = 0.6 * q_factor
    if confluent_present and not confirmed:
        image_conf *= 0.85
        warnings.append(
            "Merged (confluent) wheals detected: the individual count is less reliable."
        )

    # Skin-tone context for interpreting redness.
    ita = med_da = None
    if lab is not None and skin_area:
        normal = (skin_mask > 0) & (union == 0)
        if normal.sum() > 100:
            L = float(np.median(lab[..., 0][normal]))
            b = float(np.median(lab[..., 2][normal]))
            ita = round(math.degrees(math.atan2(L - 50.0, b)), 1)
            if ita < DARK_SKIN_ITA:
                warnings.append(
                    "Redness-based detection is less reliable on darker skin tones; please check "
                    "carefully for missed wheals."
                )
    das = [l.delta_a_star for l in counted if l.delta_a_star is not None]
    if das:
        med_da = round(float(np.median(das)), 2)

    band = sorted({wheal_score(n) for n in range(low, high + 1)}) if high - low < 200 else [wheal_score(low), 3]
    if confluent_present and confl_pct >= LARGE_CONFLUENT_PCT:
        band = sorted(set(band) | {3})

    if not reasons and image_conf < MIN_IMAGE_CONFIDENCE:
        reasons.append("Detection confidence is too low for a reliable count.")
    status = "insufficient_evidence" if reasons else "done"

    return AnalysisSummary(
        status=status,
        visible_count=visible,
        expected_count=round(expected, 1),
        count_low=low,
        count_high=high,
        image_confidence=round(image_conf, 3),
        confluent_present=confluent_present,
        confluent_area_pct=round(confl_pct, 1),
        skin_area_px=skin_area,
        affected_area_px=affected,
        affected_pct_of_photographed_skin=round(affected_pct, 2),
        suggested_score_band=band,
        insufficient_reasons=reasons,
        warnings=list(dict.fromkeys(warnings)),  # de-duplicate, keep order
        ita_degrees=ita,
        median_delta_a_star=med_da,
    )


class SummaryStage:
    name = "summary"
    version = "0.1.0"

    def run(self, ctx: AnalysisContext) -> None:
        assert ctx.skin_mask is not None
        ctx.summary = summarize(
            ctx.lesions,
            ctx.skin_mask,
            ctx.lab,
            ctx.quality,
            ctx.confidence_threshold,
            abstain_reasons=ctx.abstain_reasons,
            warnings=ctx.warnings,
        )

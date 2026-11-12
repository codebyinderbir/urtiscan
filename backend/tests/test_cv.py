"""Pipeline tests on synthetic photos with known ground truth.

These check that the plumbing is correct (counting, splitting, units, abstaining). They say
nothing about accuracy on real urticaria photos, which needs expert-labelled data.
"""
import math

import numpy as np
import pytest

from app.cv.detectors.yolo import mask_nms, tile_boxes
from app.cv.pipeline import default_pipeline
from app.cv.summary import wheal_score
from app.cv.types import LesionCandidate
from tests.synthetic import make_photo


@pytest.fixture(scope="module")
def pipeline():
    return default_pipeline()


@pytest.mark.parametrize("tone", ["light", "medium", "dark"])
@pytest.mark.parametrize("seed", [0, 1])
def test_counts_isolated_and_touching_wheals(pipeline, tone, seed):
    photo = make_photo(seed=seed, tone=tone, n_isolated=12, n_pairs=2)
    s = pipeline.run(photo.image_bgr).summary
    assert s.status == "done"
    assert abs(s.visible_count - len(photo.wheals)) <= 1
    assert s.count_low <= s.visible_count <= s.count_high


def test_scale_marker_gives_millimetres(pipeline):
    photo = make_photo(seed=2, n_pairs=0)
    ctx = pipeline.run(photo.image_bgr)
    assert ctx.calibration.marker_detected
    assert ctx.calibration.mm_per_px == pytest.approx(1 / photo.px_per_mm, rel=0.03)
    errors = []
    for wh in photo.wheals:
        true_d = 2 * math.sqrt(wh.rx * wh.ry) / photo.px_per_mm
        nearest = min(ctx.lesions, key=lambda l: (l.centroid[0] - wh.cx) ** 2 + (l.centroid[1] - wh.cy) ** 2)
        errors.append(abs(nearest.equiv_diameter_mm - true_d))
    assert max(errors) < 1.0  # mm
    assert all(l.size_class in {"small", "medium", "large"} for l in ctx.lesions)


def test_no_marker_means_no_millimetres(pipeline):
    ctx = pipeline.run(make_photo(seed=3, marker=False).image_bgr)
    assert ctx.calibration.mm_per_px is None
    assert all(l.area_mm2 is None and l.size_class is None for l in ctx.lesions)
    assert any("scale marker" in w for w in ctx.summary.warnings)


def test_clear_skin_finds_nothing(pipeline):
    s = pipeline.run(make_photo(seed=4, n_isolated=0, n_pairs=0).image_bgr).summary
    assert s.visible_count == 0
    assert s.suggested_score_band == [0]


def test_blurry_photo_abstains(pipeline):
    ctx = pipeline.run(make_photo(seed=5, blur=6).image_bgr)
    assert ctx.quality.verdict == "fail"
    assert ctx.summary.status == "insufficient_evidence"
    assert ctx.lesions == []  # detection skipped, nothing invented


def test_redness_is_positive_inside_wheals(pipeline):
    ctx = pipeline.run(make_photo(seed=6).image_bgr)
    das = [l.delta_a_star for l in ctx.lesions if l.delta_a_star is not None]
    assert das and min(das) > 0


@pytest.mark.parametrize("count,score", [(0, 0), (1, 1), (19, 1), (20, 2), (50, 2), (51, 3)])
def test_wheal_score_mapping(count, score):
    assert wheal_score(count) == score


def test_tiles_cover_image():
    boxes = tile_boxes(2500, 1300, 1024, 0.2)
    covered = np.zeros((1300, 2500), bool)
    for x0, y0, x1, y1 in boxes:
        covered[y0:y1, x0:x1] = True
    assert covered.all()


def test_mask_nms_removes_tile_duplicates():
    sq = np.array([[10, 10], [60, 10], [60, 60], [10, 60]], np.int32)
    a = LesionCandidate(sq, 0.9)
    b = LesionCandidate(sq + 2, 0.6)  # same lesion seen from a neighbouring tile
    c = LesionCandidate(sq + 200, 0.7)
    kept = mask_nms([a, b, c], (400, 400), 0.5)
    assert [k.score for k in kept] == [0.9, 0.7]

"""End-to-end API test: upload -> detect -> review -> confirm -> export."""
import cv2
import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.synthetic import make_photo


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _upload(client, **kw):
    photo = make_photo(**kw)
    ok, buf = cv2.imencode(".jpg", photo.image_bgr, [cv2.IMWRITE_JPEG_QUALITY, 92])
    r = client.post(
        "/api/photos",
        files={"file": ("forearm.jpg", buf.tobytes(), "image/jpeg")},
        data={"region": "arm_left"},
    )
    assert r.status_code == 201, r.text
    return photo, r.json()


def test_health(client):
    r = client.get("/api/health").json()
    assert r["status"] == "ok" and r["confidence_calibrated"] is False


def test_review_workflow(client):
    photo, body = _upload(client, seed=1, n_isolated=8, n_pairs=1)
    a = body["analysis"]
    assert a["status"] == "done"
    assert a["count_provenance"] == "ai_estimated"
    n = a["visible_count"]
    assert abs(n - len(photo.wheals)) <= 1
    assert client.get(body["image_url"]).status_code == 200
    assert client.get(body["overlay_url"]).status_code == 200

    aid = a["id"]
    first, second = a["lesions"][0], a["lesions"][1]

    # Reject a false positive.
    a = client.post(f"/api/analyses/{aid}/lesions/{first['id']}/reject").json()
    assert a["visible_count"] == n - 1

    # Draw a missed wheal.
    poly = [[100, 100], [140, 100], [140, 140], [100, 140]]
    r = client.post(f"/api/analyses/{aid}/lesions", json={"polygon": poly})
    assert r.status_code == 201
    a = r.json()
    assert a["visible_count"] == n
    added = [l for l in a["lesions"] if l["source"] == "user_added"][0]
    assert added["confidence"] == 1.0 and added["area_px"] > 1000

    # Merging lesions that don't touch is refused.
    r = client.post(f"/api/analyses/{aid}/merge", json={"lesion_ids": [second["id"], added["id"]]})
    assert r.status_code == 422

    # Confirm: range collapses, provenance changes, edits are locked.
    a = client.post(f"/api/analyses/{aid}/confirm").json()
    assert a["review_status"] == "confirmed"
    assert a["count_provenance"] == "patient_corrected"
    assert a["count_low"] == a["count_high"] == a["visible_count"] == n
    assert client.post(f"/api/analyses/{aid}/lesions/{second['id']}/reject").status_code == 409

    labels = client.get(f"/api/analyses/{aid}/labels.txt").text.strip().splitlines()
    assert len(labels) == n and labels[0].startswith("0 ")

    actions = [c["action"] for c in client.get(f"/api/analyses/{aid}/corrections").json()]
    assert actions == ["reject", "add", "confirm"]


def test_merge_touching(client):
    _, body = _upload(client, seed=2, n_isolated=0, n_pairs=1)
    a = body["analysis"]
    active = [l for l in a["lesions"] if l["status"] == "active"]
    assert len(active) == 2
    r = client.post(f"/api/analyses/{a['id']}/merge", json={"lesion_ids": [l["id"] for l in active]})
    assert r.status_code == 200, r.text
    assert r.json()["visible_count"] == 1


def test_bad_upload_rejected(client):
    r = client.post("/api/photos", files={"file": ("x.jpg", b"not an image", "image/jpeg")},
                    data={"region": "arm_left"})
    assert r.status_code == 422


def test_delete_photo(client):
    _, body = _upload(client, seed=3, n_isolated=3, n_pairs=0)
    assert client.delete(f"/api/photos/{body['id']}").status_code == 204
    assert client.get(f"/api/photos/{body['id']}").status_code == 404

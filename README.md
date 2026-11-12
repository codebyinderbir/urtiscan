# UrtiScan — AI-assisted urticaria assessment (research prototype)

> **Research prototype. Not a medical device. Not for diagnosis or treatment decisions.**
> All counts are estimates that must be reviewed by a person.

UrtiScan analyses a photograph of skin, outlines possible wheals (hives), counts them with an
uncertainty range, and lets the user correct every result. This repository is **Milestone 1**
of the roadmap in the design doc: *upload a photo → wheals detected and outlined → review and
correct → estimated count with a confidence assessment.*

## What Milestone 1 does

| Step | What happens | Where |
| --- | --- | --- |
| Upload | Photo + body region + time; EXIF location stripped, orientation fixed | `backend/app/storage.py` |
| Quality gate | Blur, exposure, glare, resolution → `ok` / `warn` / `fail` | `backend/app/cv/quality.py` |
| Calibration | Detects a printed ArUco marker → mm per pixel (otherwise pixels only) | `backend/app/cv/calibration.py` |
| Skin mask | Separates skin from background (heuristic for now) | `backend/app/cv/skin.py` |
| Wheal detection | Pluggable detector: heuristic baseline, or YOLO-seg once trained | `backend/app/cv/detectors/` |
| Measurement | Area, diameters, solidity, size class, confluence, Δa* redness | `backend/app/cv/measure.py` |
| Summary | Visible count, 95% range, image confidence, or *insufficient evidence* | `backend/app/cv/summary.py` |
| Review | Reject, restore, draw, merge lesions; every edit is logged | `frontend/src/components/` |

## Important: the default detector is a heuristic baseline

There is no trained urticaria model yet (see *Dataset and validation plan* in the design doc).
Until one exists, the app uses `HeuristicWhealDetector`, which finds patches that are redder than
the surrounding skin in CIELAB colour space and splits touching patches with a watershed.

* It works best on lighter skin with clear erythema and **will under-detect on darker skin**,
  where wheals are often skin-coloured or violaceous. The UI says so.
* Its confidence scores are capped and **not calibrated**.
* It exists so the whole loop (upload → detect → review → corrections saved) can be built and
  tested now. Review corrections are stored and can be exported as YOLO-seg training labels
  (`GET /api/analyses/{id}/labels.txt`), which is how the real model gets trained.

When a YOLO-seg model is trained, set `URTISCAN_DETECTOR=yolo` and
`URTISCAN_YOLO_WEIGHTS=/path/to/best.pt`. Nothing else changes.

## Running it on your Mac

You need **Python 3.10+** and **Node 18+**.

```bash
# 1. Backend (terminal 1)
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 2. Frontend (terminal 2)
cd frontend
npm install
npm run dev
# open http://localhost:5173
```

No photos handy? Generate a synthetic test image with a scale marker:

```bash
cd backend && source .venv/bin/activate
python ../tools/make_sample_image.py ../data/sample_forearm.jpg
```

Print a scale marker for real photos (print at 100% scale; the black square must measure 20 mm):

```bash
python ../tools/make_marker.py ../data/urtiscan_marker.png
```

Run the tests:

```bash
cd backend && source .venv/bin/activate && pytest -q
```

## Project layout

```
backend/
  app/
    main.py            FastAPI app
    config.py          Settings (env vars prefixed URTISCAN_)
    db.py, models.py   SQLAlchemy models (SQLite now, Postgres-ready)
    schemas.py         API request/response models
    storage.py         Image storage (local folder now, S3-compatible later)
    api/routes.py      HTTP endpoints
    services/          Runs the pipeline, applies corrections
    cv/                Computer vision pipeline (no web or DB code in here)
      types.py         Shared dataclasses
      pipeline.py      Composes stages; records model versions
      quality.py  calibration.py  skin.py  measure.py  summary.py  overlay.py
      detectors/       base.py (interface), heuristic.py, yolo.py
  tests/
frontend/              React + TypeScript + Vite review UI
tools/                 Sample image + printable marker generators
docs/                  Architecture notes
```

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `URTISCAN_DATA_DIR` | `../data` | Where photos and the SQLite DB live |
| `URTISCAN_DATABASE_URL` | `sqlite:///<data>/urtiscan.db` | Any SQLAlchemy URL; Postgres for pilots |
| `URTISCAN_DETECTOR` | `heuristic` | `heuristic` or `yolo` |
| `URTISCAN_YOLO_WEIGHTS` | — | Path to trained YOLO-seg weights |
| `URTISCAN_MARKER_MM` | `20` | Printed ArUco marker side length in mm |
| `URTISCAN_CONFIDENCE_THRESHOLD` | `0.5` | Minimum lesion confidence counted as "visible" |

## Privacy

Photos stay on this machine in `data/` (git-ignored). Nothing is sent to external services.
Before any use with real patients: research ethics approval, consent, encryption at rest,
authentication and a privacy impact assessment (see the design doc).

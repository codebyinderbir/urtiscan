# Technical decisions (Milestone 1)

Short records of choices that shape the code. The full design lives in the project design doc
("UrtiScan: AI-Assisted Urticaria Assessment — Technical Design & Roadmap").

## 1. A heuristic detector first, behind a swappable interface
No expert-labelled urticaria dataset exists yet, so a trained model is not possible today.
`HeuristicWhealDetector` (CIELAB redness vs local skin background, hysteresis, half-maximum
edges, power-diagram splitting) lets the full upload → review → correction loop work now.
Every detector implements `WhealDetector.detect()`, so `YoloSegWhealDetector` drops in once
trained. Corrections are exported as YOLO-seg labels to bootstrap that training.

## 2. Confidence is shown, capped and labelled "not calibrated"
Heuristic scores are capped at 0.85 and the UI says they are not validated. The count range is a
Poisson-binomial interval over per-lesion confidences; it becomes meaningful only after
calibration against expert labels (temperature scaling, Phase 5).

## 3. Abstain instead of guessing
A failed quality gate skips detection entirely and reports *insufficient evidence*. Without a
scale marker, sizes stay in pixels; millimetres are never estimated.

## 4. Visible count ≠ daily wheal score
The photo shows one region at one moment. The UI shows only a *photo-level hint*; the UAS7
daily wheal score will be confirmed by the patient (Phase 2).

## 5. Provenance on the count
`ai_estimated` → `patient_reviewed` (confirmed, no edits) or `patient_corrected` (confirmed
after edits). Every edit is an append-only row in `lesion_corrections`.

## 6. SQLite + local files now, Postgres + S3 later
Zero setup for development. Only portable column types are used; storage is behind a small
class. Switching is configuration, plus Alembic migrations before anyone else uses the schema.

## 7. Synchronous analysis for the MVP
Analysis takes about 0.3 s on a 2048-px image, so the upload request waits for it. The
service layer has no HTTP code, so moving it into a queue worker later is a wrapper, not a
rewrite.

## 8. Synthetic tests check plumbing, not accuracy
`tests/synthetic.py` draws wheals with known positions and sizes, including touching pairs and
three skin tones. Passing tests mean counting, splitting and units work. They say nothing about
real-photo accuracy, which needs the validation plan in the design doc.

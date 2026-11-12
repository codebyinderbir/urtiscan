import type { Analysis } from "../types";
import { confidenceLabel } from "./lesionStyle";

const SCORE_NAMES = ["none", "mild", "moderate", "intense"];
const PROVENANCE = {
  ai_estimated: { text: "AI estimate · not yet reviewed", cls: "ai" },
  patient_reviewed: { text: "Reviewed by you · no changes", cls: "ok" },
  patient_corrected: { text: "Corrected by you", cls: "ok" },
} as const;

export default function SummaryPanel({ a }: { a: Analysis }) {
  const conf = confidenceLabel(a.image_confidence);
  const prov = PROVENANCE[a.count_provenance];
  const insufficient = a.status === "insufficient_evidence";
  const band = a.suggested_score_band;
  const bandText = band.map((s) => `${s} (${SCORE_NAMES[s]})`).join(" or ");
  const confirmed = a.review_status === "confirmed";

  return (
    <section className="summary">
      {insufficient && (
        <div className="banner warn" role="alert">
          <strong>Insufficient evidence for a reliable count.</strong>
          <ul>
            {a.insufficient_reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
          {a.quality.verdict === "fail" && <span>Please retake the photo using the tips on the upload screen.</span>}
        </div>
      )}

      <div className="stat-grid">
        <div className="stat main">
          <span className="stat-label">Visible wheals in this photo</span>
          <span className="stat-value">{insufficient && !confirmed ? "–" : a.visible_count}</span>
          <span className={`chip ${prov.cls}`}>{prov.text}</span>
          {!confirmed && !insufficient && (
            <span className="muted small">
              Likely range {a.count_low}–{a.count_high}
              {!a.confidence_calibrated && " (approximate: model confidence not yet calibrated)"}
            </span>
          )}
        </div>

        <div className="stat">
          <span className="stat-label">Analysis confidence</span>
          <span className={`stat-value tone-${conf.tone}`}>{conf.text}</span>
          <div className="meter" aria-hidden>
            <div className={`meter-fill tone-${conf.tone}`} style={{ width: `${a.image_confidence * 100}%` }} />
          </div>
          <span className="muted small">
            {Math.round(a.image_confidence * 100)} / 100
            {!a.confidence_calibrated && !confirmed && " · heuristic score, not validated"}
          </span>
        </div>

        <div className="stat">
          <span className="stat-label">Photographed skin affected</span>
          <span className="stat-value">{a.affected_pct.toFixed(1)}%</span>
          <span className="muted small">Of skin in this photo only, not of the whole body</span>
        </div>

        <div className="stat">
          <span className="stat-label">Scale</span>
          <span className="stat-value small-value">
            {a.mm_per_px ? `${(1 / a.mm_per_px).toFixed(1)} px/mm` : "No marker"}
          </span>
          <span className="muted small">
            {a.mm_per_px ? "Sizes in millimetres" : "Sizes in pixels; add the printed marker"}
          </span>
        </div>
      </div>

      {!insufficient && (
        <p className="score-note">
          <strong>Photo-level hint:</strong> this photo alone corresponds to a wheal score of {bandText}.{" "}
          <span className="muted">
            The daily UAS7 wheal score covers all wheals over 24 hours and is confirmed by you (coming in
            Phase 2).
          </span>
        </p>
      )}

      {a.confluent_present && (
        <p className="muted small">
          Confluent (merged) areas make up {a.confluent_area_pct.toFixed(0)}% of the affected area. Individual
          wheals inside them cannot be counted reliably.
        </p>
      )}

      {a.warnings.length > 0 && (
        <ul className="warnings">
          {a.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

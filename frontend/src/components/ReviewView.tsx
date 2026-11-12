import { useEffect, useState } from "react";
import { api } from "../api";
import { REGION_LABELS, type Analysis, type Health, type Photo, type Point } from "../types";
import LesionCanvas, { type Mode } from "./LesionCanvas";
import LesionTable from "./LesionTable";
import SummaryPanel from "./SummaryPanel";
import { LEGEND } from "./lesionStyle";

interface Props {
  photo: Photo;
  health: Health | null;
  onChanged: () => void;
  onDeleted: () => void;
  onReplaced: (p: Photo) => void;
}

const THRESHOLD = 0.5; // matches URTISCAN_CONFIDENCE_THRESHOLD default
const fmt = new Intl.DateTimeFormat(undefined, { dateStyle: "full", timeStyle: "short" });

export default function ReviewView({ photo, health, onChanged, onDeleted, onReplaced }: Props) {
  const [analysis, setAnalysis] = useState<Analysis | null>(photo.analysis);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [mode, setMode] = useState<Mode>("select");
  const [layout, setLayout] = useState<"split" | "single">("split");
  const [zoom, setZoom] = useState(1);
  const [showRejected, setShowRejected] = useState(false);
  const [showLabels, setShowLabels] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const editable = analysis?.review_status === "pending";

  const run = async (fn: () => Promise<Analysis>) => {
    setBusy(true);
    setError(null);
    try {
      setAnalysis(await fn());
      setSelected(new Set());
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const select = (id: string, additive: boolean) =>
    setSelected((prev) => {
      const next = new Set(additive ? prev : []);
      if (prev.has(id) && additive) next.delete(id);
      else next.add(id);
      return next;
    });

  // Delete / Backspace rejects the selection in select mode.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!analysis || !editable || mode !== "select" || selected.size === 0) return;
      if ((e.target as HTMLElement).tagName === "INPUT") return;
      if (e.key === "Delete" || e.key === "Backspace") {
        e.preventDefault();
        const ids = [...selected];
        run(async () => {
          let a = analysis;
          for (const id of ids) a = await api.reject(a.id, id);
          return a;
        });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (!analysis) return <p>No analysis for this photo.</p>;
  const aid = analysis.id;
  const selectedActive = analysis.lesions.filter((l) => selected.has(l.id) && l.status === "active");
  const selectedRejected = analysis.lesions.filter((l) => selected.has(l.id) && l.status === "rejected");

  const addPolygon = (pts: Point[]) => run(() => api.addLesion(aid, pts));
  const rejectSelected = () =>
    run(async () => {
      let a = analysis;
      for (const l of selectedActive) a = await api.reject(aid, l.id);
      return a;
    });
  const restoreSelected = () =>
    run(async () => {
      let a = analysis;
      for (const l of selectedRejected) a = await api.restore(aid, l.id);
      return a;
    });

  const remove = async () => {
    if (!window.confirm("Delete this photo and its analysis permanently?")) return;
    await api.deletePhoto(photo.id);
    onDeleted();
  };

  const canvas = (
    <LesionCanvas
      imageUrl={photo.image_url}
      width={photo.width}
      height={photo.height}
      lesions={analysis.lesions}
      selected={selected}
      mode={editable ? mode : "select"}
      showRejected={showRejected}
      showLabels={showLabels}
      threshold={THRESHOLD}
      zoom={zoom}
      onSelect={select}
      onClearSelection={() => setSelected(new Set())}
      onPolygon={addPolygon}
    />
  );

  return (
    <div className="review">
      <div className="review-head">
        <div>
          <h1>{REGION_LABELS[photo.region] ?? photo.region}</h1>
          <p className="muted small">
            {fmt.format(new Date(photo.taken_at))}
            {photo.device_model && ` · ${photo.device_model}`} · detector {health?.detector ?? "…"}
          </p>
        </div>
        <div className="head-actions">
          <button className="btn ghost" onClick={remove}>
            Delete photo
          </button>
          <button
            className="btn ghost"
            disabled={busy}
            title="Run the current model again; the old result is kept in the database"
            onClick={async () => {
              setBusy(true);
              try {
                onReplaced(await api.reanalyse(photo.id));
                onChanged();
              } finally {
                setBusy(false);
              }
            }}
          >
            Re-analyse
          </button>
        </div>
      </div>

      <SummaryPanel a={analysis} />

      <div className="toolbar" role="toolbar" aria-label="Review tools">
        <div className="seg">
          <button className={mode === "select" ? "on" : ""} onClick={() => setMode("select")} disabled={!editable}>
            Select
          </button>
          <button className={mode === "draw" ? "on" : ""} onClick={() => setMode("draw")} disabled={!editable}>
            Draw missed wheal
          </button>
        </div>
        <button className="btn" disabled={!editable || busy || !selectedActive.length} onClick={rejectSelected}>
          Not a wheal{selectedActive.length > 1 ? ` (${selectedActive.length})` : ""}
        </button>
        <button
          className="btn"
          disabled={!editable || busy || selectedActive.length < 2}
          onClick={() => run(() => api.merge(aid, selectedActive.map((l) => l.id)))}
          title="Shift-click two or more touching outlines that are really one wheal"
        >
          Merge
        </button>
        {showRejected && (
          <button className="btn" disabled={!editable || busy || !selectedRejected.length} onClick={restoreSelected}>
            Restore
          </button>
        )}
        <span className="spacer" />
        <label className="check">
          <input type="checkbox" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} /> Numbers
        </label>
        <label className="check">
          <input type="checkbox" checked={showRejected} onChange={(e) => setShowRejected(e.target.checked)} /> Show
          rejected
        </label>
        <div className="seg">
          <button className={layout === "split" ? "on" : ""} onClick={() => setLayout("split")}>
            Side by side
          </button>
          <button className={layout === "single" ? "on" : ""} onClick={() => setLayout("single")}>
            Annotated
          </button>
        </div>
        <div className="seg" aria-label="Zoom">
          {[1, 2, 3].map((z) => (
            <button key={z} className={zoom === z ? "on" : ""} onClick={() => setZoom(z)}>
              {z}×
            </button>
          ))}
        </div>
      </div>

      {mode === "draw" && editable && (
        <p className="hint">
          Click around the edge of the missed wheal. Double-click or press Enter to finish · Backspace undoes a point
          · Esc cancels.
        </p>
      )}
      {mode === "select" && editable && (
        <p className="hint">
          Click an outline to select it (Shift-click for several). Dashed outlines are low-confidence detections.
        </p>
      )}
      {error && <div className="banner error">{error}</div>}

      <div className={`images ${layout}`}>
        {layout === "split" && (
          <figure>
            <figcaption>Original</figcaption>
            <div className="canvas-scroll">
              <div className="canvas" style={{ width: `${zoom * 100}%`, aspectRatio: `${photo.width} / ${photo.height}` }}>
                <img src={photo.image_url} alt="Original photo" />
              </div>
            </div>
          </figure>
        )}
        <figure>
          <figcaption>AI-annotated {editable ? "· editable" : "· review confirmed"}</figcaption>
          {canvas}
        </figure>
      </div>

      <ul className="legend">
        {LEGEND.map((l) => (
          <li key={l.key}>
            <span className="swatch" style={{ background: l.color }} />
            {l.label}
          </li>
        ))}
      </ul>

      <section className="card">
        <div className="section-head">
          <h2>Lesions</h2>
          {editable ? (
            <button className="btn primary" disabled={busy} onClick={() => run(() => api.confirm(aid))}>
              Confirm review ({analysis.visible_count} wheals)
            </button>
          ) : (
            <div className="head-actions">
              <a className="btn ghost" href={api.labelsUrl(aid)} download={`${photo.id}.txt`}>
                Export training labels
              </a>
              <button className="btn" disabled={busy} onClick={() => run(() => api.reopen(aid))}>
                Reopen review
              </button>
            </div>
          )}
        </div>
        <LesionTable
          lesions={analysis.lesions}
          selected={selected}
          showRejected={showRejected}
          editable={editable}
          onSelect={select}
          onReject={(id) => run(() => api.reject(aid, id))}
          onRestore={(id) => run(() => api.restore(aid, id))}
        />
        <p className="muted small">
          Δa* is redness compared with nearby unaffected skin (CIELAB). It is supplementary: wheals can be red,
          skin-coloured or violaceous depending on skin tone.
          {analysis.ita_degrees != null && ` Skin-tone angle (ITA°) of unaffected skin: ${analysis.ita_degrees}°.`}
        </p>
      </section>

      <details className="card provenance">
        <summary>Model versions and image quality</summary>
        <dl>
          {Object.entries(analysis.model_versions).map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
          <div>
            <dt>quality</dt>
            <dd>
              {analysis.quality.verdict} · sharpness {analysis.quality.blur_score} · brightness L*{" "}
              {analysis.quality.brightness}
            </dd>
          </div>
        </dl>
      </details>
    </div>
  );
}

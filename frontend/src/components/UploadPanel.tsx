import { useMemo, useState } from "react";
import { api } from "../api";
import { REGION_LABELS, type Photo } from "../types";

interface Props {
  regions: string[];
  onUploaded: (p: Photo) => void;
}

function nowLocal(): string {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

const TIPS = [
  "Use the same phone and roughly the same distance (about 30–40 cm) each time.",
  "Even, diffuse daylight. No flash, no harsh shadows.",
  "Hold the camera straight on to the skin, not at an angle.",
  "Place the printed 20 mm scale marker flat on the skin, inside the photo.",
  "Fill most of the frame with the body region; keep clothing and background out.",
  "Take extra photos during a flare. Wheals come and go, so one photo is one moment.",
];

export default function UploadPanel({ regions, onUploaded }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [region, setRegion] = useState("");
  const [takenAt, setTakenAt] = useState(nowLocal());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const preview = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  const regionList = regions.length ? regions : Object.keys(REGION_LABELS);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || !region) return;
    setBusy(true);
    setError(null);
    try {
      onUploaded(await api.upload(file, region, takenAt));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="upload-grid">
      <form className="card" onSubmit={submit}>
        <h1>Analyse a photo</h1>
        <p className="muted">
          Upload one photo of one body region. The app outlines possible wheals for you to check
          and correct.
        </p>

        <label className="dropzone">
          {preview ? (
            <img src={preview} alt="Selected photo preview" />
          ) : (
            <span>
              <strong>Take or choose a photo</strong>
              <br />
              <span className="muted small">JPEG or PNG, up to 30 MB</span>
            </span>
          )}
          <input
            type="file"
            accept="image/jpeg,image/png"
            capture="environment"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>

        <div className="field-row">
          <label className="field">
            <span>Body region</span>
            <select value={region} onChange={(e) => setRegion(e.target.value)} required>
              <option value="" disabled>
                Choose…
              </option>
              {regionList.map((r) => (
                <option key={r} value={r}>
                  {REGION_LABELS[r] ?? r}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Taken at</span>
            <input type="datetime-local" value={takenAt} onChange={(e) => setTakenAt(e.target.value)} />
          </label>
        </div>

        {error && <div className="banner error">{error}</div>}
        <button className="btn primary" disabled={!file || !region || busy}>
          {busy ? "Analysing…" : "Analyse photo"}
        </button>
        <p className="muted small">
          Photos stay on this computer. Location and other metadata are removed on upload.
        </p>
      </form>

      <section className="card tips">
        <h2>Taking a consistent photo</h2>
        <ol>
          {TIPS.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ol>
        <p className="muted small">
          No marker yet? Run <code>python tools/make_marker.py data/marker.png</code> and print it
          at 100% scale. Without it, sizes are shown in pixels only.
        </p>
      </section>
    </div>
  );
}

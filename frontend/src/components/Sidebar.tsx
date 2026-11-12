import { REGION_LABELS, type PhotoSummary } from "../types";

interface Props {
  photos: PhotoSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}

const fmt = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

export default function Sidebar({ photos, selectedId, onSelect, onNew }: Props) {
  return (
    <aside className="sidebar">
      <button className="btn primary block" onClick={onNew}>
        + New photo
      </button>
      <h2 className="side-title">Photo history</h2>
      {photos.length === 0 && <p className="muted small">No photos yet.</p>}
      <ul className="history">
        {photos.map((p) => (
          <li key={p.id}>
            <button
              className={`history-item ${p.id === selectedId ? "active" : ""}`}
              onClick={() => onSelect(p.id)}
            >
              <img src={p.thumbnail_url} alt="" loading="lazy" />
              <span className="history-text">
                <span className="history-region">{REGION_LABELS[p.region] ?? p.region}</span>
                <span className="muted small">{fmt.format(new Date(p.taken_at))}</span>
                <span className="history-meta">
                  {p.status === "insufficient_evidence" ? (
                    <span className="chip warn">insufficient evidence</span>
                  ) : (
                    <span className="chip">{p.visible_count ?? "–"} wheals</span>
                  )}
                  {p.review_status === "confirmed" ? (
                    <span className="chip ok">reviewed</span>
                  ) : (
                    <span className="chip ai">needs review</span>
                  )}
                </span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}

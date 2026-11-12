import type { Lesion } from "../types";
import { lesionColor } from "./lesionStyle";

interface Props {
  lesions: Lesion[];
  selected: Set<string>;
  showRejected: boolean;
  editable: boolean;
  onSelect: (id: string, additive: boolean) => void;
  onReject: (id: string) => void;
  onRestore: (id: string) => void;
}

const SOURCE = { ai: "AI", user_added: "You", user_merged: "Merged" } as const;

export default function LesionTable({ lesions, selected, showRejected, editable, onSelect, onReject, onRestore }: Props) {
  const rows = lesions
    .filter((l) => l.status === "active" || (showRejected && l.status === "rejected"))
    .sort((a, b) => a.label - b.label);
  if (!rows.length) return <p className="muted">No lesions outlined.</p>;
  const mm = rows.some((l) => l.equiv_diameter_mm != null);

  return (
    <div className="table-wrap">
      <table className="lesions">
        <thead>
          <tr>
            <th>#</th>
            <th>Diameter ({mm ? "mm" : "px"})</th>
            <th>Area ({mm ? "mm²" : "px"})</th>
            <th>Size</th>
            <th title="Redness vs surrounding skin (CIELAB Δa*). Supplementary only.">Δa*</th>
            <th>Confidence</th>
            <th>Source</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((l) => (
            <tr
              key={l.id}
              className={`${selected.has(l.id) ? "selected" : ""} ${l.status === "rejected" ? "rejected" : ""}`}
              onClick={(e) => onSelect(l.id, e.shiftKey || e.metaKey || e.ctrlKey)}
            >
              <td>
                <span className="swatch" style={{ background: lesionColor(l) }} />
                {l.label}
              </td>
              <td>{(l.equiv_diameter_mm ?? l.equiv_diameter_px).toFixed(1)}</td>
              <td>{l.area_mm2 != null ? l.area_mm2.toFixed(1) : l.area_px}</td>
              <td>
                {l.size_class ?? "–"}
                {l.is_confluent && <span className="chip confl">confluent</span>}
              </td>
              <td>{l.delta_a_star?.toFixed(1) ?? "–"}</td>
              <td>{l.source === "ai" ? `${Math.round(l.confidence * 100)}%` : "–"}</td>
              <td>{SOURCE[l.source]}</td>
              <td>
                {editable &&
                  (l.status === "rejected" ? (
                    <button className="btn tiny" onClick={(e) => (e.stopPropagation(), onRestore(l.id))}>
                      Restore
                    </button>
                  ) : (
                    <button className="btn tiny ghost" onClick={(e) => (e.stopPropagation(), onReject(l.id))}>
                      Not a wheal
                    </button>
                  ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

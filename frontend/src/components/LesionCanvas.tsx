import { useEffect, useRef, useState } from "react";
import type { Lesion, Point } from "../types";
import { lesionColor } from "./lesionStyle";

export type Mode = "select" | "draw";

interface Props {
  imageUrl: string;
  width: number;
  height: number;
  lesions: Lesion[];
  selected: Set<string>;
  mode: Mode;
  showRejected: boolean;
  showLabels: boolean;
  threshold: number;
  zoom: number;
  onSelect: (id: string, additive: boolean) => void;
  onClearSelection: () => void;
  onPolygon: (pts: Point[]) => void;
}

/** The photo with an editable SVG overlay. All coordinates are working-image pixels. */
export default function LesionCanvas(props: Props) {
  const { imageUrl, width, height, lesions, selected, mode, showRejected, showLabels, threshold, zoom } = props;
  const svgRef = useRef<SVGSVGElement>(null);
  const [draft, setDraft] = useState<Point[]>([]);
  const [hover, setHover] = useState<Point | null>(null);
  const fontSize = Math.max(width, height) / 48;

  // Leaving draw mode discards an unfinished outline.
  useEffect(() => {
    if (mode !== "draw") setDraft([]);
  }, [mode]);

  useEffect(() => {
    if (mode !== "draw") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDraft([]);
      if (e.key === "Backspace") setDraft((d) => d.slice(0, -1));
      if (e.key === "Enter") {
        e.preventDefault(); // don't also "click" a focused toolbar button
        finish();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const toImage = (e: React.MouseEvent): Point => {
    const svg = svgRef.current!;
    const pt = svg.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const p = pt.matrixTransform(svg.getScreenCTM()!.inverse());
    return [Math.round(p.x), Math.round(p.y)];
  };

  const finish = (pts: Point[] = draft) => {
    if (pts.length >= 3) props.onPolygon(pts);
    setDraft([]);
  };

  // A double-click also fires two clicks, so drop the near-duplicate final point. Two quick
  // clicks in *different* places are just fast point placement, not "finish".
  const finishFromDoubleClick = () => {
    const pts = [...draft];
    const near = (a: Point, b: Point) => Math.hypot(a[0] - b[0], a[1] - b[1]) <= Math.max(width, height) / 300;
    if (pts.length < 2 || !near(pts[pts.length - 1], pts[pts.length - 2])) return;
    while (pts.length > 1 && near(pts[pts.length - 1], pts[pts.length - 2])) pts.pop();
    finish(pts);
  };

  const onClick = (e: React.MouseEvent) => {
    if (mode === "draw") {
      const p = toImage(e);
      setDraft((d) => [...d, p]);
    } else if (e.target === svgRef.current) {
      props.onClearSelection();
    }
  };

  const visible = lesions.filter((l) => l.status === "active" || (showRejected && l.status === "rejected"));

  return (
    <div className="canvas-scroll">
      <div className="canvas" style={{ width: `${zoom * 100}%`, aspectRatio: `${width} / ${height}` }}>
        <img src={imageUrl} alt="Photo under review" draggable={false} />
        <svg
          ref={svgRef}
          viewBox={`0 0 ${width} ${height}`}
          className={mode === "draw" ? "drawing" : ""}
          onClick={onClick}
          onDoubleClick={() => mode === "draw" && finishFromDoubleClick()}
          onMouseMove={(e) => mode === "draw" && setHover(toImage(e))}
          onMouseLeave={() => setHover(null)}
          role="img"
          aria-label={`${visible.filter((l) => l.status === "active").length} outlined lesions`}
        >
          <defs>
            <pattern id="hatch" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="10" stroke="#e879f9" strokeWidth="3" />
            </pattern>
          </defs>
          {visible.map((l) => {
            const pts = l.polygon.map((p) => p.join(",")).join(" ");
            const isSel = selected.has(l.id);
            const rejected = l.status === "rejected";
            const color = rejected ? "#9ca3af" : lesionColor(l);
            const low = l.source === "ai" && l.confidence < threshold;
            return (
              <g
                key={l.id}
                className="lesion"
                onClick={(e) => {
                  if (mode !== "select") return;
                  e.stopPropagation();
                  props.onSelect(l.id, e.shiftKey || e.metaKey || e.ctrlKey);
                }}
              >
                {isSel && (
                  <polygon points={pts} fill="none" stroke="#ffffff" strokeWidth={7} vectorEffect="non-scaling-stroke" />
                )}
                <polygon
                  points={pts}
                  fill={l.is_confluent && !rejected ? "url(#hatch)" : color}
                  fillOpacity={l.is_confluent && !rejected ? 0.5 : isSel ? 0.28 : 0.1}
                  stroke={color}
                  strokeWidth={isSel ? 3.5 : 2.25}
                  strokeDasharray={rejected ? "2 4" : low ? "6 4" : undefined}
                  vectorEffect="non-scaling-stroke"
                />
                {showLabels && !rejected && (
                  <text
                    x={l.centroid_x}
                    y={l.centroid_y}
                    fontSize={fontSize}
                    textAnchor="middle"
                    dominantBaseline="central"
                    className="lesion-label"
                  >
                    {l.label}
                  </text>
                )}
              </g>
            );
          })}
          {draft.length > 0 && (
            <g className="draft">
              <polyline
                points={[...draft, ...(hover ? [hover] : [])].map((p) => p.join(",")).join(" ")}
                fill="rgba(74,222,128,0.15)"
                stroke="#4ade80"
                strokeWidth={2.5}
                vectorEffect="non-scaling-stroke"
              />
              {draft.map(([x, y], i) => (
                <circle key={i} cx={x} cy={y} r={fontSize / 4} fill="#4ade80" />
              ))}
            </g>
          )}
        </svg>
      </div>
    </div>
  );
}

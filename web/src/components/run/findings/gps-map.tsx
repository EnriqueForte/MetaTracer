"use client";

import type { KeyboardEvent } from "react";

import { severityKey } from "@/lib/api/types";

import { SEVERITY_LABEL, type Finding } from "./model";

/** Same shape and range rules as classification/anchor.py::parse_gps_line. */
const GPS_LINE = /^Latitude: (-?\d+(?:\.\d+)?), Longitude: (-?\d+(?:\.\d+)?)(?:, Altitude: \S+)?$/;
const NULL_ISLAND = 1e-5;

export function parseGpsLine(snippet: string): { lat: number; lon: number } | null {
  const match = GPS_LINE.exec(snippet.trim());
  if (!match) return null;
  const lat = Number(match[1]);
  const lon = Number(match[2]);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return null;
  if (Math.abs(lat) < NULL_ISLAND && Math.abs(lon) < NULL_ISLAND) return null;
  return { lat, lon };
}

const WIDTH = 360;
const HEIGHT = 180;

/** Equirectangular: x from longitude, y from latitude. */
function project(lat: number, lon: number): [number, number] {
  return [lon + 180, 90 - lat];
}

/** Coarse continent outlines bundled with the app: no tiles, no network (CSP connect-src 'self'). */
const OUTLINES: [number, number][][] = [
  [[-168, 65], [-140, 70], [-95, 72], [-80, 62], [-60, 55], [-55, 47], [-70, 42], [-76, 35], [-81, 25], [-97, 26], [-97, 18], [-87, 15], [-83, 9], [-78, 8], [-92, 15], [-105, 20], [-117, 32], [-124, 40], [-124, 48], [-135, 57], [-150, 60], [-165, 60]],
  [[-55, 82], [-25, 83], [-20, 70], [-42, 60], [-55, 65]],
  [[-80, 10], [-62, 11], [-50, 0], [-35, -7], [-40, -22], [-48, -28], [-58, -38], [-65, -55], [-74, -52], [-72, -30], [-70, -18], [-81, -5]],
  [[-10, 36], [-9, 44], [-2, 48], [-5, 58], [5, 62], [15, 70], [30, 71], [40, 66], [40, 46], [28, 41], [20, 40], [12, 44], [3, 43]],
  [[-17, 21], [-10, 35], [10, 37], [32, 31], [43, 12], [51, 12], [40, -15], [32, -29], [20, -35], [12, -17], [9, 4], [-8, 4], [-17, 14]],
  [[40, 66], [70, 73], [110, 77], [140, 72], [180, 68], [170, 60], [140, 50], [130, 42], [122, 30], [110, 20], [105, 10], [100, 2], [92, 22], [78, 8], [72, 22], [57, 25], [52, 12], [43, 12], [35, 30], [28, 41], [40, 46]],
  [[113, -22], [122, -17], [131, -11], [142, -11], [146, -19], [153, -28], [150, -37], [140, -38], [130, -32], [115, -34]],
];

function outlinePath(points: [number, number][]): string {
  return (
    points
      .map(([lon, lat], index) => {
        const [x, y] = project(lat, lon);
        return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
      })
      .join(" ") + " Z"
  );
}

const MARKER_FILL: Record<string, string> = {
  critical: "fill-mt-sev-critical",
  high: "fill-mt-sev-high",
  medium: "fill-mt-sev-medium",
  low: "fill-mt-sev-low",
  info: "fill-mt-sev-info",
  unclassified: "fill-mt-sev-unclassified",
};

type Props = { findings: Finding[]; onOpen: (finding: Finding) => void };

export function GpsMap({ findings, onOpen }: Props) {
  const points = findings
    .filter((finding) => finding.finding_type === "gps")
    .map((finding) => ({ finding, at: parseGpsLine(finding.evidence_snippet) }))
    .filter((point): point is { finding: Finding; at: { lat: number; lon: number } } => point.at !== null);
  if (points.length === 0) return null;

  function onKey(event: KeyboardEvent<SVGGElement>, finding: Finding) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onOpen(finding);
    }
  }

  return (
    <details className="mt-card flex min-w-0 flex-col gap-3 p-4" open>
      <summary className="cursor-pointer">
        <h2 className="mt-section-title inline">GPS map</h2>{" "}
        <span className="mt-meta inline">({points.length} location(s), coordinates from the evidence only)</span>
      </summary>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="mt-3 h-auto max-h-72 w-full rounded-md bg-mt-bg"
        role="group"
        aria-label="GPS findings on a world outline"
      >
        {[-60, -30, 0, 30, 60].map((lat) => (
          <line key={`lat${lat}`} x1={0} x2={WIDTH} y1={90 - lat} y2={90 - lat} className="stroke-mt-border" strokeWidth={lat === 0 ? 0.6 : 0.3} />
        ))}
        {[-120, -60, 0, 60, 120].map((lon) => (
          <line key={`lon${lon}`} y1={0} y2={HEIGHT} x1={lon + 180} x2={lon + 180} className="stroke-mt-border" strokeWidth={lon === 0 ? 0.6 : 0.3} />
        ))}
        {OUTLINES.map((outline, index) => (
          <path key={index} d={outlinePath(outline)} className="fill-mt-elevated stroke-mt-border-strong" strokeWidth={0.4} />
        ))}
        {points.map(({ finding, at }) => {
          const [x, y] = project(at.lat, at.lon);
          const level = severityKey(finding.severity);
          const label = `${SEVERITY_LABEL[level]} GPS finding at ${at.lat.toFixed(4)}, ${at.lon.toFixed(4)}`;
          return (
            <g
              key={finding.id}
              role="button"
              tabIndex={0}
              aria-label={label}
              className="cursor-pointer focus:outline-none [&:focus-visible>circle:last-child]:stroke-mt-focus"
              onClick={() => onOpen(finding)}
              onKeyDown={(event) => onKey(event, finding)}
            >
              <title>{label}</title>
              <circle cx={x} cy={y} r={4} className="fill-mt-bg" />
              <circle cx={x} cy={y} r={2.6} className={`${MARKER_FILL[level]} stroke-mt-bg`} strokeWidth={0.8} />
            </g>
          );
        })}
      </svg>
      <p className="mt-meta">Outline is approximate and drawn locally; no map tiles are loaded.</p>
    </details>
  );
}

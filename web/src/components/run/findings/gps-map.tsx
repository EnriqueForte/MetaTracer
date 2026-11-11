"use client";

import type { KeyboardEvent } from "react";

import { severityKey } from "@/lib/api/types";

import landOutlines from "./land-outlines.json";
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

/** Natural Earth 110m land (public domain), simplified and bundled. No tiles. */
const LAND = landOutlines as [number, number][][][];

const WORLD_W = 360;
const WORLD_H = 180;

/** Equirectangular: x from longitude, y from latitude. */
function project(lat: number, lon: number): [number, number] {
  return [lon + 180, 90 - lat];
}

function ringPath(points: [number, number][]): string {
  return (
    points
      .map(([lon, lat], index) => {
        const [x, y] = project(lat, lon);
        return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
      })
      .join(" ") + " Z"
  );
}

function landPaths(): string[] {
  return LAND.map((polygon) => polygon.map(ringPath).join(" "));
}

type Frame = { x: number; y: number; w: number; h: number };

function frameOf(points: { lat: number; lon: number }[]): Frame {
  let minLat = 90;
  let maxLat = -90;
  let minLon = 180;
  let maxLon = -180;
  for (const point of points) {
    minLat = Math.min(minLat, point.lat);
    maxLat = Math.max(maxLat, point.lat);
    minLon = Math.min(minLon, point.lon);
    maxLon = Math.max(maxLon, point.lon);
  }
  if (maxLon - minLon > 180) return { x: 0, y: 0, w: WORLD_W, h: WORLD_H };
  const latSpan = Math.max(maxLat - minLat, 16);
  const lonSpan = Math.max(maxLon - minLon, 16);
  const midLat = (minLat + maxLat) / 2;
  const midLon = (minLon + maxLon) / 2;
  const south = Math.max(-90, midLat - latSpan * 0.7);
  const north = Math.min(90, midLat + latSpan * 0.7);
  const west = Math.max(-180, midLon - lonSpan * 0.7);
  const east = Math.min(180, midLon + lonSpan * 0.7);
  const x = west + 180;
  const y = 90 - north;
  return { x, y, w: Math.max(east - west, 8), h: Math.max(north - south, 8) };
}

const MARKER_FILL: Record<string, string> = {
  critical: "fill-mt-sev-critical",
  high: "fill-mt-sev-high",
  medium: "fill-mt-sev-medium",
  low: "fill-mt-sev-low",
  info: "fill-mt-sev-info",
  unclassified: "fill-mt-sev-unclassified",
};

const PATHS = landPaths();

type Props = { findings: Finding[]; onOpen: (finding: Finding) => void };

export function GpsMap({ findings, onOpen }: Props) {
  const points = findings
    .filter((finding) => finding.finding_type === "gps")
    .map((finding) => ({ finding, at: parseGpsLine(finding.evidence_snippet) }))
    .filter((point): point is { finding: Finding; at: { lat: number; lon: number } } => point.at !== null);
  if (points.length === 0) return null;

  const frame = frameOf(points.map((point) => point.at));
  const zoomed = frame.w < 240;
  const radius = Math.max(0.45, Math.min(frame.w, frame.h) * 0.018);
  const labelSize = Math.min(frame.w, frame.h) * 0.055;

  function onKey(event: KeyboardEvent<SVGGElement>, finding: Finding) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onOpen(finding);
    }
  }

  return (
    <details className="mt-card flex min-w-0 flex-col gap-3 p-4" open>
      <summary className="cursor-pointer">
        <h2 className="mt-section-title inline">Mapa GPS</h2>{" "}
        <span className="mt-meta inline">({points.length} ubicación(es), coordenadas solo de la evidencia)</span>
      </summary>
      <div
        className={
          zoomed
            ? "mt-3 grid min-w-0 grid-cols-1 gap-3 sm:h-72 sm:grid-cols-[7fr_3fr]"
            : "mt-3 grid h-72 min-w-0 grid-cols-1"
        }
      >
        <svg
          viewBox={`${frame.x.toFixed(2)} ${frame.y.toFixed(2)} ${frame.w.toFixed(2)} ${frame.h.toFixed(2)}`}
          preserveAspectRatio="xMidYMid meet"
          className="h-56 min-h-0 w-full overflow-hidden rounded-md bg-mt-bg sm:h-full"
          role="group"
          aria-label="Hallazgos GPS sobre un contorno terrestre local"
        >
          <rect x={0} y={0} width={WORLD_W} height={WORLD_H} className="fill-mt-bg" />
          {PATHS.map((d, index) => (
            <path
              key={index}
              d={d}
              fillRule="evenodd"
              vectorEffect="non-scaling-stroke"
              className="fill-mt-elevated stroke-mt-border-strong"
              strokeWidth={1}
            />
          ))}
          {points.map(({ finding, at }) => {
            const [x, y] = project(at.lat, at.lon);
            const level = severityKey(finding.severity);
            const label = `Hallazgo GPS ${SEVERITY_LABEL[level]} en ${at.lat.toFixed(4)}, ${at.lon.toFixed(4)}`;
            return (
              <g
                key={finding.id}
                role="button"
                tabIndex={0}
                aria-label={label}
                className="cursor-pointer focus:outline-none [&:focus-visible>circle:last-of-type]:stroke-mt-focus"
                onClick={() => onOpen(finding)}
                onKeyDown={(event) => onKey(event, finding)}
              >
                <title>{label}</title>
                <circle cx={x} cy={y} r={radius * 2.2} className="fill-none stroke-mt-fg" strokeWidth={radius * 0.25} />
                <circle cx={x} cy={y} r={radius} className={`${MARKER_FILL[level]} stroke-mt-bg`} strokeWidth={radius * 0.35} />
                {points.length <= 6 ? (
                  <text
                    x={x + radius * 2.8}
                    y={y + labelSize * 0.35}
                    className="fill-mt-fg"
                    fontSize={labelSize}
                    fontFamily="ui-monospace, monospace"
                  >
                    {at.lat.toFixed(2)}, {at.lon.toFixed(2)}
                  </text>
                ) : null}
              </g>
            );
          })}
        </svg>
        {zoomed ? (
          <div className="relative h-44 min-h-0 min-w-0 overflow-hidden rounded-md bg-mt-bg sm:h-full">
            <p className="mt-kicker pointer-events-none absolute left-2 top-2 z-10">Mundo</p>
            <svg
              viewBox={`0 0 ${WORLD_W} ${WORLD_H}`}
              preserveAspectRatio="xMidYMid slice"
              className="h-full w-full"
              aria-label="Contorno mundial con la región enmarcada"
            >
              {PATHS.map((d, index) => (
                <path key={index} d={d} fillRule="evenodd" className="fill-mt-elevated" />
              ))}
              <rect
                x={frame.x}
                y={frame.y}
                width={frame.w}
                height={frame.h}
                className="fill-none stroke-mt-accent"
                strokeWidth={2.5}
              />
              {points.map(({ finding, at }) => {
                const [x, y] = project(at.lat, at.lon);
                return <circle key={finding.id} cx={x} cy={y} r={3} className="fill-mt-fg" />;
              })}
            </svg>
          </div>
        ) : null}
      </div>
      <p className="mt-meta">
        La costa es un contorno Natural Earth empaquetado, dibujado en local. El marco sigue la evidencia.
        No se cargan teselas de mapa.
      </p>
    </details>
  );
}

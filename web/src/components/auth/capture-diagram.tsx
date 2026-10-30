import type { Ref } from "react";

const CX = 340;
const CY = 350;
const POINT_Y = CY - 16;
const POINT_R = 6;

const NODES = [
  { kicker: "Gate", label: "Confirmed scope", x: 340, y: 78, delay: "0.05s" },
  { kicker: "Capture", label: "In-scope GET", x: 92, y: 175, delay: "0.12s" },
  { kicker: "Extract", label: "EXIF · PDF · JS", x: 92, y: 350, delay: "0.18s" },
  { kicker: "Detect", label: "GPS", x: 92, y: 525, delay: "0.24s" },
  { kicker: "Detect", label: "Email", x: 230, y: 640, delay: "0.3s" },
  { kicker: "Detect", label: "Internal path", x: 430, y: 640, delay: "0.36s" },
  { kicker: "Detect", label: "Version · debug", x: 575, y: 175, delay: "0.42s" },
  { kicker: "Export", label: "Bounty report", x: 575, y: 525, delay: "0.48s" },
] as const;

const FIELDS = [
  { text: "EXIF:GPSInfo", x: 28, y: 24 },
  { text: "pdfinfo:Author", x: 700, y: 24 },
  { text: "http:server", x: 28, y: 688 },
  { text: "js:comment", x: 760, y: 688 },
  { text: "40.42, −3.70", x: 250, y: 32 },
] as const;

/**
 * Capture pipeline as a hub. The session spoke is drawn here (same viewBox as
 * the reticle) so it meets the centre point; AuthStage only supplies the
 * panel's x in this coordinate system.
 */
export function CaptureDiagram({
  svgRef,
  sessionX,
}: {
  svgRef?: Ref<SVGSVGElement | null>;
  sessionX?: number | null;
}) {
  const path =
    sessionX != null && sessionX > CX + POINT_R
      ? `M${CX},${POINT_Y} L${sessionX},${POINT_Y}`
      : "";
  return (
    <svg
      ref={svgRef}
      viewBox="0 0 720 720"
      preserveAspectRatio="xMidYMid meet"
      className="mt-auth-diagram"
      role="img"
      aria-label="Capture pipeline: confirmed scope, in-scope fetch, metadata extraction, detectors, bounty report"
    >
      <title>How MetaTracer captures metadata</title>
      {FIELDS.map((field) => (
        <text
          key={field.text}
          x={field.x}
          y={field.y}
          className="fill-mt-faint"
          fontSize={11}
          fontFamily="ui-monospace, monospace"
        >
          {field.text}
        </text>
      ))}
      <circle
        cx={CX}
        cy={CY}
        r={268}
        className="fill-none stroke-mt-border"
        strokeDasharray="3 7"
        strokeWidth={1}
      />
      {NODES.map((node) => (
        <line
          key={`spoke-${node.label}`}
          x1={CX}
          y1={CY}
          x2={node.x}
          y2={node.y}
          pathLength={1}
          className="mt-auth-spoke stroke-mt-border-strong"
          strokeWidth={1.25}
          style={{ animationDelay: node.delay }}
        />
      ))}
      <circle cx={CX} cy={CY} r={86} className="fill-mt-elevated stroke-mt-accent" strokeWidth={1.75} />
      {path ? (
        <line
          x1={CX}
          y1={POINT_Y}
          x2={sessionX}
          y2={POINT_Y}
          pathLength={1}
          className="mt-auth-spoke mt-auth-spoke-session stroke-mt-accent"
          strokeWidth={2}
        />
      ) : null}
      <g transform={`translate(${CX} ${POINT_Y})`} className="stroke-mt-accent fill-none" strokeWidth={2.2}>
        <circle r={22} />
        <circle r={POINT_R} className="fill-mt-accent stroke-none" />
        <path d="M0 -34 V-24 M0 24 V34 M-34 0 H-24 M24 0 H34" />
      </g>
      {path ? (
        <circle key={path} r={5} className="mt-auth-signal fill-mt-accent stroke-none">
          <animateMotion dur="1.1s" begin="0.55s" fill="freeze" path={path} />
        </circle>
      ) : null}
      <text x={CX} y={CY + 30} textAnchor="middle" className="fill-mt-fg" fontSize={15} fontWeight={600}>
        MetaTracer
      </text>
      <text x={CX} y={CY + 50} textAnchor="middle" className="fill-mt-muted" fontSize={11}>
        metadata capture
      </text>
      {NODES.map((node) => (
        <g
          key={node.label}
          className="mt-auth-node"
          transform={`translate(${node.x} ${node.y})`}
          style={{ animationDelay: node.delay }}
        >
          <rect
            x={-88}
            y={-24}
            width={176}
            height={48}
            rx={6}
            className="fill-mt-surface stroke-mt-border-strong"
            strokeWidth={1}
          />
          <text x={0} y={-4} textAnchor="middle" className="fill-mt-faint" fontSize={10}>
            {node.kicker}
          </text>
          <text x={0} y={14} textAnchor="middle" className="fill-mt-fg" fontSize={13} fontWeight={600}>
            {node.label}
          </text>
        </g>
      ))}
    </svg>
  );
}

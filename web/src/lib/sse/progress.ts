const STAGES = [
  "scope_validation",
  "discovery",
  "downloading",
  "extraction",
  "detection",
  "ai_analysis",
  "report_generation",
] as const;

export const STAGE_LABELS: Record<(typeof STAGES)[number], string> = {
  scope_validation: "Scope validation",
  discovery: "Discovery",
  downloading: "Downloading",
  extraction: "Metadata extraction",
  detection: "Detection",
  ai_analysis: "Classification and AI analysis",
  report_generation: "Report generation",
};

export type WorkStage = (typeof STAGES)[number];
export type StageState = "pending" | "active" | "done" | "failed";

export type ProgressTick = {
  stage: WorkStage | "completed" | "failed" | "aborted";
  message: string;
  current_asset: string | null;
  current_step: number;
  total_steps: number;
};

export function parseProgressEvent(value: unknown): ProgressTick | null {
  if (!value || typeof value !== "object") return null;
  const row = value as Record<string, unknown>;
  const stage = row.stage;
  const known =
    stage === "completed" ||
    stage === "failed" ||
    stage === "aborted" ||
    STAGES.includes(stage as WorkStage);
  if (!known) return null;
  if (typeof row.message !== "string") return null;
  if (typeof row.current_step !== "number" || typeof row.total_steps !== "number") return null;
  if (row.current_asset !== null && row.current_asset !== undefined && typeof row.current_asset !== "string") {
    return null;
  }
  return {
    stage: stage as ProgressTick["stage"],
    message: row.message,
    current_asset: typeof row.current_asset === "string" ? row.current_asset : null,
    current_step: row.current_step,
    total_steps: row.total_steps,
  };
}

export function applyProgress(
  states: StageState[],
  event: ProgressTick,
): StageState[] {
  const next = [...states];
  if (event.stage === "completed") return next.map(() => "done");
  if (event.stage === "failed" || event.stage === "aborted") {
    const active = next.findIndex((state) => state === "active");
    if (active >= 0) next[active] = "failed";
    return next;
  }
  const index = STAGES.indexOf(event.stage);
  return next.map((state, position) => {
    if (position < index) return "done";
    if (position === index) return "active";
    return state;
  });
}

export function initialStages(): StageState[] {
  return STAGES.map(() => "pending");
}

export { STAGES };

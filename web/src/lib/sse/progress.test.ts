import { describe, expect, it } from "vitest";

import { applyProgress, initialStages, parseProgressEvent } from "@/lib/sse/progress";

describe("progress events", () => {
  it("rejects a payload that is not a progress event", () => {
    expect(parseProgressEvent({ stage: "exploit", message: "x" })).toBeNull();
    expect(parseProgressEvent("<script>")).toBeNull();
  });

  it("marks earlier stages done and does not treat SSE failed as aborted", () => {
    const start = initialStages();
    const active = applyProgress(start, {
      stage: "discovery",
      message: "Looking",
      current_asset: null,
      current_step: 2,
      total_steps: 7,
    });
    expect(active[0]).toBe("done");
    expect(active[1]).toBe("active");
    const failed = applyProgress(active, {
      stage: "failed",
      message: "stopped",
      current_asset: null,
      current_step: 2,
      total_steps: 7,
    });
    expect(failed[1]).toBe("failed");
    expect(failed.includes("done") || failed.includes("failed")).toBe(true);
  });
});

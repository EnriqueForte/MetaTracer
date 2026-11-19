"use client";

import { useEffect, useRef } from "react";
import { BarChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";

import type { GraphMetrics } from "@/lib/api/graph";

import { hasMetricData, metricSeries, type BarSeries } from "./metrics-option";

echarts.use([BarChart, GridComponent, TooltipComponent, CanvasRenderer]);

function cssToken(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

function prefersReducedMotion(): boolean {
  return Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches);
}

function MiniBar({ series, colorToken }: { series: BarSeries; colorToken: string }) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = host.current;
    if (!node) return;
    const chart = echarts.init(node, undefined, { renderer: "canvas" });
    const fg = cssToken("--mt-fg", "#eaeff6");
    const muted = cssToken("--mt-muted", "#9aa9bb");
    const border = cssToken("--mt-border", "#1c2430");
    const color = cssToken(colorToken, "#6ad6ea");
    const reduced = prefersReducedMotion();
    chart.setOption({
      animation: !reduced,
      animationDuration: reduced ? 0 : 280,
      textStyle: { color: fg, fontFamily: "inherit" },
      tooltip: {
        trigger: "axis",
        renderMode: "richText",
        formatter: (params: unknown) => {
          if (!Array.isArray(params) || params.length === 0) return "";
          const first = params[0] as { axisValueLabel?: string; value?: number };
          return `${first.axisValueLabel ?? ""}: ${String(first.value ?? "")}`;
        },
      },
      grid: { left: 4, right: 12, top: 8, bottom: 4, containLabel: true },
      xAxis: {
        type: "value",
        minInterval: 1,
        axisLabel: { color: muted },
        splitLine: { lineStyle: { color: border } },
      },
      yAxis: {
        type: "category",
        data: series.labels,
        axisLabel: { color: muted, width: 140, overflow: "truncate" },
        axisLine: { lineStyle: { color: border } },
      },
      series: [
        {
          type: "bar",
          data: series.values,
          itemStyle: { color },
          barMaxWidth: 16,
        },
      ],
    });
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, [colorToken, series]);

  return (
    <div>
      <p className="mt-kicker">{series.title}</p>
      <div
        ref={host}
        className="mt-graph-canvas h-[160px] min-h-[160px]"
        role="img"
        aria-label={series.title}
      />
    </div>
  );
}

export function MetricsChart({ metrics }: { metrics: GraphMetrics }) {
  const series = metricSeries(metrics);
  const colors = ["--mt-chart-1", "--mt-chart-2", "--mt-chart-3"] as const;
  if (!hasMetricData(metrics)) {
    return <p className="text-sm text-mt-muted">Aún no hay métricas de inventario.</p>;
  }
  return (
    <div className="flex flex-col gap-3">
      {series.map((entry, index) => (
        <MiniBar key={entry.title} series={entry} colorToken={colors[index] ?? "--mt-chart-1"} />
      ))}
    </div>
  );
}

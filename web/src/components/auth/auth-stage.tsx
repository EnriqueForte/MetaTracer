"use client";

import { useLayoutEffect, useRef, useState, type ReactNode } from "react";

import { CaptureDiagram } from "@/components/auth/capture-diagram";

function panelXInDiagram(svg: SVGSVGElement, panel: HTMLElement): number | null {
  const box = panel.getBoundingClientRect();
  if (box.width === 0) return null;
  const ctm = typeof svg.getScreenCTM === "function" ? svg.getScreenCTM() : null;
  if (!ctm || typeof svg.createSVGPoint !== "function") return null;
  const point = svg.createSVGPoint();
  point.x = box.left + 2;
  point.y = 0;
  return point.matrixTransform(ctm.inverse()).x;
}

/** Session spoke is drawn in the diagram, aligned with the reticle point. */
export function AuthStage({ children, note }: { children: ReactNode; note?: ReactNode }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [sessionX, setSessionX] = useState<number | null>(null);

  useLayoutEffect(() => {
    const svg = svgRef.current;
    const panel = panelRef.current;
    if (!svg || !panel) return;

    function update() {
      if (!svgRef.current || !panelRef.current) return;
      setSessionX(panelXInDiagram(svgRef.current, panelRef.current));
    }

    update();
    window.addEventListener("resize", update);
    if (typeof ResizeObserver === "undefined") {
      return () => window.removeEventListener("resize", update);
    }
    const observer = new ResizeObserver(update);
    observer.observe(svg);
    observer.observe(panel);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", update);
    };
  }, []);

  return (
    <div className="mt-auth-frame">
      <aside className="mt-auth-brief" aria-label="Cómo funciona MetaTracer">
        <CaptureDiagram svgRef={svgRef} sessionX={sessionX} />
      </aside>
      <div className="mt-auth-stack">
        <div ref={panelRef} className="mt-auth-panel">
          {children}
        </div>
        {note ? <div className="mt-auth-note">{note}</div> : null}
      </div>
    </div>
  );
}

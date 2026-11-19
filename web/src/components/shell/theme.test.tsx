import { readFileSync } from "node:fs";
import path from "node:path";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ThemeSwitcher } from "@/components/shell/theme-switcher";
import { contrast, parseTokens } from "@/lib/contrast";

const CSS = readFileSync(path.resolve(__dirname, "../../app/globals.css"), "utf8");
const THEME_INIT = readFileSync(path.resolve(__dirname, "../../../public/theme-init.js"), "utf8");

function block(selector: string): string {
  const start = CSS.indexOf(selector);
  expect(start).toBeGreaterThanOrEqual(0);
  const open = CSS.indexOf("{", start);
  const close = CSS.indexOf("}", open);
  return CSS.slice(open + 1, close);
}

const DARK = parseTokens(block(":root {"));
const LIGHT = parseTokens(block(':root[data-theme="light"]'));
const SYSTEM_LIGHT = parseTokens(block(':root[data-theme="system"]'));

function runInit() {
  // Same code the browser runs before the first paint.
  new Function(THEME_INIT)();
}

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

afterEach(cleanup);

describe("Light mode (TASK-35)", () => {
  it("keeps the system-light palette identical to the explicit light palette", () => {
    expect(Object.keys(LIGHT).length).toBeGreaterThan(30);
    expect(SYSTEM_LIGHT).toEqual(LIGHT);
    expect(Object.keys(LIGHT).sort()).toEqual(
      Object.keys(DARK).filter((key) => key in LIGHT).sort(),
    );
  });

  it.each([
    ["dark", DARK],
    ["light", LIGHT],
  ])("meets WCAG AA in the %s theme", (_name, t) => {
    for (const text of ["fg", "muted", "faint"]) {
      for (const surface of ["bg", "surface", "elevated"]) {
        expect(contrast(t[text], t[surface]), `${text} on ${surface}`).toBeGreaterThanOrEqual(4.5);
      }
    }
    expect(contrast(t["accent-hover"], t.surface)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t["accent-fg"], t.accent)).toBeGreaterThanOrEqual(4.5);
    for (const surface of ["bg", "surface", "elevated"]) {
      expect(contrast(t.focus, t[surface]), `focus on ${surface}`).toBeGreaterThanOrEqual(3);
      expect(contrast(t["border-strong"], t[surface]), `border on ${surface}`).toBeGreaterThanOrEqual(3);
    }
    for (const tone of ["danger", "warning", "success"]) {
      expect(contrast(t[tone], t[`${tone}-bg`]), tone).toBeGreaterThanOrEqual(4.5);
    }
    for (const level of ["critical", "high", "medium", "low", "info", "unclassified"]) {
      expect(contrast(t[`sev-${level}`], t[`sev-${level}-bg`]), level).toBeGreaterThanOrEqual(4.5);
      expect(contrast(t[`sev-${level}`], t.surface), `${level} on surface`).toBeGreaterThanOrEqual(4.5);
    }
    // Provenance layers (U0): label text on the panel surface it sits on.
    for (const layer of ["observed", "inferred", "external"]) {
      expect(contrast(t[`layer-${layer}`], t.surface), `layer ${layer}`).toBeGreaterThanOrEqual(4.5);
      expect(contrast(t[`layer-${layer}`], t.elevated), `layer ${layer} on elevated`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("declares no permanently running animation", () => {
    // The brief forbids decorative, always-on motion. `mt-spin` is allowed
    // only as a bounded loading indicator and is the single exception.
    const infinite = [...CSS.matchAll(/animation:\s*([^;]+);/g)]
      .map((match) => match[1].trim())
      .filter((value) => value.includes("infinite"));
    expect(infinite.every((value) => value.includes("mt-spin"))).toBe(true);
    expect(CSS).not.toContain("@keyframes mt-sweep");
    expect(CSS).not.toContain("@keyframes mt-pulse");
    expect(CSS).not.toContain("@keyframes mt-asset");
    expect(CSS).not.toContain("@keyframes mt-skeleton");
  });

  it("exposes the density switch through a data attribute, not a rebuild", () => {
    expect(CSS).toContain('html[data-density="compact"]');
    expect(CSS).toContain("--mt-row-h-compact");
  });

  it("applies the stored choice before paint and defaults to dark", () => {
    runInit();
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    window.localStorage.setItem("mt-theme", "light");
    runInit();
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    window.localStorage.setItem("mt-theme", "<script>");
    runInit();
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("keeps the three theme choices in one equal row", () => {
    expect(CSS).toContain("grid-template-columns: repeat(3, minmax(0, 1fr))");
    expect(CSS).toContain(".mt-theme-option {");
    const option = block(".mt-theme-option {");
    expect(option).toContain("white-space: nowrap");
    expect(option).toContain("min-width: 0");
  });

  it("persists System / Dark / Light from the switcher", () => {
    render(<ThemeSwitcher />);
    fireEvent.click(screen.getByRole("radio", { name: "Sistema" }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("system");
    expect(window.localStorage.getItem("mt-theme")).toBe("system");
    fireEvent.click(screen.getByRole("radio", { name: "Claro" }));
    expect(screen.getByRole("radio", { name: "Claro" })).toHaveAttribute("aria-checked", "true");
    expect(window.localStorage.getItem("mt-theme")).toBe("light");
    cleanup();
    render(<ThemeSwitcher />);
    expect(screen.getByRole("radio", { name: "Claro" })).toHaveAttribute("aria-checked", "true");
  });
});

describe("App mark", () => {
  it("uses an original MetaTracer SVG, not a leftover Lucide bell", () => {
    const mark = readFileSync(path.resolve(__dirname, "../../../public/favicon.svg"), "utf8");
    const appIcon = readFileSync(path.resolve(__dirname, "../../app/icon.svg"), "utf8");
    expect(mark).toContain("#3cc4dc");
    expect(appIcon).toContain("#3cc4dc");
    expect(mark).not.toContain("#34d399");
    expect(mark).not.toContain("M15 17h5l-1.405");
    expect(block(".mt-brand-mark {")).toContain('url("/favicon.svg")');
  });
});

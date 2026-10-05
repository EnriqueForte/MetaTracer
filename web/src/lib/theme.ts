export const THEME_KEY = "mt-theme";
export const THEMES = ["system", "dark", "light"] as const;
export type ThemeChoice = (typeof THEMES)[number];

export function isThemeChoice(value: unknown): value is ThemeChoice {
  return value === "system" || value === "dark" || value === "light";
}

/** Dark stays the product default when nothing is stored. */
export function readTheme(): ThemeChoice {
  try {
    const stored = window.localStorage.getItem(THEME_KEY);
    return isThemeChoice(stored) ? stored : "dark";
  } catch {
    return "dark";
  }
}

export function applyTheme(choice: ThemeChoice): void {
  document.documentElement.setAttribute("data-theme", choice);
  try {
    window.localStorage.setItem(THEME_KEY, choice);
  } catch {
    /* private mode: the choice lasts for this page only */
  }
}

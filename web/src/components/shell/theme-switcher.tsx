"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";

import { applyTheme, readTheme, type ThemeChoice } from "@/lib/theme";

const OPTIONS: { value: ThemeChoice; label: string; icon: typeof Sun }[] = [
  { value: "system", label: "Sistema", icon: Monitor },
  { value: "dark", label: "Oscuro", icon: Moon },
  { value: "light", label: "Claro", icon: Sun },
];

export function ThemeSwitcher() {
  const [choice, setChoice] = useState<ThemeChoice>("dark");

  useEffect(() => {
    setChoice(readTheme());
  }, []);

  return (
    <div role="radiogroup" aria-label="Tema" className="mt-theme-switch">
      {OPTIONS.map((option) => {
        const Icon = option.icon;
        const selected = choice === option.value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={selected}
            className="mt-theme-option"
            onClick={() => {
              applyTheme(option.value);
              setChoice(option.value);
            }}
          >
            <Icon aria-hidden="true" className="size-3.5" />
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

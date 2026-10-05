"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";

import { applyTheme, readTheme, type ThemeChoice } from "@/lib/theme";

const OPTIONS: { value: ThemeChoice; label: string; icon: typeof Sun }[] = [
  { value: "system", label: "System", icon: Monitor },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "light", label: "Light", icon: Sun },
];

export function ThemeSwitcher() {
  const [choice, setChoice] = useState<ThemeChoice>("dark");

  useEffect(() => {
    setChoice(readTheme());
  }, []);

  return (
    <div role="radiogroup" aria-label="Theme" className="mt-theme-switch">
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

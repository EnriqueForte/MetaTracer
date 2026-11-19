/**
 * Page → public asset → leaked finding. Same kinds as the discovery graph.
 * Taller bowl so the page title sits inside the scan field.
 * Static: no looping motion (design system §6).
 */
export function EstadoScene() {
  return (
    <svg viewBox="0 0 360 156" overflow="visible" aria-hidden="true">
      <path
        d="M38 152 A142 142 0 0 1 322 152"
        fill="none"
        stroke="var(--mt-border)"
        strokeWidth="1"
      />
      <path
        d="M52 152 A128 128 0 0 1 308 152"
        fill="none"
        stroke="var(--mt-border)"
        strokeWidth="1"
      />
      <path
        d="M86 48 C130 28 150 68 180 46"
        fill="none"
        stroke="var(--mt-border-strong)"
        strokeWidth="1.4"
        strokeDasharray="3 4"
      />
      <path
        d="M206 48 C236 32 250 62 274 48"
        fill="none"
        stroke="var(--mt-accent)"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
      <path
        fill="var(--mt-elevated)"
        stroke="var(--mt-chart-1)"
        strokeWidth="1"
        opacity="0.4"
        d="M158 30h18l10 9v28h-28z"
      />
      <circle cx="72" cy="48" r="13" fill="var(--mt-elevated)" stroke="var(--mt-chart-2)" strokeWidth="2" />
      <circle cx="72" cy="48" r="4" fill="var(--mt-chart-2)" />
      <path fill="var(--mt-bg)" stroke="var(--mt-chart-1)" strokeWidth="1.5" d="M166 24h22l14 12v34h-36z" />
      <path fill="var(--mt-elevated)" stroke="var(--mt-chart-1)" strokeWidth="1.5" d="M188 24v12h14" />
      <path
        fill="none"
        stroke="var(--mt-border-strong)"
        strokeWidth="1.4"
        strokeLinecap="round"
        d="M174 46h18M174 52h12M174 58h16"
      />
      <circle cx="286" cy="48" r="16" fill="none" stroke="var(--mt-accent)" strokeWidth="1" opacity="0.45" />
      <path
        fill="none"
        stroke="var(--mt-accent)"
        strokeWidth="1.2"
        d="M286 36v4M286 56v4M274 48h4M294 48h4"
      />
      <rect
        x="278"
        y="40"
        width="16"
        height="16"
        rx="2"
        transform="rotate(45 286 48)"
        fill="var(--mt-elevated)"
        stroke="var(--mt-chart-4)"
        strokeWidth="1.6"
      />
      <circle cx="286" cy="48" r="2.2" fill="var(--mt-accent)" />
    </svg>
  );
}

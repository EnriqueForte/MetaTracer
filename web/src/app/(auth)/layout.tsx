import type { ReactNode } from "react";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <a className="mt-skip" href="#main-content">
        Skip to main content
      </a>
      {children}
    </>
  );
}

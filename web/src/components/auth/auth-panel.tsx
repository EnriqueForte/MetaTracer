import type { ReactNode } from "react";

import { AuthStage } from "@/components/auth/auth-stage";
import { MaintainerCredit } from "@/components/shell/maintainer-credit";

export function AuthPanel({
  title,
  lede,
  children,
  note,
}: {
  title: string;
  lede: string;
  children: ReactNode;
  note?: ReactNode;
}) {
  return (
    <main id="main-content" className="mt-auth">
      <AuthStage
        note={note}
      >
        <div>
          <p className="mt-kicker">Session</p>
          <h1 className="mt-title">{title}</h1>
          <p className="text-sm text-mt-muted">{lede}</p>
        </div>
        {children}
      </AuthStage>
      <MaintainerCredit placement="page" />
    </main>
  );
}

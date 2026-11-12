"use client";

import type { ReactNode } from "react";

import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";

import { FindingDetail } from "./finding-detail";
import { type Finding } from "./model";

type Props = {
  finding: Finding | null;
  canMutate: boolean;
  onClose: () => void;
  extra?: (finding: Finding) => ReactNode;
};

export function FindingSheet({ finding, canMutate, onClose, extra }: Props) {
  return (
    <Sheet open={finding !== null} onOpenChange={(open) => { if (!open) onClose(); }}>
      <SheetContent className="w-[min(36rem,100%)] overflow-y-auto">
        {finding ? (
          <>
            <SheetTitle>{finding.title}</SheetTitle>
            <SheetDescription className="sr-only">{finding.type_label}</SheetDescription>
            <FindingDetail finding={finding} canMutate={canMutate} extra={extra} heading={false} />
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

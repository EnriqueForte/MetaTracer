"use client";

import { useRef } from "react";

type AutoFocusHandler = (event: Event) => void;

/**
 * Radix only restores focus to a Dialog.Trigger. Our dialogs often open from
 * state, so remember what had focus at open time and return focus there on close.
 */
export function useRestoreFocus(onOpen?: AutoFocusHandler, onClose?: AutoFocusHandler) {
  const previous = useRef<HTMLElement | null>(null);
  return {
    onOpenAutoFocus: (event: Event) => {
      previous.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      onOpen?.(event);
    },
    onCloseAutoFocus: (event: Event) => {
      onClose?.(event);
      if (event.defaultPrevented) return;
      const target = previous.current;
      if (target && target.isConnected) {
        event.preventDefault();
        target.focus();
      }
    },
  };
}

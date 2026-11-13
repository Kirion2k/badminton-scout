"use client";

import { useEffect } from "react";

/** "/" focuses the player search from anywhere, unless the user is already typing. */
export function SlashFocus() {
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey)
        return;
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable=true]"))
        return;
      const search = document.querySelector<HTMLInputElement>(
        "input[name=q][data-player-search]",
      );
      if (!search) return;
      event.preventDefault();
      search.focus();
      search.select();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return null;
}

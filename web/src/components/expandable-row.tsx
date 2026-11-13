"use client";

import { ChevronRight } from "lucide-react";
import { type ReactNode, useId, useState } from "react";

import { cn } from "@/lib/utils";

/** A result row whose names stay ordinary links, with a separate button (the score) that opens
 * the scoresheet beneath it. Closed by default; the panel is in the DOM either way. */
export function ExpandableRow({
  main,
  score,
  label,
  children,
}: {
  main: ReactNode;
  score: ReactNode;
  label: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <li className="border-b border-border">
      <div
        className={cn(
          "grid grid-cols-[minmax(0,1fr)] items-center gap-x-3 px-2 py-2 sm:grid-cols-[minmax(0,1fr)_auto]",
          open && "bg-wash/70",
        )}
      >
        <div className="min-w-0 leading-snug">{main}</div>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={id}
          aria-label={label}
          onClick={() => setOpen(!open)}
          className="-my-1 flex min-h-10 items-center gap-2 justify-self-end rounded-md px-2 text-[14px] whitespace-nowrap hover:bg-wash sm:justify-self-auto"
        >
          {score}
          <ChevronRight
            aria-hidden
            className={cn(
              "size-4 text-subtle transition-transform duration-150",
              open && "rotate-90",
            )}
          />
        </button>
      </div>
      <div id={id} hidden={!open} className="px-2 pt-1 pb-3 text-[13px]">
        {children}
      </div>
    </li>
  );
}

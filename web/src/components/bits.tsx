import { ChevronDown } from "lucide-react";
import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { type Outcome, formatScore, resultLabel } from "@/lib/format";

// a won result is filled form green, a lost one outlined in red: shape and letter, not colour alone
const TONE = {
  win: "bg-win text-white",
  loss: "text-loss ring-1 ring-loss ring-inset",
  neutral: "text-neutral-status ring-1 ring-border ring-inset",
};

export function ResultBadge({
  status,
  result,
}: {
  status: string;
  result: Outcome;
}) {
  const label = resultLabel(status, result);
  return (
    <span
      title={label.title}
      className={cn(
        "num inline-flex h-6 min-w-6 items-center justify-center rounded-[3px] px-1.5 text-[12px] font-bold whitespace-nowrap",
        TONE[label.tone],
      )}
    >
      {label.text}
      <span className="sr-only"> ({label.title})</span>
    </span>
  );
}

export function Score({
  games,
}: {
  games: readonly (readonly [number, number])[];
}) {
  if (games.length === 0)
    return <span className="text-muted-foreground">–</span>;
  return <span className="num whitespace-nowrap">{formatScore(games)}</span>;
}

/** Decided results oldest → newest, as W/L squares. Undecided matches are left out. */
export function FormStrip({ results }: { results: ("won" | "lost")[] }) {
  if (results.length === 0) return null;
  const won = results.filter((r) => r === "won").length;
  return (
    <div className="flex items-center gap-3">
      <ol
        className="flex gap-1"
        aria-label={`Last ${results.length} decided matches, oldest first: ${won} won`}
      >
        {results.map((r, i) => (
          <li
            key={i}
            title={r === "won" ? "Won" : "Lost"}
            className={cn(
              "num flex size-[22px] items-center justify-center rounded-[3px] text-[12px] font-bold",
              r === "won"
                ? "bg-win text-white"
                : "text-loss ring-1 ring-loss ring-inset",
            )}
          >
            {r === "won" ? "W" : "L"}
          </li>
        ))}
      </ol>
    </div>
  );
}

/** Where a record comes from, always next to it: quiet, with the way to the coverage page. */
export function SourceNote({ children }: { children: ReactNode }) {
  return (
    <p className="flex flex-wrap items-center gap-x-1.5 text-xs text-subtle">
      <span>Source</span>
      <span className="text-muted-foreground">{children}</span>
      <span aria-hidden>·</span>
      <Link
        href="/coverage"
        className="underline decoration-foreground/25 underline-offset-[3px] transition-colors hover:text-foreground hover:decoration-current"
      >
        About this data
      </Link>
    </p>
  );
}

export function EmptyState({
  title,
  children,
}: {
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="px-6 py-14 text-center">
      <p className="text-[15px] font-medium">{title}</p>
      {children && (
        <div className="mt-1.5 text-sm text-muted-foreground">{children}</div>
      )}
    </div>
  );
}

export function RowsSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="space-y-3 p-5" role="status" aria-busy="true">
      <span className="sr-only">Loading…</span>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton
          key={i}
          className="h-10 w-full rounded-lg bg-muted"
          style={{ opacity: 1 - i * (0.6 / rows) }}
        />
      ))}
    </div>
  );
}

/** A native select in the shared control style: keyboard and mobile pickers come for free. */
export function Select({ className, ...props }: ComponentProps<"select">) {
  return (
    <span className={cn("relative inline-flex", className)}>
      <select
        {...props}
        className="control w-full cursor-pointer appearance-none pr-8"
      />
      <ChevronDown
        aria-hidden
        className="pointer-events-none absolute top-1/2 right-2.5 size-4 -translate-y-1/2 text-subtle"
      />
    </span>
  );
}

/** The quiet secondary button: filters, pagination. */
export const BUTTON_QUIET =
  "inline-flex h-9 items-center justify-center rounded-md bg-card px-4 text-sm font-medium text-foreground ring-1 ring-input transition-colors hover:bg-muted";

/** A page section: a green condensed heading over a green hairline, like a printed form. */
export function Section({
  id,
  title,
  action,
  children,
  className,
}: {
  id?: string;
  title: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section id={id} className={cn("min-w-0 scroll-mt-20", className)}>
      <div className="sheet-head">
        <h2>{title}</h2>
        {action && (
          <div className="text-[13px] font-normal text-muted-foreground [font-stretch:100%]">
            {action}
          </div>
        )}
      </div>
      {children}
    </section>
  );
}

export const LINK =
  "underline decoration-foreground/25 underline-offset-[3px] transition-colors hover:decoration-foreground";

/** Links to the previous/next page, keeping every other query parameter. */
export function Pager({
  path,
  params,
  page,
  pageSize,
  total,
}: {
  path: string;
  params: Record<string, string | undefined>;
  page: number;
  pageSize: number;
  total: number;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  const href = (p: number) => {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v) q.set(k, v);
    if (p > 1) q.set("page", String(p));
    const s = q.toString();
    return s ? `${path}?${s}` : path;
  };
  const link = cn(BUTTON_QUIET, "h-8 px-3 text-[13px]");
  return (
    <nav
      aria-label="Pages"
      className="flex items-center justify-between gap-4 border-t px-5 py-3.5 text-[13px]"
    >
      <span className="num text-subtle">
        Page {page} of {pages} · {total.toLocaleString("en-AU")} total
      </span>
      <span className="flex gap-2">
        {page > 1 ? (
          <Link className={link} href={href(page - 1)} rel="prev">
            Previous
          </Link>
        ) : null}
        {page < pages ? (
          <Link className={link} href={href(page + 1)} rel="next">
            Next
          </Link>
        ) : null}
      </span>
    </nav>
  );
}

/** A federation's country code, as results lists print it. */
export function FedCode({ code, label }: { code: string; label?: string }) {
  return (
    <span
      title={label}
      className="shrink-0 text-[12px] font-semibold tracking-[0.04em] text-muted-foreground"
    >
      <span aria-hidden={!!label}>{code}</span>
      {label && <span className="sr-only">{label}</span>}
    </span>
  );
}

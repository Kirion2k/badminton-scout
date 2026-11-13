import { ChevronDown } from "lucide-react";
import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  type Outcome,
  formatDate,
  formatRetrieved,
  formatScore,
  resultLabel,
} from "@/lib/format";

// solid result blocks, like a form guide: white on each tone is at least 5:1
const TONE = {
  win: "bg-win text-white",
  loss: "bg-loss text-white",
  neutral: "bg-muted text-neutral-status ring-1 ring-neutral-status/30",
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
        "num inline-flex h-7 min-w-9 items-center justify-center rounded-md px-2 font-display text-[13px] font-bold tracking-[0.04em] uppercase",
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
  return (
    <span className="num font-display text-[18px] font-semibold whitespace-nowrap">
      {formatScore(games)}
    </span>
  );
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
              "num flex size-7 items-center justify-center rounded-md font-display text-[13px] font-bold",
              r === "won" ? "bg-win text-white" : "bg-loss text-white",
            )}
          >
            {r === "won" ? "W" : "L"}
          </li>
        ))}
      </ol>
    </div>
  );
}

export function Provenance({
  sources,
  retrievedAt,
}: {
  sources: string[];
  retrievedAt: string | null | undefined;
}) {
  return (
    <SourceNote>
      {sources.join(", ") || "not recorded"} · {formatRetrieved(retrievedAt)}
    </SourceNote>
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

const LABEL = "label-quiet";

export function Label({ children }: { children: ReactNode }) {
  return <span className={LABEL}>{children}</span>;
}

/** A labelled value inside a <dl>: the term styled as a label, the value as given. */
export function Fact({
  term,
  title,
  className,
  children,
}: {
  term: string;
  title?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div title={title} className={className}>
      <dt className={LABEL}>{term}</dt>
      <dd className="mt-1.5">{children}</dd>
    </div>
  );
}

export function Panel({
  title,
  children,
  className,
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "min-w-0 rounded-[10px] bg-card ring-1 ring-border",
        className,
      )}
    >
      {title && (
        <h2 className="px-5 pt-4 pb-1 text-[13px] font-medium text-muted-foreground">
          {title}
        </h2>
      )}
      {children}
    </section>
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
    <div className="space-y-3 p-5" aria-busy="true" aria-label="Loading">
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

export function PageHeader({
  title,
  eyebrow,
  children,
}: {
  title: ReactNode;
  eyebrow?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="space-y-4 pb-10">
      {eyebrow && <p className="label-quiet">{eyebrow}</p>}
      <h1 className="display max-w-4xl text-[36px] leading-[1] text-balance uppercase sm:text-[52px]">
        {title}
      </h1>
      {children}
    </div>
  );
}

/** Icon + text items in one quiet line ("24–25 Oct 2026 · Melbourne · Badminton Victoria"). */
export function MetaRow({ children }: { children: ReactNode }) {
  return (
    <ul className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-muted-foreground">
      {children}
    </ul>
  );
}

export function MetaItem({
  icon: Icon,
  label,
  children,
}: {
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  label: string;
  children: ReactNode;
}) {
  return (
    <li className="flex min-w-0 items-center gap-2">
      <Icon aria-hidden className="size-4 shrink-0 text-subtle" />
      <span className="sr-only">{label}: </span>
      <span className="min-w-0 truncate text-foreground">{children}</span>
    </li>
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

/** Link pills for one choice among a few (events). The selected one is marked, not loud. */
export function PillLink({
  href,
  selected,
  children,
}: {
  href: string;
  selected: boolean;
  children: ReactNode;
}) {
  return (
    <Link
      href={href}
      aria-current={selected ? "page" : undefined}
      className={cn(
        "relative inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full px-3.5 text-[13px] whitespace-nowrap transition-colors duration-150",
        selected
          ? "bg-night text-on-dark"
          : "text-muted-foreground ring-1 ring-border hover:bg-muted hover:text-foreground",
      )}
    >
      {children}
    </Link>
  );
}

/** The quiet secondary button: filters, pagination. */
export const BUTTON_QUIET =
  "inline-flex h-10 items-center justify-center rounded-lg bg-card px-4 text-sm font-medium text-foreground ring-1 ring-input transition-colors hover:bg-muted";

/** A page section: a condensed uppercase heading over a heavy rule, like a broadcast lower third. */
export function Section({
  title,
  action,
  children,
  className,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("min-w-0", className)}>
      <div className="flex items-baseline justify-between gap-4 border-b-2 border-foreground pb-2">
        <h2 className="display text-[22px] tracking-[0.02em] uppercase">
          {title}
        </h2>
        {action && <div className="text-[13px]">{action}</div>}
      </div>
      {children}
    </section>
  );
}

/** A big condensed figure with its label: real counts only. */
export function Stat({ value, label }: { value: ReactNode; label: string }) {
  return (
    <div>
      <p className="reveal display num text-[40px] leading-none">{value}</p>
      <p className="label-quiet mt-1.5">{label}</p>
    </div>
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

/** A calendar-style date: big day, small month and year. Screen readers get the full date. */
export function DateBlock({ iso }: { iso: string | null | undefined }) {
  if (!iso)
    return <span className="text-[13px] text-subtle">Date not recorded</span>;
  const d = new Date(`${iso}T00:00:00Z`);
  return (
    <span className="flex flex-col leading-none">
      <span aria-hidden className="display num text-[30px]">
        {d.getUTCDate()}
      </span>
      <span aria-hidden className="label-quiet mt-1 text-[11px]">
        {d.toLocaleDateString("en-AU", {
          month: "short",
          year: "numeric",
          timeZone: "UTC",
        })}
      </span>
      <span className="sr-only">{formatDate(iso)}</span>
    </span>
  );
}

/** A federation's country code in a small badge, the sports-results way of marking a nation. */
export function FedCode({
  code,
  label,
  dark = false,
}: {
  code: string;
  /** Spoken in place of the code where no country name is shown next to it. */
  label?: string;
  dark?: boolean;
}) {
  return (
    <span
      aria-hidden={!label}
      title={label}
      className={cn(
        "inline-flex h-5 min-w-9 shrink-0 items-center justify-center rounded-[4px] px-1 font-display text-[11px] font-bold tracking-[0.08em]",
        dark ? "bg-white/12 text-on-dark" : "bg-night text-on-dark",
      )}
    >
      <span aria-hidden>{code}</span>
      {label && <span className="sr-only">{label}</span>}
    </span>
  );
}

/** A person's initials in a crest: the identity mark used instead of a photo we do not hold. */
export function Monogram({
  name,
  className,
}: {
  name: string;
  className?: string;
}) {
  const initials = name
    .split(/[\s/-]+/)
    .filter(Boolean)
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
  return (
    <span
      aria-hidden
      className={cn(
        "relative flex shrink-0 items-center justify-center overflow-hidden rounded-xl bg-night font-display font-bold text-on-dark",
        className,
      )}
    >
      <span className="absolute inset-x-0 bottom-0 h-1 bg-lime" />
      {initials}
    </span>
  );
}

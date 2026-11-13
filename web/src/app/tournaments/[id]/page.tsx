import { Building2, CalendarDays, Info, MapPin } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import {
  BUTTON_QUIET,
  EmptyState,
  Pager,
  RowsSkeleton,
  Select,
} from "@/components/bits";
import { Scoreboard } from "@/components/scoreboard";
import { Container, Hero, Shell } from "@/components/shell";
import { Skeleton } from "@/components/ui/skeleton";
import { type TournamentDetail, api } from "@/lib/api/client";
import { DISCIPLINES, formatDateRange, one, positiveInt } from "@/lib/format";
import { FEDERATION, importFlag } from "@/lib/providers";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Tournament" };

const PAGE_SIZE = 60;
const CHIP_LIMIT = 24; // more events than this in one view: a menu instead of chips
const ORDER = ["MS", "WS", "MD", "WD", "XD"];

export default function TournamentPage({
  params,
  searchParams,
}: PageProps<"/tournaments/[id]">) {
  return (
    <Shell
      hero={
        <Suspense fallback={<MatchCentreSkeleton />}>
          <MatchCentre params={params} searchParams={searchParams} />
        </Suspense>
      }
    />
  );
}

type View = { discipline?: string; event?: string };

function href(id: number, view: View) {
  const q = new URLSearchParams();
  if (view.discipline) q.set("discipline", view.discipline);
  if (view.event) q.set("event", view.event);
  const s = q.toString();
  return `/tournaments/${id}${s ? `?${s}` : ""}`;
}

async function MatchCentre({
  params,
  searchParams,
}: PageProps<"/tournaments/[id]">) {
  const id = Number((await params).id);
  if (!Number.isSafeInteger(id) || id < 1) notFound();
  const sp = await searchParams;
  const page = positiveInt(one(sp.page), 1);
  const detail = await api.tournament(id);
  const selected = detail.events.find((e) => e.name === one(sp.event));
  // an event implies its discipline; a discipline with no events here is ignored
  const asked = one(sp.discipline);
  const discipline =
    selected?.discipline ??
    (detail.events.some((e) => e.discipline === asked) ? asked : undefined);
  const view: View = { discipline, event: selected?.name };
  const matches = await api.tournamentMatches(id, {
    event: selected?.name,
    discipline: selected ? undefined : discipline,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  });
  // one event: its stages (rounds) are the groups; otherwise each event is a group
  const groups = selected
    ? groupBy(matches.items, (m) => m.round ?? "Round not recorded")
    : groupBy(matches.items, (m) => m.event);
  const title = selected
    ? selected.name
    : discipline
      ? DISCIPLINES[discipline]
      : "All matches";

  return (
    <>
      <TournamentHero id={id} detail={detail} view={view} />
      <Container>
        <EventChips id={id} detail={detail} view={view} />
        <ImportNote detail={detail} />
        <section aria-labelledby="matches-heading" className="min-w-0">
          <div className="flex items-baseline justify-between gap-3 pb-1">
            <h2 id="matches-heading" className="display text-[26px] uppercase">
              {title}
            </h2>
            <span className="label-quiet num">
              {matches.total.toLocaleString("en-AU")}{" "}
              {matches.total === 1 ? "match" : "matches"}
            </span>
          </div>
          {matches.items.length === 0 ? (
            <EmptyState
              title={
                page > 1 && matches.total > 0
                  ? "No more matches"
                  : "No matches in this event"
              }
            >
              {page > 1 && matches.total > 0 && (
                <Link
                  className="underline underline-offset-[3px]"
                  href={href(id, view)}
                >
                  Back to the first page
                </Link>
              )}
            </EmptyState>
          ) : (
            groups.map(([name, rows], i) => (
              <section key={`${name}-${i}`} aria-label={name} className="pt-6">
                <h3 className="sticky top-14 z-10 -mx-1 flex items-center gap-3 bg-background/95 px-1 py-2.5 backdrop-blur lg:top-16">
                  <span className="font-display text-[15px] font-bold tracking-[0.1em] uppercase">
                    {name}
                  </span>
                  {!selected && rows[0].discipline && (
                    <span className="label-quiet text-[11px]">
                      {DISCIPLINES[rows[0].discipline] ?? rows[0].discipline}
                    </span>
                  )}
                  <span aria-hidden className="h-px flex-1 bg-border" />
                </h3>
                <ul className="grid grid-cols-[minmax(0,1fr)] gap-2.5 lg:grid-cols-2">
                  {rows.map((m) => (
                    <Scoreboard key={m.id} match={m} showRound={!selected} />
                  ))}
                </ul>
              </section>
            ))
          )}
          <div className="mt-8">
            <Pager
              path={`/tournaments/${id}`}
              params={{
                discipline: selected ? undefined : discipline,
                event: selected?.name,
              }}
              page={page}
              pageSize={PAGE_SIZE}
              total={matches.total}
            />
          </div>
        </section>
      </Container>
    </>
  );
}

/** The court-green header: identity, facts, provenance, and the discipline tabs on its edge. */
function TournamentHero({
  id,
  detail,
  view,
}: {
  id: number;
  detail: TournamentDetail;
  view: View;
}) {
  const fed = FEDERATION[detail.source_id];
  const total = detail.events.reduce((n, e) => n + e.matches, 0);
  const days =
    detail.start_date && detail.end_date
      ? Math.round(
          (Date.parse(detail.end_date) - Date.parse(detail.start_date)) /
            86_400_000,
        ) + 1
      : null;
  const counts = new Map<string, number>();
  for (const e of detail.events)
    if (e.discipline && ORDER.includes(e.discipline))
      counts.set(e.discipline, (counts.get(e.discipline) ?? 0) + e.matches);
  const complete = detail.import_state?.status === "complete";
  return (
    <Hero tone="court">
      <p className="font-display text-[13px] font-semibold tracking-[0.14em] text-lime uppercase">
        {fed
          ? `${fed.country ?? "International"} · ${fed.label}`
          : "Tournament"}
      </p>
      <h1 className="display mt-3 max-w-4xl text-[36px] leading-[0.98] text-balance sm:text-[52px]">
        {detail.name ?? "Unnamed tournament"}
      </h1>
      <ul className="mt-4 flex flex-wrap gap-x-6 gap-y-1.5 text-[14px] text-on-court-muted sm:mt-5">
        <HeroMeta icon={CalendarDays} label="Dates">
          <span className="num">
            {formatDateRange(detail.start_date, detail.end_date)}
          </span>
        </HeroMeta>
        <HeroMeta icon={MapPin} label="Location">
          {detail.location ?? "Not recorded"}
        </HeroMeta>
        {detail.organiser && (
          <HeroMeta icon={Building2} label="Organiser">
            {detail.organiser}
          </HeroMeta>
        )}
      </ul>
      <dl className="mt-4 flex flex-wrap items-end gap-x-7 gap-y-3 sm:mt-6 sm:gap-x-10">
        <HeroFact term="Events" value={detail.events.length} />
        <HeroFact term="Matches" value={total} />
        {days !== null && days > 0 && <HeroFact term="Days" value={days} />}
        <div className="pb-1">
          <dt className="sr-only">Import</dt>
          <dd
            className={cn(
              "rounded px-2 py-1 font-display text-[12px] font-semibold tracking-[0.1em] uppercase",
              complete ? "bg-lime text-night" : "bg-white/12 text-on-dark",
            )}
            title={detail.import_state?.note}
          >
            {complete
              ? "Imported in full"
              : (importFlag(detail.import_state) ?? "Import status unknown")}
          </dd>
        </div>
      </dl>
      <p className="mt-4 text-[12px] text-on-court-muted sm:mt-5">
        Source {detail.source} ·{" "}
        <Link
          href="/coverage"
          className="underline decoration-white/30 underline-offset-[3px] hover:text-on-dark"
        >
          About this data
        </Link>
      </p>
      <nav
        aria-label="Disciplines"
        className="-mx-4 mt-5 flex scroll-px-4 gap-0.5 overflow-x-auto px-4 sm:mx-0 sm:mt-7 sm:gap-1 sm:px-0"
      >
        <DisciplineTab
          href={href(id, {})}
          current={!view.discipline}
          code="All"
          name="All disciplines"
          count={total}
        />
        {ORDER.filter((d) => counts.has(d)).map((d) => (
          <DisciplineTab
            key={d}
            href={href(id, { discipline: d })}
            current={view.discipline === d}
            code={d}
            name={DISCIPLINES[d]}
            count={counts.get(d)!}
          />
        ))}
      </nav>
    </Hero>
  );
}

function HeroMeta({
  icon: Icon,
  label,
  children,
}: {
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <li className="flex min-w-0 items-center gap-2">
      <Icon aria-hidden className="size-4 shrink-0" />
      <span className="sr-only">{label}: </span>
      <span className="min-w-0 truncate text-on-dark">{children}</span>
    </li>
  );
}

function HeroFact({ term, value }: { term: string; value: number }) {
  return (
    <div className="flex flex-col-reverse">
      <dt className="mt-1 font-display text-[12px] font-semibold tracking-[0.12em] text-on-court-muted uppercase">
        {term}
      </dt>
      <dd className="reveal display num text-[30px] leading-none sm:text-[40px]">
        {value.toLocaleString("en-AU")}
      </dd>
    </div>
  );
}

/** A discipline tab: the code big (MS, WD…), the full name for screen readers and on hover. The
 * current tab takes the page colour, so it reads as the open folder of the match centre. */
function DisciplineTab({
  href,
  current,
  code,
  name,
  count,
}: {
  href: string;
  current: boolean;
  code: string;
  name: string;
  count: number;
}) {
  return (
    <Link
      href={href}
      title={name}
      aria-current={current ? "page" : undefined}
      className={cn(
        "flex shrink-0 items-baseline gap-1.5 rounded-t-[10px] px-3 pt-3 pb-3.5 transition-colors duration-150 sm:px-4",
        current
          ? "bg-background text-foreground"
          : "text-on-court-muted hover:bg-white/8 hover:text-on-dark",
      )}
    >
      <span
        aria-hidden
        className="font-display text-[19px] font-bold tracking-[0.05em] uppercase"
      >
        {code}
      </span>
      <span className="sr-only">{name}</span>
      {/* the count is spoken everywhere but shown from 640 px, so six tabs fit a phone */}
      <span className="sr-only">, {count} matches</span>
      <span aria-hidden className="num hidden text-[12px] sm:inline">
        {count.toLocaleString("en-AU")}
      </span>
    </Link>
  );
}

/** The events of the open discipline as chips; past CHIP_LIMIT, a menu that works without JS. */
function EventChips({
  id,
  detail,
  view,
}: {
  id: number;
  detail: TournamentDetail;
  view: View;
}) {
  const events = detail.events.filter(
    (e) => !view.discipline || e.discipline === view.discipline,
  );
  if (events.length <= 1 && !view.event) return null;
  if (events.length > CHIP_LIMIT) {
    return (
      <form
        action={`/tournaments/${id}`}
        method="get"
        className="mb-8 flex flex-wrap items-end gap-2"
      >
        {view.discipline && (
          <input type="hidden" name="discipline" value={view.discipline} />
        )}
        <label className="min-w-0 flex-1 sm:max-w-md">
          <span className="label-quiet mb-1.5 block">
            Event ({events.length})
          </span>
          <Select
            name="event"
            defaultValue={view.event ?? ""}
            className="w-full"
          >
            <option value="">All {events.length} events</option>
            {events.map((e) => (
              <option key={e.name} value={e.name}>
                {e.name} ({e.matches})
              </option>
            ))}
          </Select>
        </label>
        <button type="submit" className={BUTTON_QUIET}>
          Show
        </button>
      </form>
    );
  }
  return (
    <nav aria-label="Events" className="mb-8">
      <ul className="-mx-4 flex scroll-px-4 gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:px-0">
        <li className="shrink-0">
          <Chip
            href={href(id, { discipline: view.discipline })}
            current={!view.event}
            label={
              view.discipline
                ? `All ${DISCIPLINES[view.discipline]?.toLowerCase()}`
                : "All events"
            }
            count={events.reduce((n, e) => n + e.matches, 0)}
          />
        </li>
        {events.map((e) => (
          <li key={e.name} className="shrink-0">
            <Chip
              href={href(id, { discipline: view.discipline, event: e.name })}
              current={view.event === e.name}
              label={e.name}
              count={e.matches}
            />
          </li>
        ))}
      </ul>
    </nav>
  );
}

function Chip({
  href,
  current,
  label,
  count,
}: {
  href: string;
  current: boolean;
  label: string;
  count: number;
}) {
  return (
    <Link
      href={href}
      aria-current={current ? "page" : undefined}
      className={cn(
        "relative inline-flex h-11 items-center gap-2 rounded-full px-3.5 text-[13px] whitespace-nowrap ring-1 transition-colors duration-150",
        current
          ? "bg-night font-medium text-on-dark ring-night"
          : "bg-card text-foreground ring-border hover:ring-foreground/30",
      )}
    >
      {label}
      <span
        className={cn("num text-[12px]", current ? "text-lime" : "text-subtle")}
      >
        <span className="sr-only">, </span>
        {count}
        <span className="sr-only"> matches</span>
      </span>
    </Link>
  );
}

function ImportNote({ detail }: { detail: TournamentDetail }) {
  const flag = importFlag(detail.import_state);
  if (!flag) return null;
  return (
    <p
      role="note"
      className="mb-8 flex max-w-3xl items-start gap-2.5 rounded-lg bg-muted px-4 py-3 text-[14px] text-muted-foreground"
    >
      <Info aria-hidden className="mt-0.5 size-4 shrink-0 text-foreground" />
      <span>
        <span className="font-medium text-foreground">{flag}.</span>{" "}
        {detail.import_state?.note}
        {detail.import_state?.status !== "complete_with_gaps" &&
        detail.import_state?.unimported_matches
          ? ` ${detail.import_state.unimported_matches} more could not be imported.`
          : ""}{" "}
        Counts on this page cover the matches we hold.
      </span>
    </p>
  );
}

/** Groups by key in first-seen order: a round played over two days is still one group. */
function groupBy<T>(items: T[], key: (item: T) => string): [string, T[]][] {
  const groups = new Map<string, T[]>();
  for (const item of items) {
    const k = key(item);
    groups.set(k, [...(groups.get(k) ?? []), item]);
  }
  return [...groups];
}

function MatchCentreSkeleton() {
  return (
    <>
      <Hero tone="court">
        <div className="space-y-4 pb-16" role="status" aria-busy="true">
          <span className="sr-only">Loading tournament…</span>
          <Skeleton className="h-3 w-40 bg-white/10" />
          <Skeleton className="h-12 w-[36rem] max-w-full bg-white/10" />
          <Skeleton className="h-4 w-80 max-w-full bg-white/10" />
        </div>
      </Hero>
      <Container>
        <RowsSkeleton rows={8} />
      </Container>
    </>
  );
}

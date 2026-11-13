import {
  Building2,
  CalendarDays,
  Info,
  ListOrdered,
  MapPin,
} from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import {
  BUTTON_QUIET,
  EmptyState,
  MetaItem,
  MetaRow,
  PageHeader,
  Pager,
  RowsSkeleton,
  Select,
  SourceNote,
} from "@/components/bits";
import { Shell } from "@/components/shell";
import { Skeleton } from "@/components/ui/skeleton";
import {
  type TournamentDetail,
  type TournamentMatch,
  api,
} from "@/lib/api/client";
import {
  DISCIPLINES,
  formatDate,
  formatDateRange,
  formatScore,
  one,
  positiveInt,
  statusNote,
} from "@/lib/format";
import { FEDERATION, importFlag } from "@/lib/providers";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Tournament" };

const PAGE_SIZE = 60;
const NAVIGATOR_LIMIT = 40; // more events than this: a menu instead of a list

export default function TournamentPage({
  params,
  searchParams,
}: PageProps<"/tournaments/[id]">) {
  return (
    <Shell>
      <Suspense
        fallback={
          <div className="space-y-6">
            <Skeleton className="h-3 w-40 bg-muted" />
            <Skeleton className="h-14 w-[36rem] max-w-full bg-muted" />
            <Skeleton className="h-4 w-80 max-w-full bg-muted" />
            <RowsSkeleton rows={8} />
          </div>
        }
      >
        <Tournament params={params} searchParams={searchParams} />
      </Suspense>
    </Shell>
  );
}

async function Tournament({
  params,
  searchParams,
}: PageProps<"/tournaments/[id]">) {
  const id = Number((await params).id);
  if (!Number.isSafeInteger(id) || id < 1) notFound();
  const sp = await searchParams;
  const event = one(sp.event);
  const page = positiveInt(one(sp.page), 1);
  const detail = await api.tournament(id);
  const known = detail.events.some((e) => e.name === event);
  const matches = await api.tournamentMatches(id, {
    event: known ? event : undefined,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  });
  const total = detail.events.reduce((n, e) => n + e.matches, 0);
  const fed = FEDERATION[detail.source_id];
  const flag = importFlag(detail.import_state);
  // one event: its stages (rounds) are the groups; all events: each event is a group
  const groups = known
    ? groupBy(matches.items, (m) => m.round ?? "Round not recorded")
    : groupBy(matches.items, (m) => m.event);

  return (
    <>
      <PageHeader
        eyebrow={
          fed
            ? `${fed.country ?? "International"} · ${fed.label}`
            : "Tournament"
        }
        title={detail.name ?? "Unnamed tournament"}
      >
        <MetaRow>
          <MetaItem icon={CalendarDays} label="Dates">
            <span className="num">
              {formatDateRange(detail.start_date, detail.end_date)}
            </span>
          </MetaItem>
          <MetaItem icon={MapPin} label="Location">
            {detail.location ?? "Not recorded"}
          </MetaItem>
          {detail.organiser && (
            <MetaItem icon={Building2} label="Organiser">
              {detail.organiser}
            </MetaItem>
          )}
          <MetaItem icon={ListOrdered} label="Size">
            <span className="num">
              {detail.events.length}{" "}
              {detail.events.length === 1 ? "event" : "events"} ·{" "}
              {total.toLocaleString("en-AU")} matches
            </span>
          </MetaItem>
        </MetaRow>
        <SourceNote>{detail.source}</SourceNote>
        {flag && (
          <p
            role="note"
            className="flex max-w-2xl items-start gap-2.5 rounded-lg bg-muted px-4 py-3 text-[14px] text-muted-foreground"
          >
            <Info
              aria-hidden
              className="mt-0.5 size-4 shrink-0 text-foreground"
            />
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
        )}
      </PageHeader>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-10 lg:grid-cols-[16rem_minmax(0,1fr)] lg:gap-12">
        <EventNavigator
          id={id}
          detail={detail}
          current={known ? event : undefined}
        />
        <section aria-labelledby="matches-heading" className="min-w-0">
          <div className="flex items-baseline justify-between gap-3 border-b border-foreground/80 pb-2">
            <h2
              id="matches-heading"
              className="display text-[22px] font-semibold"
            >
              {known ? event : "All matches"}
            </h2>
            <span className="num text-[13px] text-muted-foreground">
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
            />
          ) : (
            groups.map(([name, rows], i) => (
              <section key={`${name}-${i}`} aria-label={name}>
                <h3 className="sticky top-14 z-10 flex items-baseline gap-3 bg-background/95 pt-7 pb-3 backdrop-blur lg:top-0">
                  <span className="label-quiet text-foreground">{name}</span>
                  {!known && rows[0].discipline && (
                    <span className="text-[12px] text-subtle">
                      {DISCIPLINES[rows[0].discipline] ?? rows[0].discipline}
                    </span>
                  )}
                </h3>
                <ul className="grid grid-cols-[minmax(0,1fr)] gap-2.5">
                  {rows.map((m) => (
                    <MatchCard key={m.id} match={m} showEvent={known} />
                  ))}
                </ul>
              </section>
            ))
          )}
          <Pager
            path={`/tournaments/${id}`}
            params={{ event: known ? event : undefined }}
            page={page}
            pageSize={PAGE_SIZE}
            total={matches.total}
          />
        </section>
      </div>
    </>
  );
}

/** Events grouped by discipline, so a 60-event tournament reads as five short lists. */
function EventNavigator({
  id,
  detail,
  current,
}: {
  id: number;
  detail: TournamentDetail;
  current: string | undefined;
}) {
  if (detail.events.length > NAVIGATOR_LIMIT) {
    return (
      <aside className="min-w-0">
        <form
          action={`/tournaments/${id}`}
          method="get"
          className="space-y-2 lg:sticky lg:top-8"
        >
          <label className="block">
            <span className="label-quiet mb-2 block">
              Event ({detail.events.length})
            </span>
            <Select
              name="event"
              defaultValue={current ?? ""}
              className="w-full"
            >
              <option value="">All {detail.events.length} events</option>
              {detail.events.map((e) => (
                <option key={e.name} value={e.name}>
                  {e.name} ({e.matches})
                </option>
              ))}
            </Select>
          </label>
          <button type="submit" className={`${BUTTON_QUIET} w-full`}>
            Show
          </button>
        </form>
      </aside>
    );
  }
  const byDiscipline = groupBy(
    detail.events,
    (e) => (e.discipline && DISCIPLINES[e.discipline]) || "Other events",
  );
  return (
    <aside className="min-w-0">
      <nav aria-label="Events" className="lg:sticky lg:top-8">
        <div className="-mx-4 flex scroll-px-4 gap-2 overflow-x-auto px-4 pb-2 lg:mx-0 lg:block lg:space-y-6 lg:overflow-visible lg:px-0">
          <EventLink
            href={`/tournaments/${id}`}
            current={!current}
            label="All events"
            count={detail.events.reduce((n, e) => n + e.matches, 0)}
          />
          {byDiscipline.map(([discipline, events]) => (
            <div key={discipline} className="contents lg:block">
              <p className="label-quiet hidden pb-1.5 lg:block">{discipline}</p>
              {events.map((e) => (
                <EventLink
                  key={e.name}
                  href={`/tournaments/${id}?event=${encodeURIComponent(e.name)}`}
                  current={current === e.name}
                  label={e.name}
                  count={e.matches}
                />
              ))}
            </div>
          ))}
        </div>
      </nav>
    </aside>
  );
}

function EventLink({
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
        "relative flex h-9 shrink-0 items-center justify-between gap-3 rounded-lg px-3 text-[14px] whitespace-nowrap transition-colors lg:w-full",
        current
          ? "bg-foreground text-background"
          : "text-muted-foreground ring-1 ring-border hover:bg-muted hover:text-foreground lg:ring-0",
      )}
    >
      <span className="truncate">{label}</span>
      <span className="num text-[12px] opacity-75">
        <span className="sr-only">, </span>
        {count}
        <span className="sr-only"> matches</span>
      </span>
    </Link>
  );
}

function groupBy<T>(items: T[], key: (item: T) => string): [string, T[]][] {
  const groups: [string, T[]][] = [];
  for (const item of items) {
    const k = key(item);
    const last = groups.at(-1);
    if (last && last[0] === k) last[1].push(item);
    else groups.push([k, [item]]);
  }
  return groups;
}

/** A scoreboard: two sides, one column per game, the won game bold, a lime dot for the winner. */
function MatchCard({
  match: m,
  showEvent,
}: {
  match: TournamentMatch;
  showEvent: boolean;
}) {
  const note = statusNote(m.status);
  const side1 = m.games.map(([a]) => a);
  const side2 = m.games.map(([, b]) => b);
  return (
    <li className="rounded-[10px] bg-card px-4 py-3.5 ring-1 ring-border [contain-intrinsic-size:auto_104px] [content-visibility:auto] sm:px-5">
      <div className="mb-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-subtle">
        {showEvent ? (
          <span>{formatDate(m.played_on)}</span>
        ) : (
          <>
            <span className="font-medium text-muted-foreground">
              {m.round ?? "Round not recorded"}
            </span>
            <span>{formatDate(m.played_on)}</span>
          </>
        )}
        {note && (
          <span className="rounded-full bg-muted px-2 py-0.5 font-medium text-foreground/80">
            {note}
          </span>
        )}
      </div>
      <div className="space-y-1.5">
        <SideLine
          people={m.side1}
          points={side1}
          opponent={side2}
          won={m.winner_side === 1}
        />
        <SideLine
          people={m.side2}
          points={side2}
          opponent={side1}
          won={m.winner_side === 2}
        />
      </div>
      <p className="sr-only">
        Score: {m.games.length ? formatScore(m.games) : "none recorded"}
      </p>
    </li>
  );
}

function SideLine({
  people,
  points,
  opponent,
  won,
}: {
  people: TournamentMatch["side1"];
  points: number[];
  opponent: number[];
  won: boolean;
}) {
  return (
    <div className="flex items-center gap-3">
      <span
        aria-hidden
        className={cn(
          "size-2 shrink-0 rounded-full",
          won ? "bg-primary ring-1 ring-accent-ink/40" : "bg-transparent",
        )}
      />
      <span
        className={cn(
          "min-w-0 flex-1 truncate text-[15px]",
          won ? "font-semibold text-foreground" : "text-muted-foreground",
        )}
      >
        {people.length === 0
          ? "Not recorded"
          : people.map((p, i) => (
              <span key={`${p.id}-${i}`}>
                {i > 0 && <span className="text-subtle"> / </span>}
                {p.withheld ? (
                  <span className="text-subtle italic">{p.name}</span>
                ) : (
                  <Link
                    href={`/players/${p.id}`}
                    className="underline-offset-[3px] hover:text-foreground hover:underline"
                  >
                    {p.name}
                  </Link>
                )}
              </span>
            ))}
        {won && <span className="sr-only"> (winner)</span>}
      </span>
      <span className="num flex shrink-0 gap-1" aria-hidden>
        {points.map((pt, g) => (
          <span
            key={g}
            className={cn(
              "w-8 text-right text-[15px]",
              pt > opponent[g]
                ? "font-semibold text-foreground"
                : "text-subtle",
            )}
          >
            {pt}
          </span>
        ))}
      </span>
    </div>
  );
}

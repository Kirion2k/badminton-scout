import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import {
  Building2,
  CalendarDays,
  Info,
  ListOrdered,
  MapPin,
} from "lucide-react";

import {
  BUTTON_QUIET,
  EmptyState,
  MetaItem,
  MetaRow,
  Pager,
  Panel,
  PageHeader,
  PillLink,
  RowsSkeleton,
  Select,
  SourceNote,
} from "@/components/bits";
import { Shell } from "@/components/shell";
import { Skeleton } from "@/components/ui/skeleton";
import { type TournamentMatch, api } from "@/lib/api/client";
import {
  DISCIPLINES,
  formatDate,
  formatDateRange,
  formatScore,
  one,
  positiveInt,
  statusNote,
} from "@/lib/format";
import { importFlag } from "@/lib/providers";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Tournament" };

const PAGE_SIZE = 50;
const MAX_CHIPS = 12;

export default function TournamentPage({
  params,
  searchParams,
}: PageProps<"/tournaments/[id]">) {
  return (
    <Shell>
      <Suspense
        fallback={
          <div className="space-y-8">
            <div className="space-y-3">
              <Skeleton className="h-3 w-24 bg-white/[0.04]" />
              <Skeleton className="h-9 w-[28rem] max-w-full bg-white/[0.04]" />
              <Skeleton className="h-4 w-80 max-w-full bg-white/[0.04]" />
            </div>
            <Panel>
              <RowsSkeleton rows={8} />
            </Panel>
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
  const perEvent = new Map(detail.events.map((e) => [e.name, e.matches]));

  return (
    <>
      <PageHeader
        eyebrow="Tournament"
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
        <div className="pt-1">
          <SourceNote>{detail.source}</SourceNote>
        </div>
        {importFlag(detail.import_state) && (
          <p
            role="note"
            className="flex max-w-2xl items-start gap-2.5 rounded-lg bg-white/[0.04] px-3.5 py-2.5 text-[13px] text-muted-foreground"
          >
            <Info aria-hidden className="mt-0.5 size-4 shrink-0 text-subtle" />
            <span>
              <span className="font-medium text-foreground">
                {importFlag(detail.import_state)}.
              </span>{" "}
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

      {detail.events.length <= MAX_CHIPS ? (
        <nav
          aria-label="Events"
          className="-mx-4 mb-6 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:px-0"
        >
          <PillLink href={`/tournaments/${id}`} selected={!known}>
            All events
          </PillLink>
          {detail.events.map((e) => (
            <PillLink
              key={e.name}
              href={`/tournaments/${id}?event=${encodeURIComponent(e.name)}`}
              selected={known && e.name === event}
            >
              {e.name}
              <span className="num text-subtle">
                <span className="sr-only">, </span>
                {e.matches}
                <span className="sr-only"> matches</span>
              </span>
            </PillLink>
          ))}
        </nav>
      ) : (
        // large tournaments list every group as an event: a menu instead of a wall of pills
        <form
          action={`/tournaments/${id}`}
          method="get"
          className="mb-6 flex flex-wrap items-center gap-2"
        >
          <label className="min-w-0 flex-1 sm:flex-none">
            <span className="sr-only">Event ({detail.events.length})</span>
            <Select
              name="event"
              defaultValue={known ? event : ""}
              className="w-full sm:w-80"
            >
              <option value="">All {detail.events.length} events</option>
              {detail.events.map((e) => (
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
      )}

      <Panel>
        <h2 className="sr-only">Matches</h2>
        {matches.items.length === 0 ? (
          <EmptyState
            title={
              page > 1 && matches.total > 0
                ? "No more matches"
                : "No matches in this event"
            }
          />
        ) : (
          <div className="px-2 py-2">
            {groupByEvent(matches.items).map(([name, rows], i) => (
              <section
                key={`${name}-${i}`}
                aria-label={name}
                className="not-first:mt-3"
              >
                <h3 className="flex items-baseline gap-2 px-3 pt-3 pb-1.5">
                  <span className="text-[13px] font-medium">{name}</span>
                  <span className="text-xs text-subtle">
                    {rows[0].discipline
                      ? (DISCIPLINES[rows[0].discipline] ?? rows[0].discipline)
                      : ""}
                    {perEvent.has(name) && (
                      <span className="num">
                        {rows[0].discipline ? " · " : ""}
                        {perEvent.get(name)} matches
                      </span>
                    )}
                  </span>
                </h3>
                <ul>
                  {rows.map((m) => (
                    <MatchRow key={m.id} match={m} />
                  ))}
                </ul>
              </section>
            ))}
          </div>
        )}
        <Pager
          path={`/tournaments/${id}`}
          params={{ event: known ? event : undefined }}
          page={page}
          pageSize={PAGE_SIZE}
          total={matches.total}
        />
      </Panel>
    </>
  );
}

/** Consecutive matches of one event, in the order the API gives them. */
function groupByEvent(items: TournamentMatch[]): [string, TournamentMatch[]][] {
  const groups: [string, TournamentMatch[]][] = [];
  for (const m of items) {
    const last = groups.at(-1);
    if (last && last[0] === m.event) last[1].push(m);
    else groups.push([m.event, [m]]);
  }
  return groups;
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
          "size-1.5 shrink-0 rounded-full",
          won ? "bg-primary" : "bg-transparent",
        )}
      />
      <span
        className={cn(
          "min-w-0 flex-1 truncate text-sm",
          won ? "font-medium text-foreground" : "text-muted-foreground",
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
              "w-7 text-right text-sm",
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

function MatchRow({ match: m }: { match: TournamentMatch }) {
  const note = statusNote(m.status);
  const side1 = m.games.map(([a]) => a);
  const side2 = m.games.map(([, b]) => b);
  return (
    <li className="grid gap-x-6 gap-y-2 rounded-lg px-3 py-3 transition-colors hover:bg-white/[0.025] sm:grid-cols-[8.5rem_minmax(0,1fr)] sm:items-center">
      <div className="flex items-baseline gap-2 sm:block">
        <p className="text-[13px] text-foreground/85">
          {m.round ?? "Round not recorded"}
        </p>
        <p className="num text-xs text-subtle">
          {formatDate(m.played_on)}
          {note && (
            <span className="ml-2 rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[11px] text-muted-foreground sm:mt-1.5 sm:ml-0 sm:block sm:w-fit">
              {note}
            </span>
          )}
        </p>
      </div>
      <div className="min-w-0 space-y-1">
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
        <p className="sr-only">
          Score: {m.games.length ? formatScore(m.games) : "none recorded"}
        </p>
      </div>
    </li>
  );
}

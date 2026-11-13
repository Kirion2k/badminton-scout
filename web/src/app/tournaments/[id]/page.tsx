import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import {
  BUTTON_QUIET,
  EmptyState,
  FedCode,
  Pager,
  RowsSkeleton,
  Select,
} from "@/components/bits";
import { People, ResultRow } from "@/components/scoresheet";
import { Shell } from "@/components/shell";
import { Skeleton } from "@/components/ui/skeleton";
import {
  type TournamentDetail,
  type TournamentMatch,
  api,
} from "@/lib/api/client";
import { DISCIPLINES, formatDateRange, one, positiveInt } from "@/lib/format";
import { FEDERATION, importFlag } from "@/lib/providers";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Tournament" };

const PAGE_SIZE = 60;
const LIST_LIMIT = 30; // more events than this in one view: a menu instead of a list
const ORDER = ["MS", "WS", "MD", "WD", "XD"];

export default function TournamentPage({
  params,
  searchParams,
}: PageProps<"/tournaments/[id]">) {
  return (
    <Shell>
      <Suspense fallback={<PageSkeleton />}>
        <Tournament params={params} searchParams={searchParams} />
      </Suspense>
    </Shell>
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

async function Tournament({
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
  // one event: its rounds are the groups; otherwise each event is a group
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
      <Header detail={detail} />
      <Disciplines id={id} detail={detail} view={view} />
      <div className="mt-6 grid grid-cols-[minmax(0,1fr)] gap-x-12 gap-y-6 lg:grid-cols-[minmax(0,1fr)_17rem]">
        <section
          aria-labelledby="matches-heading"
          className="min-w-0 lg:order-1"
        >
          <div className="sheet-head">
            <h2 id="matches-heading">{title}</h2>
            <span className="num text-[13px] font-normal text-muted-foreground [font-stretch:100%]">
              {matches.total.toLocaleString("en-AU")}{" "}
              {matches.total === 1 ? "match" : "matches"} · winner first
            </span>
          </div>
          {selected && (
            <EventWinner
              event={selected.name}
              rows={matches.items}
              lastPage={page * PAGE_SIZE >= matches.total}
            />
          )}
          {matches.items.length === 0 ? (
            <EmptyState
              title={
                page > 1 && matches.total > 0
                  ? "No more matches"
                  : "No matches in this event"
              }
            >
              {page > 1 && matches.total > 0 && (
                <Link className="underline" href={href(id, view)}>
                  Back to the first page
                </Link>
              )}
            </EmptyState>
          ) : (
            groups.map(([name, rows]) => (
              <section key={name} aria-label={name} className="mt-5">
                <h3 className="sticky top-14 z-10 flex items-baseline gap-3 bg-background/95 px-2 py-1.5 text-[16px] font-bold [font-stretch:80%] backdrop-blur-sm">
                  {name}
                  {!selected && rows[0].discipline && (
                    <span className="text-[12px] font-normal text-subtle [font-stretch:100%]">
                      {DISCIPLINES[rows[0].discipline] ?? rows[0].discipline}
                    </span>
                  )}
                </h3>
                {(selected
                  ? [[name, rows] as const]
                  : groupBy(rows, (m) => m.round ?? "Round not recorded")
                ).map(([round, inRound]) => (
                  <div key={round}>
                    {!selected && (
                      <p className="px-2 pt-2 pb-1 text-[12px] text-subtle">
                        {round}
                      </p>
                    )}
                    <ul className="border-t border-border">
                      {inRound.map((m) => (
                        <ResultRow key={m.id} match={m} />
                      ))}
                    </ul>
                  </div>
                ))}
              </section>
            ))
          )}
          <div className="mt-6">
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
        <Events id={id} detail={detail} view={view} />
      </div>
    </>
  );
}

const FINAL = /^(final|finale|finals|f)$/i;
// a group stage or pool has no final by design: saying one is missing would misdescribe it
const GROUP = /\b(group|pool|poule|gruppe|groep|grupo)\b/i;

/** An event's winner, read from its final when the source publishes one; never inferred. */
function EventWinner({
  event,
  rows,
  lastPage,
}: {
  event: string;
  rows: TournamentMatch[];
  lastPage: boolean;
}) {
  const final = rows.find((m) => FINAL.test((m.round ?? "").trim()));
  if (!final) {
    return lastPage && !GROUP.test(event) ? (
      <p className="px-2 pt-2 text-[13px] text-subtle">
        No final is published for this event, so no winner is named.
      </p>
    ) : null;
  }
  const side =
    final.winner_side === 1
      ? final.side1
      : final.winner_side === 2
        ? final.side2
        : null;
  return (
    <p className="px-2 pt-2 text-[14px]">
      <span className="text-muted-foreground">Winner </span>
      {side ? (
        <span className="font-semibold">
          <People people={side} />
        </span>
      ) : (
        <span className="text-subtle">not decided in the published final</span>
      )}
    </p>
  );
}

/** Identity and facts as two plain lines, then what we hold and where it came from. */
function Header({ detail }: { detail: TournamentDetail }) {
  const fed = FEDERATION[detail.source_id];
  const total = detail.events.reduce((n, e) => n + e.matches, 0);
  const flag = importFlag(detail.import_state);
  return (
    <header className="max-w-4xl">
      <h1 className="display text-[32px] leading-[1.05] text-balance sm:text-[42px]">
        {detail.name ?? "Unnamed tournament"}
      </h1>
      <p className="mt-2 text-[15px]">
        <span className="num font-semibold">
          {formatDateRange(detail.start_date, detail.end_date)}
        </span>
        <span className="text-muted-foreground">
          {" · "}
          {detail.location ?? "Location not recorded"}
          {detail.organiser && ` · ${detail.organiser}`}
        </span>
      </p>
      <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[14px] text-muted-foreground">
        {fed && <FedCode code={fed.code} />}
        <span>{fed?.label ?? detail.source}</span>
        <span aria-hidden>·</span>
        <span className="num">
          {detail.events.length} events · {total.toLocaleString("en-AU")}{" "}
          matches
        </span>
        <span aria-hidden>·</span>
        {flag ? (
          <span className="text-foreground" title={detail.import_state?.note}>
            {flag}: counts cover the matches we hold
          </span>
        ) : (
          <span>every published match imported</span>
        )}
      </p>
      <p className="mt-1 text-[12px] text-subtle">
        Source {detail.source} ·{" "}
        <Link href="/coverage" className="underline">
          About this data
        </Link>
      </p>
    </header>
  );
}

/** The discipline control: plain tabs with the code (MS…) and its full name on hover. */
function Disciplines({
  id,
  detail,
  view,
}: {
  id: number;
  detail: TournamentDetail;
  view: View;
}) {
  const counts = new Map<string, number>();
  for (const e of detail.events)
    if (e.discipline && ORDER.includes(e.discipline))
      counts.set(e.discipline, (counts.get(e.discipline) ?? 0) + e.matches);
  const total = detail.events.reduce((n, e) => n + e.matches, 0);
  const tabs: [string | undefined, string, string, number][] = [
    [undefined, "All", "All disciplines", total],
    ...ORDER.filter((d) => counts.has(d)).map(
      (d) =>
        [d, d, DISCIPLINES[d], counts.get(d)!] as [
          string,
          string,
          string,
          number,
        ],
    ),
  ];
  return (
    <nav aria-label="Disciplines" className="mt-5 overflow-x-auto">
      <ul className="inline-flex min-w-max rounded-md border border-input">
        {tabs.map(([d, code, name, n]) => {
          const current = view.discipline === d;
          return (
            <li key={code} className="border-l border-input first:border-l-0">
              <Link
                href={href(id, { discipline: d })}
                title={name}
                aria-current={current ? "page" : undefined}
                className={cn(
                  "relative flex h-10 items-center gap-1.5 px-3.5 text-[14px] font-semibold transition-colors [font-stretch:85%] hover:no-underline",
                  current ? "bg-form text-white" : "hover:bg-wash",
                )}
              >
                <span aria-hidden>{code}</span>
                <span className="sr-only">{name}</span>
                <span
                  className={cn(
                    "num text-[12px] font-normal",
                    current ? "text-white/80" : "text-subtle",
                  )}
                >
                  <span className="sr-only">, </span>
                  {n}
                  <span className="sr-only"> matches</span>
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/** The events of the open discipline: a side list on desktop, a scrolling row on a phone, the
 * same links either way. Past LIST_LIMIT a menu that works without JavaScript. */
function Events({
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
  const heading = (
    <p className="sheet-head mb-1">
      Events
      <span className="num text-[13px] font-normal text-muted-foreground [font-stretch:100%]">
        {events.length}
      </span>
    </p>
  );
  if (events.length > LIST_LIMIT) {
    return (
      <aside className="min-w-0 lg:order-2">
        <form
          action={`/tournaments/${id}`}
          method="get"
          className="space-y-2 lg:sticky lg:top-20"
        >
          {heading}
          {view.discipline && (
            <input type="hidden" name="discipline" value={view.discipline} />
          )}
          <label className="block">
            <span className="sr-only">Event</span>
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
          <button type="submit" className={`${BUTTON_QUIET} w-full`}>
            Show event
          </button>
        </form>
      </aside>
    );
  }
  const all = events.reduce((n, e) => n + e.matches, 0);
  return (
    <aside className="order-first min-w-0 lg:order-2">
      <nav aria-label="Events" className="lg:sticky lg:top-20">
        <div className="hidden lg:block">{heading}</div>
        <ul className="-mx-4 flex gap-1.5 overflow-x-auto px-4 pb-1 lg:mx-0 lg:block lg:px-0">
          <EventLink
            href={href(id, { discipline: view.discipline })}
            current={!view.event}
            label={
              view.discipline
                ? `All ${DISCIPLINES[view.discipline]?.toLowerCase()}`
                : "All events"
            }
            count={all}
          />
          {events.map((e) => (
            <EventLink
              key={e.name}
              href={href(id, { discipline: view.discipline, event: e.name })}
              current={view.event === e.name}
              label={e.name}
              count={e.matches}
            />
          ))}
        </ul>
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
    <li className="shrink-0 lg:border-b lg:border-border">
      <Link
        href={href}
        aria-current={current ? "page" : undefined}
        className={cn(
          "relative flex h-10 items-center justify-between gap-3 rounded-md px-3 text-[14px] whitespace-nowrap ring-1 ring-border hover:no-underline lg:h-9 lg:rounded-none lg:px-1 lg:ring-0",
          current
            ? "bg-form font-semibold text-white lg:bg-transparent lg:text-form"
            : "hover:bg-wash",
        )}
      >
        <span className="truncate">{label}</span>
        <span
          className={cn(
            "num text-[12px]",
            current ? "text-white/80 lg:text-form" : "text-subtle",
          )}
        >
          <span className="sr-only">, </span>
          {count}
          <span className="sr-only"> matches</span>
        </span>
      </Link>
    </li>
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

function PageSkeleton() {
  return (
    <div className="space-y-4" role="status" aria-busy="true">
      <span className="sr-only">Loading tournament…</span>
      <Skeleton className="h-10 w-[36rem] max-w-full bg-muted" />
      <Skeleton className="h-4 w-80 max-w-full bg-muted" />
      <Skeleton className="h-10 w-72 bg-muted" />
      <RowsSkeleton rows={8} />
    </div>
  );
}

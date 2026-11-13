import { MapPin, Search, SlidersHorizontal } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import {
  BUTTON_QUIET,
  DateBlock,
  EmptyState,
  FedCode,
  LINK,
  Pager,
  RowsSkeleton,
  Select,
} from "@/components/bits";
import { Hero, Shell } from "@/components/shell";
import { Input } from "@/components/ui/input";
import { type Coverage, type TournamentSummary, api } from "@/lib/api/client";
import {
  DISCIPLINES,
  formatDateRange,
  one,
  positiveInt,
  validYear,
} from "@/lib/format";
import { FEDERATION, PROVIDER_LABEL, importFlag } from "@/lib/providers";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Tournaments" };

const PAGE_SIZE = 30;
const SORTS = {
  newest: "Newest first",
  oldest: "Oldest first",
  matches: "Most matches",
};

export default function TournamentsPage({
  searchParams,
}: PageProps<"/tournaments">) {
  return (
    <Shell
      hero={
        <Hero>
          <p className="font-display text-[13px] font-semibold tracking-[0.14em] text-lime uppercase">
            Competitions
          </p>
          <h1 className="display mt-3 text-[44px] leading-[0.95] uppercase sm:text-[64px]">
            Tournaments
          </h1>
          <p className="mt-4 max-w-2xl pb-10 text-[16px] text-on-dark-muted">
            Every tournament with published results, from every connected
            federation. Open one for its match centre.
          </p>
        </Hero>
      }
    >
      <Suspense fallback={<RowsSkeleton rows={10} />}>
        <TournamentList searchParams={searchParams} />
      </Suspense>
    </Shell>
  );
}

type Filters = Record<
  "q" | "location" | "year" | "source" | "discipline" | "sort",
  string | undefined
>;

async function TournamentList({
  searchParams,
}: Pick<PageProps<"/tournaments">, "searchParams">) {
  const sp = await searchParams;
  const text = (key: string) => {
    const v = one(sp[key])?.trim();
    return v && v.length >= 2 && v.length <= 100 ? v : undefined;
  };
  // anything the API would reject is dropped here, so a hand-edited URL shows all, not an error
  const filters: Filters = {
    q: text("q"),
    location: text("location"),
    year: validYear(one(sp.year)),
    source: known(one(sp.source), PROVIDER_LABEL),
    discipline: known(one(sp.discipline), DISCIPLINES),
    sort: known(one(sp.sort), SORTS),
  };
  const page = positiveInt(one(sp.page), 1);
  const [data, coverage] = await Promise.all([
    api.tournaments({
      ...filters,
      limit: PAGE_SIZE,
      offset: (page - 1) * PAGE_SIZE,
    }),
    api.coverage(),
  ]);
  const filtered = Object.entries(filters).some(([k, v]) => k !== "sort" && v);
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-10 lg:grid-cols-[15rem_minmax(0,1fr)] lg:gap-12">
      <FilterRail filters={filters} coverage={coverage} />
      <section aria-labelledby="results-heading" className="min-w-0">
        <div className="flex flex-wrap items-baseline justify-between gap-3 border-b-2 border-foreground pb-2">
          <h2
            id="results-heading"
            className="display text-[22px] uppercase"
            aria-live="polite"
          >
            <span className="num">{data.total.toLocaleString("en-AU")}</span>{" "}
            {filtered
              ? "tournaments match"
              : "tournaments with published results"}
          </h2>
          <span className="flex items-baseline gap-4 text-[13px]">
            <a
              href="#filters"
              className={`${LINK} inline-flex items-center gap-1.5 lg:hidden`}
            >
              <SlidersHorizontal aria-hidden className="size-3.5" />
              Filters
            </a>
            {filtered && (
              <Link
                href="/tournaments"
                className={`${LINK} text-muted-foreground`}
              >
                Clear filters
              </Link>
            )}
          </span>
        </div>
        {data.items.length === 0 ? (
          <EmptyState
            title={
              page > 1 && data.total > 0
                ? "No more tournaments"
                : filtered
                  ? "No tournaments match these filters"
                  : "No tournaments imported yet"
            }
          >
            {page > 1 && data.total > 0 ? (
              <Link className={LINK} href={`/tournaments?${query(filters)}`}>
                Back to the first page
              </Link>
            ) : filtered ? (
              "Try a shorter name, another year, or every federation."
            ) : null}
          </EmptyState>
        ) : (
          <div>
            {byMonth(data.items, filters.sort === "matches").map(
              ([month, items]) => (
                <div key={month}>
                  {month && (
                    <h3 className="label-quiet sticky top-14 z-10 bg-background/95 pt-6 pb-2 backdrop-blur lg:top-0">
                      {month}
                    </h3>
                  )}
                  <ul
                    aria-label={month || "Tournaments"}
                    className="divide-y border-b last:border-b-0"
                  >
                    {items.map((t) => (
                      <TournamentRow key={t.id} tournament={t} />
                    ))}
                  </ul>
                </div>
              ),
            )}
          </div>
        )}
        <Pager
          path="/tournaments"
          params={filters}
          page={page}
          pageSize={PAGE_SIZE}
          total={data.total}
        />
      </section>
    </div>
  );
}

/** Groups consecutive tournaments by start month; a matches sort is not chronological, so flat. */
function byMonth(
  items: TournamentSummary[],
  flat: boolean,
): [string, TournamentSummary[]][] {
  if (flat) return [["", items]];
  const groups: [string, TournamentSummary[]][] = [];
  for (const t of items) {
    const month = t.start_date
      ? new Date(`${t.start_date}T00:00:00Z`).toLocaleDateString("en-AU", {
          month: "long",
          year: "numeric",
          timeZone: "UTC",
        })
      : "Date not recorded";
    const last = groups.at(-1);
    if (last && last[0] === month) last[1].push(t);
    else groups.push([month, [t]]);
  }
  return groups;
}

/** One row: date block, the title leading, then place and federation, completeness and counts.
 * The title's stretched link makes the whole row the hit area but the only tab stop. */
function TournamentRow({ tournament: t }: { tournament: TournamentSummary }) {
  const fed = FEDERATION[t.source_id];
  const flag = importFlag(t.import_state);
  return (
    <li className="group relative grid grid-cols-[3.75rem_minmax(0,1fr)] gap-x-4 gap-y-1 py-4 transition-colors duration-150 hover:bg-card sm:grid-cols-[4.5rem_minmax(0,1fr)_7rem] sm:px-2">
      <DateBlock iso={t.start_date} />
      <div className="min-w-0">
        <Link
          href={`/tournaments/${t.id}`}
          className="text-[16px] leading-snug font-semibold text-pretty after:absolute after:inset-0 group-hover:underline focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-ring"
        >
          {t.name ?? "Unnamed tournament"}
        </Link>
        <p className="mt-1 flex min-w-0 flex-wrap items-center gap-x-2 text-[13px] text-muted-foreground">
          <span className="num">
            {formatDateRange(t.start_date, t.end_date)}
          </span>
          {t.location && (
            <>
              <span aria-hidden className="text-subtle">
                ·
              </span>
              <span className="truncate">{t.location}</span>
            </>
          )}
        </p>
        <p className="mt-1.5 flex flex-wrap items-center gap-2 text-[12px] text-subtle">
          {fed && <FedCode code={fed.code} />}
          <span>{fed?.label ?? t.source_id}</span>
          {flag && (
            <span
              title={t.import_state?.note}
              className="rounded-full bg-muted px-2 py-0.5 font-medium text-foreground/80"
            >
              {flag}
            </span>
          )}
          <span className="num sm:hidden">
            · {t.matches.toLocaleString("en-AU")} matches
          </span>
        </p>
      </div>
      <p className="num hidden text-right sm:block">
        <span className="display text-[28px] leading-none">
          {t.matches.toLocaleString("en-AU")}
        </span>
        <span className="block text-[12px] text-subtle">
          matches · {t.events} {t.events === 1 ? "event" : "events"}
        </span>
      </p>
    </li>
  );
}

function query(filters: Filters, override: Partial<Filters> = {}): string {
  return new URLSearchParams(
    Object.entries({ ...filters, ...override }).filter(
      (e): e is [string, string] => !!e[1],
    ),
  ).toString();
}

/** The rail: federation as a list with live counts, the rest as a small form. Below 1024 px it
 * folds into a disclosure so the results stay first on a phone. */
function FilterRail({
  filters,
  coverage,
}: {
  filters: Filters;
  coverage: Coverage;
}) {
  const played = coverage.providers
    .flatMap((p) => [p.first_played, p.last_played])
    .filter(Boolean)
    .sort();
  const first = Number(played[0]?.slice(0, 4));
  const last = Number(played.at(-1)?.slice(0, 4));
  const years =
    first && last
      ? Array.from({ length: last - first + 1 }, (_, i) => String(last - i))
      : [];
  const federations = coverage.providers
    .filter((p) => p.public_tournaments > 0)
    .sort((a, b) => b.public_tournaments - a.public_tournaments);
  return (
    <aside
      id="filters"
      aria-label="Filters"
      className="order-last min-w-0 lg:order-none"
    >
      <div className="space-y-8 lg:sticky lg:top-8">
        <form
          action="/tournaments"
          method="get"
          role="search"
          aria-label="Filter tournaments"
          className="space-y-3"
        >
          {filters.source && (
            <input type="hidden" name="source" value={filters.source} />
          )}
          <label className="relative block">
            <span className="sr-only">Name</span>
            <Search
              aria-hidden
              className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle"
            />
            <Input
              name="q"
              type="search"
              defaultValue={filters.q}
              minLength={2}
              maxLength={100}
              placeholder="Tournament name…"
              className="pl-9"
            />
          </label>
          <label className="relative block">
            <span className="sr-only">Location or state</span>
            <MapPin
              aria-hidden
              className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle"
            />
            <Input
              name="location"
              defaultValue={filters.location}
              minLength={2}
              maxLength={100}
              placeholder="City, state or country…"
              className="pl-9"
            />
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label>
              <span className="sr-only">Year</span>
              <Select
                name="year"
                defaultValue={filters.year ?? ""}
                className="w-full"
              >
                <option value="">Any year</option>
                {years.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </Select>
            </label>
            <label>
              <span className="sr-only">Discipline</span>
              <Select
                name="discipline"
                defaultValue={filters.discipline ?? ""}
                className="w-full"
              >
                <option value="">All events</option>
                {Object.entries(DISCIPLINES).map(([code, name]) => (
                  <option key={code} value={code}>
                    {name}
                  </option>
                ))}
              </Select>
            </label>
          </div>
          <label className="block">
            <span className="sr-only">Sort</span>
            <Select
              name="sort"
              defaultValue={filters.sort ?? "newest"}
              className="w-full"
            >
              {Object.entries(SORTS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </label>
          <button type="submit" className={`${BUTTON_QUIET} w-full`}>
            Apply
          </button>
        </form>
        <nav aria-label="Federations">
          <p className="label-quiet mb-2">Federation</p>
          <ul className="space-y-0.5 text-[14px]">
            <li>
              <FederationLink
                href={`/tournaments?${query(filters, { source: undefined })}`}
                current={!filters.source}
                label="All federations"
                count={coverage.public_tournaments}
              />
            </li>
            {federations.map((p) => {
              const fed = FEDERATION[p.source_id];
              return (
                <li key={p.source_id}>
                  <FederationLink
                    href={`/tournaments?${query(filters, { source: p.source_id })}`}
                    current={filters.source === p.source_id}
                    label={fed?.country ?? fed?.label ?? p.name}
                    count={p.public_tournaments}
                    code={fed?.code}
                  />
                </li>
              );
            })}
          </ul>
        </nav>
      </div>
    </aside>
  );
}

function FederationLink({
  href,
  current,
  label,
  count,
  code,
}: {
  href: string;
  current: boolean;
  label: string;
  count: number;
  code?: string;
}) {
  return (
    <Link
      href={href}
      aria-current={current ? "page" : undefined}
      className={cn(
        "flex h-9 items-center justify-between gap-3 rounded-lg px-3 transition-colors",
        current
          ? "bg-night font-medium text-on-dark"
          : "text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      <span className="flex min-w-0 items-center gap-2">
        {code && <FedCode code={code} dark={current} />}
        <span className="truncate">{label}</span>
      </span>
      <span className="num text-[12px] opacity-80">
        {count.toLocaleString("en-AU")}
      </span>
    </Link>
  );
}

function known(
  value: string | undefined,
  table: Record<string, string>,
): string | undefined {
  return value && Object.hasOwn(table, value) ? value : undefined;
}

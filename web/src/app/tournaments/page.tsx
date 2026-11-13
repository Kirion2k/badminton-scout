import { MapPin, Search, SlidersHorizontal } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import {
  BUTTON_QUIET,
  EmptyState,
  FedCode,
  LINK,
  Pager,
  RowsSkeleton,
  Select,
} from "@/components/bits";
import { Shell } from "@/components/shell";
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
    <Shell>
      <header className="max-w-3xl pb-6">
        <h1 className="display text-[32px] leading-[1.05] sm:text-[42px]">
          Tournaments
        </h1>
        <p className="mt-2 text-[15px] text-muted-foreground">
          Every tournament with published results, from every connected
          federation. Open one for its results by discipline, event and round.
        </p>
      </header>
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
        <div className="sheet-head flex-wrap">
          <h2 id="results-heading" aria-live="polite">
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
                    <h3 className="sticky top-14 z-10 bg-background/95 pt-5 pb-1.5 text-[14px] font-semibold backdrop-blur-sm">
                      {month}
                    </h3>
                  )}
                  <ul
                    aria-label={month || "Tournaments"}
                    className="border-t border-border"
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

/** One row in reference order: date, the title, then place, federation and completeness, then
 * the match count. The title's stretched link makes the row the hit area but one tab stop. */
function TournamentRow({ tournament: t }: { tournament: TournamentSummary }) {
  const fed = FEDERATION[t.source_id];
  const flag = importFlag(t.import_state);
  return (
    <li className="group relative grid grid-cols-[4.5rem_minmax(0,1fr)_auto] items-baseline gap-x-3 border-b border-border px-1 py-2.5 hover:bg-wash">
      <span className="num text-[13px] text-muted-foreground">
        {formatDateRange(t.start_date, t.end_date)
          .replace(/ \d{4}/g, "")
          .replace(/ – .*/, "")}
      </span>
      <div className="min-w-0">
        <Link
          href={`/tournaments/${t.id}`}
          className="leading-snug font-semibold text-pretty after:absolute after:inset-0 group-hover:underline focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-ring"
        >
          {t.name ?? "Unnamed tournament"}
        </Link>
        <p className="mt-0.5 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-muted-foreground">
          {fed && <FedCode code={fed.code} />}
          <span>{fed?.country ?? fed?.label ?? t.source_id}</span>
          {t.location && <span className="truncate">· {t.location}</span>}
          {flag && (
            <span title={t.import_state?.note} className="text-foreground">
              · {flag}
            </span>
          )}
        </p>
      </div>
      <span className="num text-right text-[13px] text-muted-foreground">
        {t.matches.toLocaleString("en-AU")}
        <span className="hidden sm:inline">
          {" "}
          matches · {t.events} {t.events === 1 ? "event" : "events"}
        </span>
      </span>
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
          <p className="sheet-head mb-1">Federation</p>
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
          ? "bg-form font-medium text-white"
          : "text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      <span className="flex min-w-0 items-center gap-2">
        {code && <FedCode code={code} />}
        <span className="truncate">{label}</span>
      </span>
      <span className="num text-[12px]">{count.toLocaleString("en-AU")}</span>
    </Link>
  );
}

function known(
  value: string | undefined,
  table: Record<string, string>,
): string | undefined {
  return value && Object.hasOwn(table, value) ? value : undefined;
}

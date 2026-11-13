import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { MapPin, Search } from "lucide-react";

import {
  BUTTON_QUIET,
  EmptyState,
  Pager,
  Panel,
  PageHeader,
  RowsSkeleton,
  Select,
} from "@/components/bits";
import { Shell } from "@/components/shell";
import { Input } from "@/components/ui/input";
import { api, type Coverage, type TournamentSummary } from "@/lib/api/client";
import {
  DISCIPLINES,
  formatDateRange,
  one,
  positiveInt,
  validYear,
} from "@/lib/format";
import { PROVIDER_LABEL, importFlag } from "@/lib/providers";

export const metadata: Metadata = { title: "Tournaments" };

const PAGE_SIZE = 25;

export default function TournamentsPage({
  searchParams,
}: PageProps<"/tournaments">) {
  return (
    <Shell>
      <PageHeader title="Tournaments">
        <p className="max-w-2xl text-[15px] text-muted-foreground">
          Every tournament with published results, newest first.
        </p>
      </PageHeader>
      <Suspense
        fallback={
          <Panel>
            <RowsSkeleton rows={10} />
          </Panel>
        }
      >
        <TournamentList searchParams={searchParams} />
      </Suspense>
    </Shell>
  );
}

async function TournamentList({
  searchParams,
}: Pick<PageProps<"/tournaments">, "searchParams">) {
  const sp = await searchParams;
  const text = (key: string) => {
    const v = one(sp[key])?.trim();
    return v && v.length >= 2 && v.length <= 100 ? v : undefined;
  };
  // anything the API would reject is dropped here, so a hand-edited URL shows all, not an error
  const filters = {
    q: text("q"),
    location: text("location"),
    year: validYear(one(sp.year)),
    source: known(one(sp.source), PROVIDER_LABEL),
    discipline: known(one(sp.discipline), DISCIPLINES),
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
  const filtered = Object.values(filters).some(Boolean);
  return (
    <div className="space-y-5">
      <Filters filters={filters} coverage={coverage} />
      <div className="flex items-baseline justify-between gap-4 px-1 text-[13px]">
        <p className="text-muted-foreground" aria-live="polite">
          <span className="num font-medium text-foreground">
            {data.total.toLocaleString("en-AU")}
          </span>{" "}
          {filtered
            ? "tournaments match"
            : "tournaments with published results"}
        </p>
        {filtered && (
          <Link
            href="/tournaments"
            className="text-muted-foreground underline decoration-white/20 underline-offset-[3px] hover:text-foreground"
          >
            Clear filters
          </Link>
        )}
      </div>
      <Panel>
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
              <Link
                className="underline"
                href={`/tournaments?${query(filters)}`}
              >
                Back to the first page
              </Link>
            ) : filtered ? (
              "Try a shorter name, another year, or all providers."
            ) : null}
          </EmptyState>
        ) : (
          <>
            <div
              aria-hidden
              className="label-quiet hidden grid-cols-[minmax(0,1fr)_12rem_6.5rem] gap-6 px-5 pt-4 pb-2 md:grid lg:grid-cols-[minmax(0,1fr)_12rem_10rem_6.5rem]"
            >
              <span>Tournament</span>
              <span>When · where</span>
              <span className="hidden lg:block">Provider</span>
              <span className="text-right">Matches</span>
            </div>
            <ul aria-label="Tournaments" className="px-2 pb-2">
              {data.items.map((t) => (
                <TournamentRow key={t.id} tournament={t} />
              ))}
            </ul>
          </>
        )}
        <Pager
          path="/tournaments"
          params={filters}
          page={page}
          pageSize={PAGE_SIZE}
          total={data.total}
        />
      </Panel>
    </div>
  );
}

/** One scannable row: the title leads, everything else is quieter. The whole row is the link's
 * hit area (a stretched ::after), so only the title is announced and tabbed to. */
function TournamentRow({ tournament: t }: { tournament: TournamentSummary }) {
  const when = formatDateRange(t.start_date, t.end_date);
  const provider = PROVIDER_LABEL[t.source_id] ?? t.source_id;
  const flag = importFlag(t.import_state);
  return (
    <li className="group relative grid gap-x-6 gap-y-1 rounded-lg py-3.5 pr-20 pl-3 md:pr-3 transition-colors hover:bg-white/[0.03] md:grid-cols-[minmax(0,1fr)_12rem_6.5rem] md:items-center lg:grid-cols-[minmax(0,1fr)_12rem_10rem_6.5rem]">
      <div className="min-w-0">
        <Link
          href={`/tournaments/${t.id}`}
          className="text-[15px] leading-snug font-medium text-pretty after:absolute after:inset-0 after:rounded-lg group-hover:text-white focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-ring"
        >
          {t.name ?? "Unnamed tournament"}
        </Link>
        {(t.organiser || flag) && (
          <p className="mt-0.5 flex min-w-0 items-center gap-2 text-[13px] text-muted-foreground">
            {flag && (
              <span
                title={t.import_state?.note}
                className="shrink-0 rounded-md bg-white/[0.06] px-1.5 py-px text-[11px] text-foreground/80"
              >
                {flag}
              </span>
            )}
            <span className="truncate">{t.organiser}</span>
          </p>
        )}
        <p className="num mt-1 text-[13px] text-subtle md:hidden">
          {when}
          {t.location ? ` · ${t.location}` : ""} · {provider}
        </p>
      </div>
      <div className="hidden min-w-0 text-[13px] md:block">
        <p className="num whitespace-nowrap text-foreground/90">{when}</p>
        <p className="truncate text-muted-foreground">
          {t.location ?? "Location not recorded"}
        </p>
      </div>
      <p className="hidden truncate text-[13px] text-muted-foreground lg:block">
        {provider}
      </p>
      <p className="num absolute top-3.5 right-3 text-right md:static">
        <span className="text-[15px] font-medium">
          {t.matches.toLocaleString("en-AU")}
        </span>
        <span className="block text-xs text-subtle">
          {t.events} {t.events === 1 ? "event" : "events"}
        </span>
      </p>
    </li>
  );
}

type Filters = Record<
  "q" | "location" | "year" | "source" | "discipline",
  string | undefined
>;

function query(filters: Filters): string {
  return new URLSearchParams(
    Object.entries(filters).filter((e): e is [string, string] => !!e[1]),
  ).toString();
}

function Filters({
  filters,
  coverage,
}: {
  filters: Filters;
  coverage: Coverage;
}) {
  // only years and providers that actually have public results are offered
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
  const providers = coverage.providers.filter((p) => p.public_tournaments > 0);
  return (
    <form
      action="/tournaments"
      method="get"
      role="search"
      aria-label="Filter tournaments"
      className="grid grid-cols-2 gap-2 rounded-xl bg-card p-2 ring-1 ring-white/[0.04] sm:flex sm:flex-wrap sm:items-center"
    >
      <label className="relative col-span-2 sm:min-w-56 sm:flex-[2]">
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
          placeholder="Tournament name"
          className="pl-9"
        />
      </label>
      <label className="relative col-span-2 sm:min-w-40 sm:flex-1">
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
          placeholder="Location or state"
          className="pl-9"
        />
      </label>
      <label>
        <span className="sr-only">Year</span>
        <Select
          name="year"
          defaultValue={filters.year ?? ""}
          className="w-full sm:w-28"
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
        <span className="sr-only">Provider</span>
        <Select
          name="source"
          defaultValue={filters.source ?? ""}
          className="w-full sm:w-48"
        >
          <option value="">All providers</option>
          {providers.map((p) => (
            <option key={p.source_id} value={p.source_id}>
              {PROVIDER_LABEL[p.source_id] ?? p.name}
            </option>
          ))}
        </Select>
      </label>
      <label className="col-span-2 sm:col-span-1">
        <span className="sr-only">Discipline</span>
        <Select
          name="discipline"
          defaultValue={filters.discipline ?? ""}
          className="w-full sm:w-44"
        >
          <option value="">All disciplines</option>
          {Object.entries(DISCIPLINES).map(([code, name]) => (
            <option key={code} value={code}>
              {name}
            </option>
          ))}
        </Select>
      </label>
      <button
        type="submit"
        className={`${BUTTON_QUIET} col-span-2 sm:col-span-1`}
      >
        Apply
      </button>
    </form>
  );
}

function known(
  value: string | undefined,
  table: Record<string, string>,
): string | undefined {
  return value && Object.hasOwn(table, value) ? value : undefined;
}

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";

import {
  DateBlock,
  EmptyState,
  LINK,
  RowsSkeleton,
  Section,
} from "@/components/bits";
import { SearchForm } from "@/components/search-form";
import { Shell } from "@/components/shell";
import { Skeleton } from "@/components/ui/skeleton";
import { type Coverage, api } from "@/lib/api/client";
import { formatDate, formatMoment, one } from "@/lib/format";
import { FEDERATION, importFlag } from "@/lib/providers";

export default function DiscoverPage({ searchParams }: PageProps<"/">) {
  return (
    <Shell showSearch={false}>
      <section className="pb-14 lg:pb-20">
        <p className="label-quiet">Badminton results, worldwide</p>
        <Suspense
          fallback={
            <Skeleton className="mt-4 h-24 w-full max-w-3xl bg-muted" />
          }
        >
          <Headline />
        </Suspense>
        <div className="mt-8 max-w-2xl">
          <h2 className="sr-only">Find a player</h2>
          <Suspense fallback={<SearchForm />}>
            <SearchBox searchParams={searchParams} />
          </Suspense>
          <p className="mt-3 text-[13px] text-muted-foreground">
            Search by name. Small spelling mistakes are fine.
          </p>
        </div>
      </section>
      <Suspense fallback={<RowsSkeleton rows={6} />}>
        <Results searchParams={searchParams} />
      </Suspense>
    </Shell>
  );
}

/** The real totals, said as a sentence: the first thing anyone should learn about the data. */
async function Headline() {
  const c = await api.coverage();
  const sources = c.providers.filter((p) => p.public_tournaments > 0).length;
  const n = (v: number) => v.toLocaleString("en-AU");
  return (
    <h1 className="display mt-4 max-w-4xl text-[34px] leading-[1.08] font-semibold text-balance sm:text-[52px]">
      <span className="num">{n(c.public_matches)}</span> matches from{" "}
      <span className="num">{n(c.public_tournaments)}</span> tournaments, across{" "}
      {sources} {sources === 1 ? "source" : "sources"}, each traced to where it
      was published.
    </h1>
  );
}

async function SearchBox({
  searchParams,
}: Pick<PageProps<"/">, "searchParams">) {
  const q = one((await searchParams).q);
  return <SearchForm defaultValue={q} />;
}

async function Results({ searchParams }: Pick<PageProps<"/">, "searchParams">) {
  const q = one((await searchParams).q)?.trim();
  if (q && q.length >= 2) return <PlayerResults q={q} />;
  return <Overview />;
}

async function PlayerResults({ q }: { q: string }) {
  const hits = await api.searchPlayers(q);
  return (
    <Section
      title="Players"
      action={
        <span className="text-muted-foreground">
          {hits.length} {hits.length === 1 ? "match" : "matches"} for “{q}”
        </span>
      }
    >
      {hits.length === 0 ? (
        <EmptyState title={`No players match “${q}”`}>
          Try a surname alone, or see{" "}
          <Link className={LINK} href="/coverage">
            which competitions are included
          </Link>
          .
        </EmptyState>
      ) : (
        <ul className="divide-y">
          {hits.map((hit) => (
            <li key={hit.id}>
              <Link
                href={`/players/${hit.id}`}
                className="group flex items-center justify-between gap-4 py-4 transition-colors hover:bg-muted/60 sm:px-2"
              >
                <span className="display text-[20px] font-semibold group-hover:underline">
                  {hit.name}
                </span>
                <span className="num shrink-0 text-[13px] text-muted-foreground">
                  {hit.matches} {hit.matches === 1 ? "match" : "matches"}
                  {hit.last_played
                    ? ` · last ${formatDate(hit.last_played)}`
                    : ""}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

async function Overview() {
  const [recent, coverage] = await Promise.all([
    api.tournaments({ limit: 8 }),
    api.coverage(),
  ]);
  return (
    <div className="grid gap-14 xl:grid-cols-[minmax(0,1fr)_22rem] xl:gap-16">
      <Section
        title="Latest results"
        action={
          <Link
            href="/tournaments"
            className={`${LINK} inline-flex items-center gap-1`}
          >
            All {coverage.public_tournaments.toLocaleString("en-AU")}{" "}
            tournaments
            <ArrowRight aria-hidden className="size-3.5" />
          </Link>
        }
      >
        {recent.items.length === 0 ? (
          <EmptyState title="No tournaments with published results yet" />
        ) : (
          <ol className="divide-y">
            {recent.items.map((t) => {
              const flag = importFlag(t.import_state);
              const fed = FEDERATION[t.source_id];
              return (
                <li
                  key={t.id}
                  className="group relative grid grid-cols-[4.5rem_minmax(0,1fr)] gap-4 py-4"
                >
                  <DateBlock iso={t.start_date} />
                  <div className="min-w-0">
                    <Link
                      href={`/tournaments/${t.id}`}
                      className="text-[16px] leading-snug font-medium text-pretty after:absolute after:inset-0 group-hover:underline focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-ring"
                    >
                      {t.name ?? "Unnamed tournament"}
                    </Link>
                    <p className="mt-1 truncate text-[13px] text-muted-foreground">
                      {[t.location, fed?.country ?? fed?.label]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                    <p className="num mt-1 text-[13px] text-subtle">
                      {t.matches.toLocaleString("en-AU")} matches · {t.events}{" "}
                      events
                      {flag ? ` · ${flag}` : ""}
                    </p>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </Section>
      <Federations coverage={coverage} />
    </div>
  );
}

/** Where the data comes from, as an index: real public counts, never "full national coverage". */
function Federations({ coverage }: { coverage: Coverage }) {
  const live = coverage.providers
    .filter((p) => p.public_tournaments > 0)
    .sort((a, b) => b.public_matches - a.public_matches);
  return (
    <Section title="Federations">
      <ul className="divide-y">
        {live.map((p) => {
          const fed = FEDERATION[p.source_id];
          return (
            <li key={p.source_id}>
              <Link
                href={`/tournaments?source=${p.source_id}`}
                className="group flex items-baseline justify-between gap-4 py-3"
              >
                <span className="min-w-0">
                  <span className="block truncate font-medium group-hover:underline">
                    {fed?.country ?? fed?.label ?? p.name}
                  </span>
                  <span className="block truncate text-[12px] text-subtle">
                    {fed?.country
                      ? fed.label
                      : "Tournaments from many countries"}
                  </span>
                </span>
                <span className="num shrink-0 text-right text-[13px] text-muted-foreground">
                  {p.public_tournaments} tournaments
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
      <p className="mt-4 text-[13px] text-muted-foreground">
        Updated{" "}
        {formatMoment(coverage.last_sync_at) ?? "when the first sync runs"}.{" "}
        <Link href="/coverage" className={LINK}>
          Sources and gaps
        </Link>
      </p>
    </Section>
  );
}

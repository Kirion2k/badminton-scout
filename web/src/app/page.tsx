import Link from "next/link";
import { Suspense } from "react";

import { EmptyState, Fact, Panel, RowsSkeleton } from "@/components/bits";
import { SearchForm } from "@/components/search-form";
import { Shell } from "@/components/shell";
import { api } from "@/lib/api/client";
import {
  formatDate,
  formatDateRange,
  formatMoment,
  formatNextSync,
  formatRetrieved,
  one,
} from "@/lib/format";

export default function DiscoverPage({ searchParams }: PageProps<"/">) {
  return (
    <Shell showSearch={false}>
      <section className="mx-auto max-w-2xl pt-6 pb-10 text-center">
        <h1 className="text-[28px] leading-tight font-semibold tracking-tight">
          Find a player
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Search match records by name. Small spelling mistakes are fine.
        </p>
        <div className="mt-6">
          <Suspense fallback={<SearchForm autoFocus />}>
            <SearchBox searchParams={searchParams} />
          </Suspense>
        </div>
      </section>
      <Suspense fallback={<RowsSkeleton rows={4} />}>
        <Results searchParams={searchParams} />
      </Suspense>
    </Shell>
  );
}

async function SearchBox({
  searchParams,
}: Pick<PageProps<"/">, "searchParams">) {
  const q = one((await searchParams).q);
  return <SearchForm defaultValue={q} autoFocus />;
}

async function Results({ searchParams }: Pick<PageProps<"/">, "searchParams">) {
  const q = one((await searchParams).q)?.trim();
  if (q && q.length >= 2) return <PlayerResults q={q} />;
  return <Overview />;
}

async function PlayerResults({ q }: { q: string }) {
  const hits = await api.searchPlayers(q);
  if (hits.length === 0) {
    return (
      <div className="mx-auto max-w-2xl">
        <EmptyState title={`No players match “${q}”`}>
          Try a surname alone, or check the{" "}
          <Link className="underline" href="/coverage">
            coverage
          </Link>{" "}
          page for which competitions are included.
        </EmptyState>
      </div>
    );
  }
  return (
    <div className="mx-auto max-w-2xl">
      <p className="mb-2 text-xs text-muted-foreground">
        {hits.length} {hits.length === 1 ? "player" : "players"} · best match
        first
      </p>
      <Panel>
        <ul className="divide-y">
          {hits.map((hit) => (
            <li key={hit.id}>
              <Link
                href={`/players/${hit.id}`}
                className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-muted"
              >
                <span className="font-medium">{hit.name}</span>
                <span className="num text-xs text-muted-foreground">
                  {hit.matches} {hit.matches === 1 ? "match" : "matches"}
                  {hit.last_played
                    ? ` · last ${formatDate(hit.last_played)}`
                    : ""}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}

async function Overview() {
  const [recent, coverage] = await Promise.all([
    api.tournaments({ limit: 6 }),
    api.coverage(),
  ]);
  const importing = coverage.providers.filter(
    (p) => p.status === "connected_importing",
  );
  const latest = importing
    .map((p) => p.last_played)
    .filter(Boolean)
    .sort()
    .at(-1);
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Panel title="Recently played tournaments" className="lg:col-span-2">
        {recent.items.length === 0 ? (
          <div className="p-4">
            <EmptyState title="No tournaments with published results yet" />
          </div>
        ) : (
          <ul className="divide-y">
            {recent.items.map((t) => (
              <li key={t.id}>
                <Link
                  href={`/tournaments/${t.id}`}
                  className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-muted"
                >
                  <span className="min-w-0">
                    <span className="block truncate font-medium">
                      {t.name ?? "Unnamed tournament"}
                    </span>
                    <span className="block text-xs text-muted-foreground">
                      {formatDateRange(t.start_date, t.end_date)}
                      {t.location ? ` · ${t.location}` : ""}
                    </span>
                  </span>
                  <span className="num shrink-0 text-xs text-muted-foreground">
                    {t.matches} matches
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
        <div className="border-t px-4 py-3 text-sm">
          <Link href="/tournaments" className="text-primary hover:underline">
            Browse all {coverage.public_tournaments.toLocaleString("en-AU")}{" "}
            tournaments with results →
          </Link>
        </div>
      </Panel>
      <Panel title="What’s in the data">
        <dl className="grid grid-cols-2 gap-4 p-4 text-sm">
          <Fact term="Tournaments" className="col-span-2">
            <span className="num text-xl font-semibold">
              {coverage.public_tournaments.toLocaleString("en-AU")}
            </span>{" "}
            <span className="text-muted-foreground">
              with published results
            </span>
          </Fact>
          <Fact term="Matches">
            <span className="num text-xl font-semibold">
              {coverage.public_matches.toLocaleString("en-AU")}
            </span>
          </Fact>
          <Fact term="Players">
            <span className="num text-xl font-semibold">
              {coverage.public_players.toLocaleString("en-AU")}
            </span>
          </Fact>
          <Fact term="Importing from" className="col-span-2">
            {importing.map((p) => p.name).join(", ") || "No source yet"}
          </Fact>
          <Fact term="Latest match" className="col-span-2">
            {formatDate(latest)}
          </Fact>
          <Fact term="Last update" className="col-span-2">
            {formatMoment(coverage.last_sync_at) ??
              formatRetrieved(coverage.last_retrieved_at)}
            {coverage.next_sync_at && (
              <span className="block text-xs text-muted-foreground">
                next: {formatNextSync(coverage.next_sync_at)}
              </span>
            )}
          </Fact>
        </dl>
        <div className="space-y-2 px-4 pb-4 text-sm">
          <p className="text-xs text-muted-foreground">
            The historical database is growing: more tournaments are imported
            each day within each provider’s request allowance.
          </p>
          <Link href="/coverage" className="block text-primary hover:underline">
            Sources, gaps and pending providers →
          </Link>
        </div>
      </Panel>
    </div>
  );
}

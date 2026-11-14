import Link from "next/link";
import { Suspense } from "react";

import {
  EmptyState,
  FedCode,
  LINK,
  RowsSkeleton,
  Section,
  SourceNote,
} from "@/components/bits";
import { ResultRow } from "@/components/scoresheet";
import { SearchForm } from "@/components/search-form";
import { Shell } from "@/components/shell";
import { type TournamentSummary, api } from "@/lib/api/client";
import { formatDate, formatMoment, one } from "@/lib/format";
import { FEDERATION, importFlag } from "@/lib/providers";

export default function DiscoverPage({ searchParams }: PageProps<"/">) {
  return (
    <Shell showSearch={false}>
      <section className="max-w-3xl">
        <h1 className="display text-[30px] leading-[1.05] text-balance sm:text-[40px]">
          Look up any badminton player’s results, across federations.
        </h1>
        <div className="mt-5">
          <h2 className="sr-only">Find a player</h2>
          <Suspense fallback={<SearchForm />}>
            <SearchBox searchParams={searchParams} />
          </Suspense>
          <Suspense fallback={<p className="mt-2 h-5" />}>
            <Totals />
          </Suspense>
        </div>
      </section>
      <div className="mt-10">
        <Suspense fallback={<RowsSkeleton rows={6} />}>
          <Results searchParams={searchParams} />
        </Suspense>
      </div>
    </Shell>
  );
}

/** The real totals, said once under the search: context, not a headline. */
async function Totals() {
  const c = await api.coverage();
  const sources = c.providers.filter((p) => p.public_tournaments > 0).length;
  const n = (v: number) => v.toLocaleString("en-AU");
  return (
    <p className="num mt-2 text-[13px] text-muted-foreground">
      {n(c.public_players)} players, {n(c.public_matches)} matches from{" "}
      {n(c.public_tournaments)} tournaments and {sources} sources. Small
      spelling mistakes in a name are fine.
    </p>
  );
}

async function SearchBox({
  searchParams,
}: Pick<PageProps<"/">, "searchParams">) {
  const q = one((await searchParams).q);
  return <SearchForm defaultValue={q} autoFocus={!q} />;
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
        <span>
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
        <ul className="max-w-3xl">
          {hits.map((hit) => (
            <li key={hit.id} className="border-b border-border">
              <Link
                href={`/players/${hit.id}`}
                className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-4 px-1 py-2.5 hover:bg-wash hover:no-underline"
              >
                <span className="truncate text-[16px] font-semibold">
                  {hit.name}
                </span>
                <span className="num text-[13px] text-muted-foreground">
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

/** Late-stage rounds first: a final says "tournament" faster than a group match. */
const LATE_ROUND = /final|finale|halbfinale|demi|semi|kf|hf|^f$|^sf$|^qf$/i;

async function Overview() {
  const recent = await api.tournaments({ limit: 12 });
  const featured = recent.items.find(
    (t) => t.import_state?.status === "complete" && t.matches > 0,
  );
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-x-12 gap-y-10 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <div className="min-w-0">
        {featured && <LatestResults tournament={featured} />}
      </div>
      <Suspense fallback={<RowsSkeleton rows={6} />}>
        <Federations />
      </Suspense>
      <Section
        className="lg:col-span-2"
        title="Recently played"
        action={
          <Link href="/tournaments" className="underline">
            All {recent.total.toLocaleString("en-AU")} tournaments
          </Link>
        }
      >
        {recent.items.length === 0 ? (
          <EmptyState title="No tournaments with published results yet" />
        ) : (
          <ul>
            {recent.items.map((t) => (
              <TournamentLine key={t.id} t={t} />
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}

/** Sources with public tournaments, streamed on their own: coverage is the slowest call. */
async function Federations() {
  const coverage = await api.coverage();
  const live = coverage.providers
    .filter((p) => p.public_tournaments > 0)
    .sort((a, b) => b.public_matches - a.public_matches);
  return (
    <Section title="Federations">
      <ul className="text-[14px]">
        {live.map((p) => {
          const fed = FEDERATION[p.source_id];
          return (
            <li key={p.source_id} className="border-b border-border">
              <Link
                href={`/tournaments?source=${p.source_id}`}
                className="flex items-center gap-2.5 py-2 hover:no-underline"
              >
                <FedCode code={fed?.code ?? "—"} />
                <span className="min-w-0 flex-1 truncate hover:underline">
                  {fed?.country ?? fed?.label ?? p.name}
                </span>
                <span className="num text-muted-foreground">
                  {p.public_tournaments}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
      <p className="mt-2 text-[12px] text-subtle">
        Tournaments per source. Updated{" "}
        {formatMoment(coverage.last_sync_at) ?? "when the first sync runs"}.{" "}
        <Link href="/coverage" className="underline">
          Sources and gaps
        </Link>
      </p>
    </Section>
  );
}

/** Real results from the newest fully imported tournament, its late rounds first. */
async function LatestResults({
  tournament: t,
}: {
  tournament: TournamentSummary;
}) {
  // the API lists oldest first: count, then read only the newest 40 (the final day's rounds)
  const { total } = await api.tournamentMatches(t.id, { limit: 1 });
  const page = await api.tournamentMatches(t.id, {
    limit: 40,
    offset: Math.max(0, total - 40),
  });
  const decided = page.items.filter((m) => m.winner_side !== null);
  const late = decided.filter((m) => LATE_ROUND.test(m.round ?? ""));
  const shown = (late.length >= 3 ? late : decided).slice(-6).reverse();
  if (shown.length === 0) return null;
  return (
    <Section
      title="Latest results"
      action={
        <Link href={`/tournaments/${t.id}`} className="underline">
          {t.name ?? "Tournament"}
        </Link>
      }
    >
      <ul>
        {shown.map((m) => (
          <ResultRow
            key={m.id}
            match={m}
            context={[m.event, m.round].filter(Boolean).join(" · ")}
          />
        ))}
      </ul>
      <div className="mt-2">
        <SourceNote>{t.source}</SourceNote>
      </div>
    </Section>
  );
}

function TournamentLine({ t }: { t: TournamentSummary }) {
  const fed = FEDERATION[t.source_id];
  const flag = importFlag(t.import_state);
  return (
    <li className="border-b border-border">
      <Link
        href={`/tournaments/${t.id}`}
        className="grid grid-cols-[4.5rem_minmax(0,1fr)_auto] items-baseline gap-3 px-1 py-2 hover:bg-wash hover:no-underline"
      >
        <span className="num text-[13px] text-muted-foreground">
          {formatDate(t.start_date).replace(/ \d{4}$/, "")}
        </span>
        <span className="min-w-0">
          <span className="block truncate font-semibold">
            {t.name ?? "Unnamed tournament"}
          </span>
          <span className="flex items-center gap-2 text-[12px] text-subtle">
            {fed && (
              <FedCode code={fed.code} label={fed.country ?? fed.label} />
            )}
            <span className="truncate">{t.location}</span>
            {flag && <span className="text-foreground">· {flag}</span>}
          </span>
        </span>
        <span className="num text-[13px] text-muted-foreground">
          {t.matches.toLocaleString("en-AU")}
        </span>
      </Link>
    </li>
  );
}

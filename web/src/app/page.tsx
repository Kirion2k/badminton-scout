import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";

import {
  DateBlock,
  EmptyState,
  FedCode,
  LINK,
  Monogram,
  RowsSkeleton,
  Section,
} from "@/components/bits";
import { Scoreboard } from "@/components/scoreboard";
import { SearchForm } from "@/components/search-form";
import { Hero, Shell } from "@/components/shell";
import { type Coverage, type TournamentSummary, api } from "@/lib/api/client";
import { formatDate, formatMoment, one } from "@/lib/format";
import { FEDERATION, importFlag } from "@/lib/providers";

export default function DiscoverPage({ searchParams }: PageProps<"/">) {
  return (
    <Shell
      showSearch={false}
      hero={
        <Hero>
          <p className="font-display text-[13px] font-semibold tracking-[0.14em] text-lime uppercase">
            Badminton results, worldwide
          </p>
          <h1 className="display mt-3 max-w-3xl text-[44px] leading-[0.95] uppercase sm:text-[68px]">
            Find any player.
            <br />
            Read every result.
          </h1>
          <div className="mt-8 max-w-2xl">
            <h2 className="sr-only">Find a player</h2>
            <Suspense fallback={<SearchForm />}>
              <SearchBox searchParams={searchParams} />
            </Suspense>
            <p className="mt-3 text-[13px] text-on-dark-muted">
              Search by name. Small spelling mistakes are fine.
            </p>
          </div>
          <Suspense fallback={<div className="h-28" />}>
            <Totals />
          </Suspense>
        </Hero>
      }
    >
      <Suspense fallback={<RowsSkeleton rows={6} />}>
        <Results searchParams={searchParams} />
      </Suspense>
    </Shell>
  );
}

/** The real totals as a quiet strip at the foot of the hero: they support, not headline. */
async function Totals() {
  const c = await api.coverage();
  const federations = c.providers.filter((p) => p.public_tournaments > 0);
  const facts: [number, string][] = [
    [c.public_matches, "Matches"],
    [c.public_tournaments, "Tournaments"],
    [c.public_players, "Players"],
    [federations.length, "Sources"],
  ];
  return (
    <dl className="mt-10 grid grid-cols-2 gap-x-8 gap-y-5 border-t border-white/12 py-6 sm:grid-cols-4">
      {facts.map(([value, label]) => (
        <div key={label} className="flex flex-col-reverse">
          <dt className="mt-1 font-display text-[12px] font-semibold tracking-[0.12em] text-on-dark-muted uppercase">
            {label}
          </dt>
          <dd className="reveal display num text-[32px] leading-none">
            {value.toLocaleString("en-AU")}
          </dd>
        </div>
      ))}
    </dl>
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
        <ul className="grid grid-cols-[minmax(0,1fr)] gap-2.5 pt-5 md:grid-cols-2">
          {hits.map((hit) => (
            <li key={hit.id}>
              <Link
                href={`/players/${hit.id}`}
                className="group flex items-center gap-4 rounded-[10px] bg-card p-3 ring-1 ring-border transition-shadow duration-150 hover:shadow-[0_6px_20px_-12px_rgb(11_21_38/0.35)] hover:ring-foreground/20"
              >
                <Monogram name={hit.name} className="size-11 text-[17px]" />
                <span className="min-w-0">
                  <span className="block truncate text-[16px] font-semibold group-hover:underline">
                    {hit.name}
                  </span>
                  <span className="num block truncate text-[13px] text-muted-foreground">
                    {hit.matches} {hit.matches === 1 ? "match" : "matches"}
                    {hit.last_played
                      ? ` · last ${formatDate(hit.last_played)}`
                      : ""}
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

/** Late-stage rounds first: a finals scoreboard says "tournament" faster than a group match. */
const LATE_ROUND = /final|finale|halbfinale|demi|semi|kf|hf|^f$|^sf$|^qf$/i;

async function Overview() {
  const [recent, coverage] = await Promise.all([
    api.tournaments({ limit: 12 }),
    api.coverage(),
  ]);
  const featured = recent.items.find(
    (t) => t.import_state?.status === "complete" && t.matches > 0,
  );
  return (
    <div className="space-y-16">
      {featured && <FeaturedResults tournament={featured} />}
      <Section
        title="Latest competitions"
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
          <ol className="grid grid-cols-[minmax(0,1fr)] gap-2.5 pt-5 md:grid-cols-2 xl:grid-cols-3">
            {recent.items.slice(0, 9).map((t) => (
              <CompetitionCard key={t.id} tournament={t} />
            ))}
          </ol>
        )}
      </Section>
      <Federations coverage={coverage} />
    </div>
  );
}

/** Real scoreboards from the newest fully imported tournament, late rounds first. */
async function FeaturedResults({
  tournament: t,
}: {
  tournament: TournamentSummary;
}) {
  const page = await api.tournamentMatches(t.id, { limit: 200 });
  const decided = page.items.filter((m) => m.winner_side !== null);
  const late = decided.filter((m) => LATE_ROUND.test(m.round ?? ""));
  const shown = (late.length >= 2 ? late : decided).slice(-4).reverse();
  if (shown.length === 0) return null;
  const fed = FEDERATION[t.source_id];
  return (
    <Section
      title="Latest results"
      action={
        <Link
          href={`/tournaments/${t.id}`}
          className={`${LINK} inline-flex items-center gap-1`}
        >
          Open match centre
          <ArrowRight aria-hidden className="size-3.5" />
        </Link>
      }
    >
      <p className="flex flex-wrap items-center gap-2 pt-4 text-[14px] text-muted-foreground">
        {fed && <FedCode code={fed.code} label={fed.country ?? fed.label} />}
        <Link
          href={`/tournaments/${t.id}`}
          className="font-semibold text-foreground hover:underline"
        >
          {t.name ?? "Unnamed tournament"}
        </Link>
        <span className="num">· {formatDate(t.start_date)}</span>
      </p>
      <ul className="grid grid-cols-[minmax(0,1fr)] gap-2.5 pt-4 lg:grid-cols-2">
        {shown.map((m) => (
          <Scoreboard key={m.id} match={m} showEvent />
        ))}
      </ul>
    </Section>
  );
}

function CompetitionCard({ tournament: t }: { tournament: TournamentSummary }) {
  const flag = importFlag(t.import_state);
  const fed = FEDERATION[t.source_id];
  return (
    <li className="group relative grid grid-cols-[3.5rem_minmax(0,1fr)] gap-4 rounded-[10px] bg-card p-4 ring-1 ring-border transition-shadow duration-150 hover:shadow-[0_6px_20px_-12px_rgb(11_21_38/0.35)] hover:ring-foreground/20">
      <DateBlock iso={t.start_date} />
      <div className="min-w-0">
        <Link
          href={`/tournaments/${t.id}`}
          className="line-clamp-2 text-[16px] leading-snug font-semibold text-pretty after:absolute after:inset-0 group-hover:underline focus-visible:outline-none focus-visible:after:rounded-[10px] focus-visible:after:outline-2 focus-visible:after:outline-ring"
        >
          {t.name ?? "Unnamed tournament"}
        </Link>
        <p className="mt-1.5 flex min-w-0 items-center gap-2 text-[13px] text-muted-foreground">
          {fed && <FedCode code={fed.code} label={fed.country ?? fed.label} />}
          <span className="truncate">{t.location ?? fed?.label}</span>
        </p>
        <p className="label-quiet num mt-2 text-[11px]">
          {t.matches.toLocaleString("en-AU")} matches · {t.events} events
          {flag ? ` · ${flag}` : ""}
        </p>
      </div>
    </li>
  );
}

/** Where the data comes from: a federation board with real public counts, never "full coverage". */
function Federations({ coverage }: { coverage: Coverage }) {
  const live = coverage.providers
    .filter((p) => p.public_tournaments > 0)
    .sort((a, b) => b.public_matches - a.public_matches);
  return (
    <Section
      title="Federations"
      action={
        <span className="text-muted-foreground">
          Updated{" "}
          {formatMoment(coverage.last_sync_at) ?? "when the first sync runs"}
        </span>
      }
    >
      <ul className="grid grid-cols-[minmax(0,1fr)] gap-2.5 pt-5 sm:grid-cols-2 lg:grid-cols-3">
        {live.map((p) => {
          const fed = FEDERATION[p.source_id];
          return (
            <li key={p.source_id}>
              <Link
                href={`/tournaments?source=${p.source_id}`}
                className="group flex items-center gap-3 rounded-[10px] bg-card p-3.5 ring-1 ring-border transition-colors duration-150 hover:ring-foreground/30"
              >
                <FedCode code={fed?.code ?? "—"} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-semibold group-hover:underline">
                    {fed?.country ?? fed?.label ?? p.name}
                  </span>
                  <span className="block truncate text-[12px] text-subtle">
                    {fed?.country
                      ? fed.label
                      : "Tournaments from many countries"}
                  </span>
                </span>
                <span className="num shrink-0 text-right">
                  <span className="display block text-[22px] leading-none">
                    {p.public_tournaments}
                  </span>
                  <span className="label-quiet text-[10px]">tournaments</span>
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
      <p className="mt-4 text-[13px] text-muted-foreground">
        <Link href="/coverage" className={LINK}>
          Sources, freshness and gaps
        </Link>
      </p>
    </Section>
  );
}

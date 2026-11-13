import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { AutoSubmit } from "@/components/auto-submit";
import {
  BUTTON_QUIET,
  EmptyState,
  FormStrip,
  LINK,
  Pager,
  ResultBadge,
  RowsSkeleton,
  Section,
  Select,
} from "@/components/bits";
import { GameSheet, People, StatusNote } from "@/components/scoresheet";
import { Shell } from "@/components/shell";
import { Skeleton } from "@/components/ui/skeleton";
import { type PlayerMatch, type PlayerProfile, api } from "@/lib/api/client";
import {
  DISCIPLINES,
  formatDate,
  formatRetrieved,
  one,
  positiveInt,
  statusNote,
  validYear,
} from "@/lib/format";

// A fixed title: player names are not put into metadata, which crawlers and previews read.
export const metadata: Metadata = { title: "Player" };

const PAGE_SIZE = 25;

export default function PlayerPage({
  params,
  searchParams,
}: PageProps<"/players/[id]">) {
  return (
    <Shell>
      <Suspense fallback={<ProfileSkeleton />}>
        <Profile params={params} searchParams={searchParams} />
      </Suspense>
    </Shell>
  );
}

function parseId(raw: string): number {
  const id = Number(raw);
  if (!Number.isSafeInteger(id) || id < 1) notFound();
  return id;
}

async function Profile({ params, searchParams }: PageProps<"/players/[id]">) {
  const id = parseId((await params).id);
  const sp = await searchParams;
  const filters = {
    discipline: DISCIPLINES[one(sp.discipline) ?? ""]
      ? one(sp.discipline)
      : undefined,
    tournament: /^\d+$/.test(one(sp.tournament) ?? "")
      ? one(sp.tournament)
      : undefined,
    year: validYear(one(sp.year)),
    result: ["won", "lost"].includes(one(sp.result) ?? "")
      ? one(sp.result)
      : undefined,
  };
  const page = positiveInt(one(sp.page), 1);
  // the profile first: a merged id redirects, an unknown or restricted one is not found
  const profile = await api.profile(id);
  const [matches, recent] = await Promise.all([
    api.playerMatches(id, {
      discipline: filters.discipline,
      tournament_id: filters.tournament,
      year: filters.year,
      result: filters.result,
      limit: PAGE_SIZE,
      offset: (page - 1) * PAGE_SIZE,
    }),
    api.playerMatches(id, { limit: 100 }),
  ]);
  const form = recent.items
    .filter((m) => m.status !== "not_played" && m.result !== null)
    .slice(0, 10)
    .map((m) => m.result as "won" | "lost")
    .reverse();
  const filtered = Object.values(filters).some(Boolean);

  return (
    <>
      <Header profile={profile} form={form} />
      <div className="mt-8 grid grid-cols-[minmax(0,1fr)] gap-x-12 gap-y-10 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <Section
          title="Results"
          action={
            <span className="num">
              {matches.total} {matches.total === 1 ? "match" : "matches"} ·
              newest first
            </span>
          }
        >
          <Filters id={id} profile={profile} filters={filters} />
          {matches.items.length === 0 ? (
            page > 1 && matches.total > 0 ? (
              <EmptyState title="No more matches">
                <Link className={LINK} href={`/players/${id}`}>
                  Back to the first page
                </Link>
              </EmptyState>
            ) : (
              <EmptyState
                title={
                  filtered ? "No matches with these filters" : "No matches"
                }
              >
                {filtered && (
                  <Link className={LINK} href={`/players/${id}`}>
                    Clear filters
                  </Link>
                )}
              </EmptyState>
            )
          ) : (
            <MatchHistory matches={matches.items} />
          )}
          <p className="mt-3 text-[12px] text-subtle">
            In each score, this player’s side is the top row, in blue. Source{" "}
            {profile.sources.join(", ") || "not recorded"} ·{" "}
            {formatRetrieved(profile.data_retrieved_at)} ·{" "}
            <Link href="/coverage" className="underline">
              About this data
            </Link>
          </p>
          <Pager
            path={`/players/${id}`}
            params={filters}
            page={page}
            pageSize={PAGE_SIZE}
            total={matches.total}
          />
        </Section>
        <aside className="min-w-0 space-y-8" aria-label="Player summary">
          <ByDiscipline profile={profile} />
          <Opponents profile={profile} />
          <Partners matches={recent.items} />
        </aside>
      </div>
    </>
  );
}

/** Who this is in one line, then the record, the reach and the form in one band. */
function Header({
  profile,
  form,
}: {
  profile: PlayerProfile;
  form: ("won" | "lost")[];
}) {
  const { record } = profile;
  const rate = record.played
    ? Math.round((record.won / record.played) * 100)
    : null;
  return (
    <header>
      <h1 className="display text-[36px] leading-none text-balance sm:text-[46px]">
        {profile.name}
      </h1>
      <p className="mt-2 text-[15px] text-muted-foreground">
        {profile.disciplines.length > 0 && (
          <span className="font-semibold text-foreground">
            {profile.disciplines.map((d) => DISCIPLINES[d] ?? d).join(", ")}
          </span>
        )}
        {profile.disciplines.length > 0 && " · "}
        <span className="num">
          active {formatDate(profile.first_played)} –{" "}
          {formatDate(profile.last_played)}
        </span>
      </p>
      <dl className="mt-4 flex flex-wrap items-baseline gap-x-8 gap-y-3 border-t-2 border-b border-t-form border-b-border py-3">
        <div
          className="flex items-baseline gap-2"
          title="Decided matches only. Walkovers are included and counted separately."
        >
          <dt className="text-[14px] text-muted-foreground">Record</dt>
          <dd className="display num text-[28px] leading-none">
            {record.won}–{record.lost}
          </dd>
        </div>
        <div className="flex items-baseline gap-2">
          <dt className="sr-only">Win rate</dt>
          <dd className="num text-[15px]">
            {rate === null
              ? "no decided matches"
              : `${rate}% of ${record.played} decided`}
            {record.walkovers > 0 && (
              <span className="text-muted-foreground">
                , {record.walkovers} by walkover
              </span>
            )}
          </dd>
        </div>
        <div className="flex items-baseline gap-2">
          <dt className="sr-only">Tournaments</dt>
          <dd className="num text-[15px]">
            {profile.tournaments}{" "}
            {profile.tournaments === 1 ? "tournament" : "tournaments"}
          </dd>
        </div>
        {form.length > 0 && (
          <div className="flex items-center gap-2.5">
            <dt className="text-[14px] text-muted-foreground">
              Last {form.length}
            </dt>
            <dd>
              <FormStrip results={form} />
            </dd>
          </div>
        )}
      </dl>
    </header>
  );
}

/** Wins and losses per discipline, decided matches only: real counts and a bar to compare them. */
function ByDiscipline({ profile }: { profile: PlayerProfile }) {
  if (profile.by_discipline.length === 0) return null;
  return (
    <Section title="By discipline">
      <ul>
        {profile.by_discipline.map((d) => {
          const played = d.won + d.lost;
          return (
            <li key={d.discipline} className="border-b border-border py-2">
              <div className="flex items-baseline justify-between text-[14px]">
                <span>{DISCIPLINES[d.discipline] ?? d.discipline}</span>
                <span className="num">
                  {d.won}–{d.lost}
                  <span className="ml-2 text-[12px] text-subtle">
                    {Math.round((d.won / played) * 100)}%
                  </span>
                </span>
              </div>
              <div
                aria-hidden
                className="mt-1.5 flex h-1.5 overflow-hidden rounded-full bg-loss/20"
              >
                <span
                  className="bg-form"
                  style={{ width: `${(d.won / played) * 100}%` }}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </Section>
  );
}

/** Head-to-head from this player's side, decided matches only. */
function Opponents({ profile }: { profile: PlayerProfile }) {
  return (
    <Section title="Head-to-head">
      {profile.opponents.length === 0 ? (
        <p className="py-3 text-[14px] text-muted-foreground">
          No decided matches yet.
        </p>
      ) : (
        <ul className="text-[14px]">
          {profile.opponents.map((o) => (
            <li
              key={o.id}
              className="flex items-baseline justify-between gap-3 border-b border-border py-2"
            >
              <Link
                href={`/players/${o.id}`}
                className="truncate hover:underline"
              >
                {o.name}
              </Link>
              <span
                className="num shrink-0"
                title={`${o.played} decided matches`}
              >
                <span className="font-semibold text-form">{o.won}</span>
                <span className="text-subtle">–</span>
                <span className="text-loss">{o.lost}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

/** Doubles partners in the latest 100 matches, from this player's side: decided matches only. */
function Partners({ matches }: { matches: PlayerMatch[] }) {
  const byPartner = new Map<
    number,
    { name: string; won: number; lost: number }
  >();
  for (const m of matches) {
    if (m.status === "not_played" || !m.result) continue;
    for (const p of m.partners) {
      if (p.withheld) continue;
      const row = byPartner.get(p.id) ?? { name: p.name, won: 0, lost: 0 };
      row[m.result === "won" ? "won" : "lost"] += 1;
      byPartner.set(p.id, row);
    }
  }
  const rows = [...byPartner.entries()]
    .sort((a, b) => b[1].won + b[1].lost - (a[1].won + a[1].lost))
    .slice(0, 6);
  if (rows.length === 0) return null;
  return (
    <Section title="Doubles partners">
      <ul className="text-[14px]">
        {rows.map(([pid, r]) => (
          <li
            key={pid}
            className="flex items-baseline justify-between gap-3 border-b border-border py-2"
          >
            <Link href={`/players/${pid}`} className="truncate hover:underline">
              {r.name}
            </Link>
            <span className="num shrink-0">
              <span className="font-semibold text-form">{r.won}</span>
              <span className="text-subtle">–</span>
              <span className="text-loss">{r.lost}</span>
            </span>
          </li>
        ))}
      </ul>
      <p className="pt-2 text-[12px] text-subtle">
        Together, in this player’s latest {matches.length} matches.
      </p>
    </Section>
  );
}

function Filters({
  id,
  profile,
  filters,
}: {
  id: number;
  profile: PlayerProfile;
  filters: Record<string, string | undefined>;
}) {
  // years from the active span, so a match's year is always offered; the API filters on match dates
  const first = Number(profile.first_played?.slice(0, 4));
  const last = Number(profile.last_played?.slice(0, 4));
  const years =
    first && last
      ? Array.from({ length: last - first + 1 }, (_, i) => String(last - i))
      : [];
  return (
    <form
      action={`/players/${id}`}
      method="get"
      aria-label="Filter matches"
      className="flex flex-wrap items-center gap-2 py-3"
    >
      <label>
        <span className="sr-only">Discipline</span>
        <Select
          name="discipline"
          defaultValue={filters.discipline ?? ""}
          className="w-36"
        >
          <option value="">All events</option>
          {profile.disciplines.map((d) => (
            <option key={d} value={d}>
              {DISCIPLINES[d] ?? d}
            </option>
          ))}
        </Select>
      </label>
      <label>
        <span className="sr-only">Tournament</span>
        <Select
          name="tournament"
          defaultValue={filters.tournament ?? ""}
          className="w-44"
        >
          <option value="">All tournaments</option>
          {profile.tournament_history.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name ?? `Tournament ${t.id}`}
            </option>
          ))}
        </Select>
      </label>
      <label>
        <span className="sr-only">Year</span>
        <Select
          name="year"
          defaultValue={filters.year ?? ""}
          className="w-[7.5rem]"
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
        <span className="sr-only">Result</span>
        <Select
          name="result"
          defaultValue={filters.result ?? ""}
          className="w-[7.5rem]"
        >
          <option value="">Any result</option>
          <option value="won">Won</option>
          <option value="lost">Lost</option>
        </Select>
      </label>
      <AutoSubmit />
      <button type="submit" className={BUTTON_QUIET}>
        Apply
      </button>
      {Object.values(filters).some(Boolean) && (
        <Link
          href={`/players/${id}`}
          className={`${LINK} px-2 text-[13px] text-muted-foreground`}
        >
          Clear
        </Link>
      )}
    </form>
  );
}

/** The history, grouped by tournament as it was played: a tournament line, then one row per
 * match with the scoresheet (this player's side on top, in blue) and the result mark. */
function MatchHistory({ matches }: { matches: PlayerMatch[] }) {
  const groups: { id: number; name: string; rows: PlayerMatch[] }[] = [];
  for (const m of matches) {
    const last = groups.at(-1);
    if (last && last.id === m.tournament.id) last.rows.push(m);
    else
      groups.push({
        id: m.tournament.id,
        name: m.tournament.name ?? "Tournament",
        rows: [m],
      });
  }
  return (
    <section aria-label="Matches, newest first">
      {groups.map((g, i) => {
        const won = g.rows.filter((m) => m.result === "won").length;
        const lost = g.rows.filter((m) => m.result === "lost").length;
        return (
          <div key={`${g.id}-${i}`} className="mt-3 first:mt-0">
            <div className="flex items-baseline justify-between gap-3 bg-wash px-2 py-1.5">
              <Link
                href={`/tournaments/${g.id}`}
                className="min-w-0 truncate text-[14px] font-semibold hover:underline"
              >
                {g.name}
              </Link>
              <span className="num shrink-0 text-[12px] text-muted-foreground">
                {formatDate(g.rows.at(-1)?.played_on)} · {won}–{lost}
              </span>
            </div>
            <ul>
              {g.rows.map((m) => (
                <MatchRow key={m.id} m={m} />
              ))}
            </ul>
          </div>
        );
      })}
    </section>
  );
}

function MatchRow({ m }: { m: PlayerMatch }) {
  const note = statusNote(m.status);
  return (
    <li className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-x-3 border-b border-border px-2 py-2 sm:grid-cols-[4.5rem_minmax(0,1fr)_auto_auto]">
      <span className="num hidden text-[13px] text-muted-foreground sm:block">
        {formatDate(m.played_on).replace(/ \d{4}$/, "")}
      </span>
      <span className="min-w-0 leading-snug">
        <span className="block truncate">
          <span className="text-subtle">vs </span>
          <People people={m.opponents} />
        </span>
        <span className="block truncate text-[12px] text-subtle">
          {m.event}
          {m.round ? ` · ${m.round}` : ""}
          {m.partners.length > 0 && (
            <>
              {" · with "}
              <People people={m.partners} />
            </>
          )}
        </span>
      </span>
      <span className="justify-self-end" title={`Source: ${m.source}`}>
        {note && m.games.length === 0 ? (
          <StatusNote>{note}</StatusNote>
        ) : (
          <span className="flex items-center gap-2">
            {note && <StatusNote>{note}</StatusNote>}
            <GameSheet games={m.games} you />
          </span>
        )}
      </span>
      <span className="justify-self-end">
        <ResultBadge status={m.status} result={m.result ?? null} />
      </span>
    </li>
  );
}

function ProfileSkeleton() {
  return (
    <div className="space-y-4" role="status" aria-busy="true">
      <span className="sr-only">Loading player…</span>
      <Skeleton className="h-11 w-80 max-w-full bg-muted" />
      <Skeleton className="h-4 w-64 bg-muted" />
      <Skeleton className="h-12 w-full bg-muted" />
      <RowsSkeleton rows={8} />
    </div>
  );
}

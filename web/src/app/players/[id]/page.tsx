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
  RowsSkeleton,
  Section,
  Select,
} from "@/components/bits";
import { MatchHistory } from "@/components/match-history";
import { Shell } from "@/components/shell";
import { Skeleton } from "@/components/ui/skeleton";
import { type PlayerMatch, type PlayerProfile, api } from "@/lib/api/client";
import {
  DISCIPLINES,
  formatDate,
  formatRetrieved,
  one,
  positiveInt,
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
      <Header
        profile={profile}
        form={form}
        hasPartners={recent.items.some(
          (m) =>
            m.result &&
            m.status !== "not_played" &&
            m.partners.some((p) => !p.withheld),
        )}
      />
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
          <WinRate profile={profile} />
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
  hasPartners,
}: {
  profile: PlayerProfile;
  form: ("won" | "lost")[];
  hasPartners: boolean;
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
        {profile.sources.length > 0 && (
          <> · results from {profile.sources.join(" and ")}</>
        )}
      </p>
      <nav
        aria-label="On this page"
        className="mt-2 flex gap-4 text-[14px] lg:hidden"
      >
        <a href="#head-to-head" className="underline">
          Head-to-head
        </a>
        {hasPartners && (
          <a href="#partners" className="underline">
            Partners
          </a>
        )}
        {profile.by_discipline.length > 0 && (
          <a href="#by-discipline" className="underline">
            By discipline
          </a>
        )}
      </nav>
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
              Last {form.length}, oldest → newest
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
    <Section id="by-discipline" title="By discipline">
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
                className="mt-1.5 flex h-1.5 overflow-hidden rounded-full bg-border"
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
    <Section id="head-to-head" title="Head-to-head">
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
              <span className="flex shrink-0 items-baseline gap-3">
                <span className="num" title={`${o.played} decided matches`}>
                  {o.won}
                  <span className="text-subtle">–</span>
                  {o.lost}
                </span>
                <Link
                  href={`/players/${profile.id}/vs/${o.id}`}
                  className="text-[13px] text-form underline"
                  aria-label={`Compare with ${o.name}`}
                >
                  Compare
                </Link>
              </span>
            </li>
          ))}
        </ul>
      )}
      <form
        action={`/players/${profile.id}/vs`}
        method="get"
        role="search"
        aria-label="Compare with another player"
        className="mt-3 flex gap-2"
      >
        <label className="min-w-0 flex-1">
          <span className="sr-only">Compare with another player</span>
          <input
            name="q"
            type="search"
            required
            minLength={2}
            maxLength={100}
            autoComplete="off"
            placeholder="Compare with…"
            className="control w-full"
          />
        </label>
        <button type="submit" className={BUTTON_QUIET}>
          Find
        </button>
      </form>
    </Section>
  );
}

/** Win rate over fixed windows and by format: decided matches only, counted from stored results. */
function WinRate({ profile }: { profile: PlayerProfile }) {
  const pct = (w: number, l: number) =>
    w + l ? `${Math.round((w / (w + l)) * 100)}%` : "–";
  // matches in events we cannot classify still count in the record: shown, never dropped
  const otherWon =
    profile.record.won - profile.by_format.reduce((n, f) => n + f.won, 0);
  const otherLost =
    profile.record.lost - profile.by_format.reduce((n, f) => n + f.lost, 0);
  const rows: [string, number, number][] = [
    ...profile.periods.map(
      (p) => [p.label, p.won, p.lost] as [string, number, number],
    ),
    ...profile.by_format.map(
      (f) =>
        [f.format === "singles" ? "Singles" : "Doubles", f.won, f.lost] as [
          string,
          number,
          number,
        ],
    ),
    ...(otherWon + otherLost > 0
      ? [
          ["Event not classified", otherWon, otherLost] as [
            string,
            number,
            number,
          ],
        ]
      : []),
  ];
  return (
    <Section id="win-rate" title="Win rate">
      <table className="w-full text-[14px]">
        <caption className="sr-only">
          Decided matches won and lost, by period and format
        </caption>
        <thead className="sr-only">
          <tr>
            <th scope="col">Period or format</th>
            <th scope="col">Won–lost</th>
            <th scope="col">Win rate</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, w, l], i) => (
            <tr
              key={label}
              className={
                i === profile.periods.length ? "border-t-2 border-border" : ""
              }
            >
              <th
                scope="row"
                className="border-b border-border py-2 text-left font-normal"
              >
                {label}
              </th>
              <td className="num border-b border-border py-2 text-right">
                {w}–{l}
              </td>
              <td className="num w-14 border-b border-border py-2 text-right text-muted-foreground">
                {pct(w, l)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="pt-2 text-[12px] text-subtle">
        Periods end today. Decided matches only: a walkover counts, a match not
        played does not. Singles is MS and WS; doubles is MD, WD and XD. “Event
        not classified” holds events whose name shows no discipline we can read.
      </p>
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
    <Section id="partners" title="Doubles partners">
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
              {r.won}
              <span className="text-subtle">–</span>
              {r.lost}
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

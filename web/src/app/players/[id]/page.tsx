import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import {
  BUTTON_QUIET,
  EmptyState,
  FormStrip,
  LINK,
  PageHeader,
  Pager,
  Provenance,
  ResultBadge,
  RowsSkeleton,
  Score,
  Section,
  Select,
} from "@/components/bits";
import { Shell } from "@/components/shell";
import { Skeleton } from "@/components/ui/skeleton";
import {
  type Schemas,
  type PlayerMatch,
  type PlayerProfile,
  api,
} from "@/lib/api/client";
import {
  DISCIPLINES,
  formatDate,
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
    api.playerMatches(id, { limit: 30 }),
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
      <div className="grid gap-14 xl:grid-cols-[minmax(0,1fr)_20rem] xl:gap-14">
        <Section
          title="Match history"
          action={
            <span className="num text-muted-foreground">
              {matches.total} {matches.total === 1 ? "match" : "matches"}
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
          <Pager
            path={`/players/${id}`}
            params={filters}
            page={page}
            pageSize={PAGE_SIZE}
            total={matches.total}
          />
        </Section>
        <aside className="min-w-0 space-y-12" aria-label="Player summary">
          <ByDiscipline profile={profile} />
          <Tournaments id={id} profile={profile} />
          <Opponents profile={profile} />
        </aside>
      </div>
    </>
  );
}

function Header({
  profile,
  form,
}: {
  profile: PlayerProfile;
  form: ("won" | "lost")[];
}) {
  const { record } = profile;
  return (
    <PageHeader eyebrow="Player" title={profile.name}>
      <dl className="grid grid-cols-2 gap-x-10 gap-y-6 border-y py-6 sm:grid-cols-4">
        <div title="Decided matches only. Walkovers are included and counted separately.">
          <dt className="label-quiet">Record</dt>
          <dd className="display num mt-2 text-[34px] leading-none font-semibold">
            <span className="text-win">{record.won}</span>
            <span className="text-subtle">–</span>
            <span className="text-loss">{record.lost}</span>
          </dd>
        </div>
        <div>
          <dt className="label-quiet">Matches decided</dt>
          <dd className="display num mt-2 text-[34px] leading-none font-semibold">
            {record.played}
          </dd>
          {record.walkovers > 0 && (
            <dd className="mt-1 text-[12px] text-subtle">
              incl. {record.walkovers} walkovers
            </dd>
          )}
        </div>
        <div>
          <dt className="label-quiet">Tournaments</dt>
          <dd className="display num mt-2 text-[34px] leading-none font-semibold">
            {profile.tournaments}
          </dd>
        </div>
        <div>
          <dt className="label-quiet">Active</dt>
          <dd className="num mt-2 text-[15px] leading-snug">
            {formatDate(profile.first_played)}
            <br />
            <span className="text-muted-foreground">
              to {formatDate(profile.last_played)}
            </span>
          </dd>
        </div>
      </dl>
      <div className="flex flex-wrap items-center justify-between gap-4">
        {form.length > 0 ? (
          <div className="flex items-center gap-3">
            <span className="label-quiet">Last {form.length} decided</span>
            <FormStrip results={form} />
          </div>
        ) : (
          <span />
        )}
        <Provenance
          sources={profile.sources}
          retrievedAt={profile.data_retrieved_at}
        />
      </div>
    </PageHeader>
  );
}

/** Wins and losses per discipline, decided matches only: real counts drawn as a simple bar. */
function ByDiscipline({ profile }: { profile: PlayerProfile }) {
  if (profile.by_discipline.length === 0) return null;
  return (
    <Section title="By discipline">
      <ul className="space-y-4 pt-4">
        {profile.by_discipline.map((d) => {
          const played = d.won + d.lost;
          return (
            <li key={d.discipline}>
              <div className="flex items-baseline justify-between text-[14px]">
                <span>{DISCIPLINES[d.discipline] ?? d.discipline}</span>
                <span className="num text-[13px] text-muted-foreground">
                  <span className="text-win">{d.won}</span>–
                  <span className="text-loss">{d.lost}</span>
                </span>
              </div>
              <div
                aria-hidden
                className="mt-1.5 flex h-1.5 overflow-hidden rounded-full bg-loss/20"
              >
                <span
                  className="bg-win"
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
      className="flex flex-wrap items-center gap-2 py-4"
    >
      <label>
        <span className="sr-only">Discipline</span>
        <Select
          name="discipline"
          defaultValue={filters.discipline ?? ""}
          className="w-40"
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
          className="w-48"
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
        <Select name="year" defaultValue={filters.year ?? ""} className="w-28">
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
          className="w-28"
        >
          <option value="">Any result</option>
          <option value="won">Won</option>
          <option value="lost">Lost</option>
        </Select>
      </label>
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

function People({ people }: { people: Schemas["PlayerRef"][] }) {
  if (people.length === 0)
    return <span className="text-muted-foreground">Not recorded</span>;
  return (
    <>
      {people.map((p, i) => (
        <span key={`${p.id}-${i}`}>
          {i > 0 && <span className="text-subtle"> / </span>}
          {p.withheld ? (
            <span className="text-subtle italic">{p.name}</span>
          ) : (
            <Link
              href={`/players/${p.id}`}
              className="underline-offset-[3px] hover:underline"
            >
              {p.name}
            </Link>
          )}
        </span>
      ))}
    </>
  );
}

function MatchHistory({ matches }: { matches: PlayerMatch[] }) {
  return (
    <ul className="divide-y border-t" aria-label="Matches, newest first">
      {matches.map((m) => {
        const note = statusNote(m.status);
        const noScore = m.games.length === 0 && m.status === "completed";
        return (
          <li
            key={m.id}
            className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 py-4 sm:grid-cols-[6.5rem_1fr_auto_auto] sm:items-center"
          >
            <span className="num text-[13px] text-muted-foreground">
              {formatDate(m.played_on)}
            </span>
            <div className="col-span-2 min-w-0 sm:col-span-1 sm:col-start-2 sm:row-start-1">
              <p className="truncate text-[15px]">
                <span className="text-subtle">vs </span>
                <span className="font-medium">
                  <People people={m.opponents} />
                </span>
                {m.partners.length > 0 && (
                  <span className="text-muted-foreground">
                    {" "}
                    · with <People people={m.partners} />
                  </span>
                )}
              </p>
              <p className="truncate text-[12px] text-subtle">
                {m.event}
                {m.round ? ` · ${m.round}` : ""}
                {note ? ` · ${note}` : ""}
                {" · "}
                <Link
                  href={`/tournaments/${m.tournament.id}`}
                  className="hover:text-foreground hover:underline"
                >
                  {m.tournament.name ?? "Tournament"}
                </Link>
              </p>
            </div>
            <span className="col-start-2 row-start-1 justify-self-end text-[15px] sm:col-start-3">
              {noScore ? (
                <span className="text-[12px] text-subtle">
                  Score unavailable
                </span>
              ) : (
                <Score games={m.games} />
              )}
            </span>
            <span
              className="col-start-2 row-start-2 justify-self-end sm:col-start-4 sm:row-start-1"
              title={`Source: ${m.source}`}
            >
              <ResultBadge status={m.status} result={m.result ?? null} />
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function Tournaments({ id, profile }: { id: number; profile: PlayerProfile }) {
  return (
    <Section title="Tournaments">
      {profile.tournament_history.length === 0 ? (
        <p className="py-4 text-[14px] text-muted-foreground">None recorded.</p>
      ) : (
        <ul className="divide-y text-[14px]">
          {profile.tournament_history.map((t) => (
            <li
              key={t.id}
              className="flex items-center justify-between gap-3 py-3"
            >
              <span className="min-w-0">
                <Link
                  href={`/tournaments/${t.id}`}
                  className="block truncate hover:underline"
                >
                  {t.name ?? `Tournament ${t.id}`}
                </Link>
                <span className="num text-[12px] text-subtle">
                  {formatDate(t.start_date)}
                </span>
              </span>
              <Link
                href={`/players/${id}?tournament=${t.id}`}
                className="num shrink-0 text-[13px] text-muted-foreground hover:text-foreground"
                aria-label={`${t.won}–${t.lost}: show matches at ${t.name ?? "this tournament"}`}
              >
                <span className="text-win">{t.won}</span>–
                <span className="text-loss">{t.lost}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

function Opponents({ profile }: { profile: PlayerProfile }) {
  return (
    <Section title="Frequent opponents">
      {profile.opponents.length === 0 ? (
        <p className="py-4 text-[14px] text-muted-foreground">
          No decided matches yet.
        </p>
      ) : (
        <ul className="divide-y text-[14px]">
          {profile.opponents.map((o) => (
            <li
              key={o.id}
              className="flex items-center justify-between gap-3 py-3"
            >
              <Link
                href={`/players/${o.id}`}
                className="truncate hover:underline"
              >
                {o.name}
              </Link>
              <span
                className="num shrink-0 text-[13px]"
                title={`${o.played} decided matches`}
              >
                <span className="text-win">{o.won}</span>
                <span className="text-subtle">–</span>
                <span className="text-loss">{o.lost}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="pt-3 text-[12px] text-subtle">
        Head-to-head from this player’s side, decided matches only.
      </p>
    </Section>
  );
}

function ProfileSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading player">
      <Skeleton className="h-3 w-20 bg-muted" />
      <Skeleton className="h-14 w-80 bg-muted" />
      <div className="grid grid-cols-2 gap-8 border-y py-6 sm:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-12 w-24 bg-muted" />
        ))}
      </div>
      <RowsSkeleton rows={8} />
    </div>
  );
}

import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import {
  EmptyState,
  Fact,
  FormStrip,
  Label,
  Pager,
  Panel,
  PageHeader,
  Provenance,
  ResultBadge,
  RowsSkeleton,
  Score,
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
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="min-w-0 space-y-3 lg:col-span-2">
          <Filters id={id} profile={profile} filters={filters} />
          <Panel>
            <h2 className="sr-only">Match history</h2>
            {matches.items.length === 0 ? (
              <div className="p-4">
                {page > 1 && matches.total > 0 ? (
                  <EmptyState title="No more matches">
                    <Link className="underline" href={`/players/${id}`}>
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
                      <Link className="underline" href={`/players/${id}`}>
                        Clear filters
                      </Link>
                    )}
                  </EmptyState>
                )}
              </div>
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
          </Panel>
        </div>
        <aside className="min-w-0 space-y-6" aria-label="Player summary">
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
    <PageHeader title={profile.name}>
      <dl className="flex flex-wrap items-end gap-x-8 gap-y-4 pt-2">
        <Fact
          term="Record"
          title="Decided matches only. Walkovers are included and counted separately."
        >
          <span className="num text-2xl font-semibold">
            <span className="text-win">{record.won}</span>
            <span className="text-muted-foreground"> – </span>
            <span className="text-loss">{record.lost}</span>
          </span>
        </Fact>
        <Fact term="Matches decided">
          <span className="num text-2xl font-semibold">{record.played}</span>
        </Fact>
        {record.walkovers > 0 && (
          <Fact term="Of which walkovers">
            <span className="num text-2xl font-semibold">
              {record.walkovers}
            </span>
          </Fact>
        )}
        <Fact term="Tournaments">
          <span className="num text-2xl font-semibold">
            {profile.tournaments}
          </span>
        </Fact>
        <Fact term="Disciplines">
          <span className="text-sm">
            {profile.disciplines.map((d) => DISCIPLINES[d] ?? d).join(", ") ||
              "Not recorded"}
          </span>
        </Fact>
        <Fact term="Active">
          <span className="num text-sm">
            {formatDate(profile.first_played)} –{" "}
            {formatDate(profile.last_played)}
          </span>
        </Fact>
        {form.length > 0 && (
          <Fact term={`Last ${form.length} decided`}>
            <FormStrip results={form} />
          </Fact>
        )}
      </dl>
      <div className="pt-3">
        <Provenance
          sources={profile.sources}
          retrievedAt={profile.data_retrieved_at}
        />
      </div>
    </PageHeader>
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
  const select =
    "h-9 rounded-md border border-input bg-card px-2 text-sm focus-visible:outline-2 focus-visible:outline-ring";
  return (
    <form
      action={`/players/${id}`}
      method="get"
      aria-label="Filter matches"
      className="flex flex-wrap items-end gap-2"
    >
      <label className="flex flex-col gap-1">
        <Label>Discipline</Label>
        <select
          name="discipline"
          defaultValue={filters.discipline ?? ""}
          className={select}
        >
          <option value="">All</option>
          {profile.disciplines.map((d) => (
            <option key={d} value={d}>
              {DISCIPLINES[d] ?? d}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <Label>Tournament</Label>
        <select
          name="tournament"
          defaultValue={filters.tournament ?? ""}
          className={`${select} max-w-56`}
        >
          <option value="">All</option>
          {profile.tournament_history.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name ?? `Tournament ${t.id}`}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <Label>Year</Label>
        <select
          name="year"
          defaultValue={filters.year ?? ""}
          className={select}
        >
          <option value="">All</option>
          {years.map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <Label>Result</Label>
        <select
          name="result"
          defaultValue={filters.result ?? ""}
          className={select}
        >
          <option value="">All</option>
          <option value="won">Won</option>
          <option value="lost">Lost</option>
        </select>
      </label>
      <button
        type="submit"
        className="h-9 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90"
      >
        Apply
      </button>
      {Object.values(filters).some(Boolean) && (
        <Link
          href={`/players/${id}`}
          className="h-9 px-2 py-2 text-sm text-muted-foreground hover:text-foreground"
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
          {i > 0 && <span className="text-muted-foreground"> / </span>}
          {p.withheld ? (
            <span className="text-subtle italic">{p.name}</span>
          ) : (
            <Link
              href={`/players/${p.id}`}
              className="hover:text-primary hover:underline"
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
    <ul className="divide-y" aria-label="Matches, newest first">
      {matches.map((m) => {
        const note = statusNote(m.status);
        return (
          <li
            key={m.id}
            className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 px-4 py-3 sm:grid-cols-[6.5rem_1fr_auto_auto] sm:items-center"
          >
            <span className="num text-xs text-muted-foreground sm:text-sm">
              {formatDate(m.played_on)}
            </span>
            <div className="col-span-2 min-w-0 sm:col-span-1 sm:row-start-1 sm:col-start-2">
              <p className="truncate text-sm">
                <span className="text-muted-foreground">vs </span>
                <People people={m.opponents} />
                {m.partners.length > 0 && (
                  <span className="text-muted-foreground">
                    {" "}
                    · with <People people={m.partners} />
                  </span>
                )}
              </p>
              <p className="truncate text-xs text-muted-foreground">
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
            <span className="row-start-1 col-start-2 justify-self-end text-sm sm:col-start-3">
              <Score games={m.games} />
            </span>
            <span
              className="row-start-2 col-start-2 justify-self-end sm:row-start-1 sm:col-start-4"
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
    <Panel title="Tournaments">
      {profile.tournament_history.length === 0 ? (
        <p className="p-4 text-sm text-muted-foreground">None recorded.</p>
      ) : (
        <ul className="divide-y text-sm">
          {profile.tournament_history.map((t) => (
            <li
              key={t.id}
              className="flex items-center justify-between gap-3 px-4 py-2.5"
            >
              <span className="min-w-0">
                <Link
                  href={`/tournaments/${t.id}`}
                  className="block truncate hover:text-primary hover:underline"
                >
                  {t.name ?? `Tournament ${t.id}`}
                </Link>
                <span className="num text-xs text-muted-foreground">
                  {formatDate(t.start_date)}
                </span>
              </span>
              <Link
                href={`/players/${id}?tournament=${t.id}`}
                className="num shrink-0 text-xs text-muted-foreground hover:text-foreground"
                aria-label={`Show matches at ${t.name ?? "this tournament"}`}
              >
                <span className="text-win">{t.won}</span>–
                <span className="text-loss">{t.lost}</span>
                <span> · {t.matches}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function Opponents({ profile }: { profile: PlayerProfile }) {
  return (
    <Panel title="Most played opponents">
      {profile.opponents.length === 0 ? (
        <p className="p-4 text-sm text-muted-foreground">
          No decided matches yet.
        </p>
      ) : (
        <ul className="divide-y text-sm">
          {profile.opponents.map((o) => (
            <li
              key={o.id}
              className="flex items-center justify-between gap-3 px-4 py-2.5"
            >
              <Link
                href={`/players/${o.id}`}
                className="truncate hover:text-primary hover:underline"
              >
                {o.name}
              </Link>
              <span
                className="num shrink-0 text-xs"
                title={`${o.played} decided matches`}
              >
                <span className="text-win">{o.won}</span>
                <span className="text-muted-foreground">–</span>
                <span className="text-loss">{o.lost}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="border-t px-4 py-2 text-xs text-muted-foreground">
        Head-to-head from this player’s side, decided matches only.
      </p>
    </Panel>
  );
}

function ProfileSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading player">
      <Skeleton className="h-9 w-72" />
      <div className="flex gap-8">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-12 w-24" />
        ))}
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="rounded-lg border bg-card lg:col-span-2">
          <RowsSkeleton rows={8} />
        </div>
        <div className="rounded-lg border bg-card">
          <RowsSkeleton rows={5} />
        </div>
      </div>
    </div>
  );
}

import type { Metadata } from "next";
import Link from "next/link";
import { notFound, permanentRedirect } from "next/navigation";
import { Suspense } from "react";

import { EmptyState, RowsSkeleton, Section } from "@/components/bits";
import { MatchHistory } from "@/components/match-history";
import { Shell } from "@/components/shell";
import { type HeadToHead, type Matchup, api } from "@/lib/api/client";
import { DISCIPLINES, formatDate, one } from "@/lib/format";

// A fixed title: player names and anything derived from ratings stay out of metadata.
export const metadata: Metadata = { title: "Matchup" };

type Discipline = "MS" | "WS";

/** Mynton Matchup: two players in one singles discipline. Probabilities and rating numbers
 * appear only when the API returns them, which it does not until their release (ADR-0013). */
export default function MatchupPage({ searchParams }: PageProps<"/compare">) {
  return (
    <Shell>
      <Suspense fallback={<RowsSkeleton rows={8} />}>
        <Compare searchParams={searchParams} />
      </Suspense>
    </Shell>
  );
}

function id(raw: string | undefined): number | undefined {
  if (raw === undefined || raw === "") return undefined;
  const n = Number(raw);
  if (!Number.isSafeInteger(n) || n < 1) notFound();
  return n;
}

function href(q: { a?: number; b?: number; d: Discipline }): string {
  const p = new URLSearchParams({ discipline: q.d });
  if (q.a) p.set("a", String(q.a));
  if (q.b) p.set("b", String(q.b));
  return `/compare?${p.toString()}`;
}

async function Compare({
  searchParams,
}: Pick<PageProps<"/compare">, "searchParams">) {
  const s = await searchParams;
  const a = id(one(s.a));
  const b = id(one(s.b));
  const d: Discipline = one(s.discipline) === "WS" ? "WS" : "MS";
  if (a && b && a === b) notFound();
  if (!a) return <Pick which="a" d={d} q={one(s.qa)?.trim() ?? ""} />;
  if (!b) return <Pick which="b" d={d} q={one(s.qb)?.trim() ?? ""} a={a} />;
  // the matchup first: for a merged id its redirect keeps this page and the discipline
  const m = await api.matchup(a, b, d);
  const h = await api.headToHead(a, b);
  return <View m={m} h={h} d={d} />;
}

async function Pick({
  which,
  d,
  q,
  a,
}: {
  which: "a" | "b";
  d: Discipline;
  q: string;
  a?: number;
}) {
  if (a) {
    const canonical = await api.canonicalPlayer(a); // a merged id: stay on this page
    if (canonical !== a) permanentRedirect(href({ a: canonical, d }));
  }
  const first = a ? await api.profile(a) : undefined;
  const hits =
    q.length >= 2 ? (await api.searchPlayers(q)).filter((h) => h.id !== a) : [];
  const field = which === "a" ? "qa" : "qb";
  return (
    <>
      <h1 className="display text-[30px] leading-[1.05] sm:text-[38px]">
        {first ? `Compare ${first.name} with…` : "Compare two players"}
      </h1>
      <p className="mt-2 max-w-2xl text-[15px] text-muted-foreground">
        Their meetings, recent results and common opponents in one singles
        discipline.
      </p>
      <form
        method="get"
        role="search"
        aria-label={
          which === "a" ? "Find the first player" : "Find the second player"
        }
        className="mt-4 flex max-w-xl flex-wrap gap-2"
      >
        {a && <input type="hidden" name="a" value={a} />}
        <label className="min-w-0 flex-1">
          <span className="sr-only">
            {which === "a" ? "First player's name" : "Second player's name"}
          </span>
          <input
            name={field}
            type="search"
            defaultValue={q}
            required
            minLength={2}
            maxLength={100}
            autoComplete="off"
            placeholder={which === "a" ? "First player" : "Second player"}
            className="control w-full"
          />
        </label>
        <label>
          <span className="sr-only">Discipline</span>
          <select name="discipline" defaultValue={d} className="control">
            <option value="MS">Men&rsquo;s singles</option>
            <option value="WS">Women&rsquo;s singles</option>
          </select>
        </label>
        <button
          type="submit"
          className="h-11 rounded-md bg-form px-4 text-sm font-semibold text-white lg:h-9"
        >
          Search
        </button>
      </form>
      <div className="mt-8 max-w-3xl">
        <Section title="Players">
          {q.length < 2 ? (
            <p className="py-3 text-[14px] text-muted-foreground">
              Search by name.
            </p>
          ) : hits.length === 0 ? (
            <EmptyState title={`No players match “${q}”`} />
          ) : (
            <ul>
              {hits.map((p) => (
                <li key={p.id} className="border-b border-border">
                  <Link
                    href={
                      which === "a"
                        ? href({ a: p.id, d })
                        : href({ a, b: p.id, d })
                    }
                    className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-4 px-1 py-2.5 hover:bg-wash hover:no-underline"
                  >
                    <span className="truncate font-semibold">{p.name}</span>
                    <span className="num text-[13px] text-muted-foreground">
                      {p.matches} matches
                      {p.last_played
                        ? ` · last ${formatDate(p.last_played)}`
                        : ""}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>
    </>
  );
}

const HEADLINE: Record<Matchup["outcome"], string> = {
  probability: "Estimated chance of winning",
  comparison: "Historical comparison",
  insufficient_data: "Not enough results to compare",
  incompatible_pools: "These players can't be compared",
  identity_uncertain: "Identity not certain",
};

function View({ m, h, d }: { m: Matchup; h: HeadToHead; d: Discipline }) {
  const meetings = h.matches.filter((x) => x.discipline === d);
  const [aw, bw] = m.head_to_head ?? [0, 0];
  return (
    <>
      <header>
        <h1 className="display text-[30px] leading-[1.05] text-balance sm:text-[40px]">
          <Link href={`/players/${h.a.id}`} className="hover:underline">
            {h.a.name}
          </Link>
          <span className="px-3 font-normal text-subtle [font-stretch:100%]">
            v
          </span>
          <Link href={`/players/${h.b.id}`} className="hover:underline">
            {h.b.name}
          </Link>
        </h1>
        <nav aria-label="Discipline" className="mt-3 flex gap-4 text-[15px]">
          {(["MS", "WS"] as const).map((x) => (
            <Link
              key={x}
              href={href({ a: h.a.id, b: h.b.id, d: x })}
              aria-current={x === d ? "page" : undefined}
              className={
                x === d
                  ? "font-semibold text-form"
                  : "text-muted-foreground underline"
              }
            >
              {DISCIPLINES[x]}
            </Link>
          ))}
          <Link
            href={href({ d })}
            className="ml-auto text-muted-foreground underline"
          >
            Change players
          </Link>
        </nav>
      </header>

      <div className="mt-8 grid grid-cols-[minmax(0,1fr)] gap-x-12 gap-y-10 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="min-w-0 space-y-10">
          <Section title="Matchup" action={DISCIPLINES[d]}>
            <Status m={m} names={[h.a.name, h.b.name]} />
          </Section>
          <Section
            title="Meetings"
            action={
              <span className="num">
                decided {aw}–{bw}, from {h.a.name}&rsquo;s side
              </span>
            }
          >
            {meetings.length === 0 ? (
              <p className="py-3 text-[14px] text-muted-foreground">
                No stored {DISCIPLINES[d].toLowerCase()} match has these two
                players on opposite sides.
              </p>
            ) : (
              <MatchHistory matches={meetings} label="Meetings, newest first" />
            )}
          </Section>
          <Suspense fallback={<RowsSkeleton rows={4} />}>
            <Recent id={h.a.id} name={h.a.name} d={d} />
          </Suspense>
          <Suspense fallback={<RowsSkeleton rows={4} />}>
            <Recent id={h.b.id} name={h.b.name} d={d} />
          </Suspense>
        </div>
        <aside className="min-w-0 space-y-10">
          <Section title="Common opponents" action="all disciplines">
            {h.common_opponents.length === 0 ? (
              <p className="py-3 text-[14px] text-muted-foreground">
                None recorded.
              </p>
            ) : (
              <table className="w-full table-fixed text-[14px]">
                <thead>
                  <tr className="text-left text-[12px] text-subtle">
                    <th className="pb-1 font-normal">Opponent</th>
                    <th className="w-16 truncate pb-1 pl-2 text-right font-normal">
                      {h.a.name}
                    </th>
                    <th className="w-16 truncate pb-1 pl-2 text-right font-normal">
                      {h.b.name}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {h.common_opponents.map((c) => (
                    <tr key={c.id} className="border-b border-border">
                      <td className="py-2">
                        <Link
                          href={`/players/${c.id}`}
                          className="block truncate hover:underline"
                        >
                          {c.name}
                        </Link>
                      </td>
                      <td className="num py-2 pl-2 text-right">
                        {c.a_won}–{c.a_lost}
                      </td>
                      <td className="num py-2 pl-2 text-right">
                        {c.b_won}–{c.b_lost}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Section>
          <Section title="About this comparison">
            <dl className="space-y-2 text-[13px] text-muted-foreground">
              {m.data_as_of && (
                <div>
                  <dt className="inline font-semibold text-foreground">
                    BWF results to{" "}
                  </dt>
                  <dd className="inline">{formatDate(m.data_as_of)}</dd>
                </div>
              )}
              <div>
                <dt className="inline font-semibold text-foreground">
                  Matches counted:{" "}
                </dt>
                <dd className="inline num">
                  {m.a?.prior_matches ?? 0} and {m.b?.prior_matches ?? 0}
                </dd>
              </div>
            </dl>
            <ul className="mt-3 list-disc space-y-1 pl-4 text-[13px] text-muted-foreground">
              <li>
                Only stored results are compared; nothing here is about playing
                style, tactics or fitness.
              </li>
              <li>Mynton figures are not BWF world rankings.</li>
              {m.data_as_of && (
                <li>
                  BWF results come from a historical compilation that ends on{" "}
                  {formatDate(m.data_as_of)}.
                </li>
              )}
            </ul>
          </Section>
        </aside>
      </div>
    </>
  );
}

function Status({ m, names }: { m: Matchup; names: [string, string] }) {
  return (
    <div className="py-3">
      <p className="text-[17px] font-semibold">{HEADLINE[m.outcome]}</p>
      {m.outcome === "probability" &&
      m.probability_a !== null &&
      m.probability_a !== undefined ? (
        <Probability m={m} names={names} />
      ) : (
        <ul className="mt-1 space-y-1 text-[15px] text-muted-foreground">
          {m.reasons.map((r) => (
            <li key={r}>
              {r.replace("Player A", names[0]).replace("Player B", names[1])}
            </li>
          ))}
        </ul>
      )}
      {m.ratings_shown && m.a && m.b && (
        <>
          <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[14px]">
            {[m.a, m.b].map((e, i) => (
              <div key={e.player_id} className="contents">
                <dt className="font-semibold">{names[i]}</dt>
                <dd className="num">
                  Mynton estimate {e.rating?.toFixed(0)}
                  {e.rating_deviation
                    ? ` ± ${e.rating_deviation.toFixed(0)}`
                    : ""}{" "}
                  · {e.prior_matches} matches
                  {e.provisional ? " (provisional)" : ""}
                </dd>
              </div>
            ))}
          </dl>
          <p className="mt-1 text-[12px] text-subtle">
            A Mynton estimate from BWF results, not a BWF ranking.
          </p>
        </>
      )}
    </div>
  );
}

function Probability({ m, names }: { m: Matchup; names: [string, string] }) {
  const p = m.probability_a ?? 0;
  const c = m.calibration;
  return (
    <div className="mt-1 text-[15px]">
      <p className="num text-[28px] font-semibold">
        {names[0]} {Math.round(p * 100)}% · {names[1]}{" "}
        {100 - Math.round(p * 100)}%
      </p>
      {c && (
        <p className="mt-1 text-muted-foreground">
          Of {c.forecasts} earlier forecasts that gave the favourite{" "}
          {Math.round(c.bin_lo * 100)}–{Math.round(c.bin_hi * 100)}%, the
          favourite won {Math.round(c.observed_rate * 100)}%.
        </p>
      )}
      {m.model && (
        <p className="mt-1 text-[13px] text-subtle">
          Model {m.model.name} {m.model.version}, results to{" "}
          {formatDate(m.model.data_as_of)}. An estimate from past results only.
        </p>
      )}
    </div>
  );
}

async function Recent({
  id: pid,
  name,
  d,
}: {
  id: number;
  name: string;
  d: Discipline;
}) {
  const page = await api.playerMatches(pid, { discipline: d, limit: 10 });
  return (
    <Section
      title={`Recent results: ${name}`}
      action={
        <Link href={`/players/${pid}?discipline=${d}`} className="underline">
          All
        </Link>
      }
    >
      {page.items.length === 0 ? (
        <p className="py-3 text-[14px] text-muted-foreground">
          No {DISCIPLINES[d].toLowerCase()} results.
        </p>
      ) : (
        <MatchHistory matches={page.items} label={`${name}, newest first`} />
      )}
    </Section>
  );
}

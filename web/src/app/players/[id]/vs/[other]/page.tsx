import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { RowsSkeleton, Section } from "@/components/bits";
import { MatchHistory } from "@/components/match-history";
import { Shell } from "@/components/shell";
import { Skeleton } from "@/components/ui/skeleton";
import { type HeadToHead, api } from "@/lib/api/client";
import { DISCIPLINES, formatDate } from "@/lib/format";

// A fixed title: player names are not put into metadata, which crawlers and previews read.
export const metadata: Metadata = { title: "Head-to-head" };

export default function HeadToHeadPage({
  params,
}: PageProps<"/players/[id]/vs/[other]">) {
  return (
    <Shell>
      <Suspense
        fallback={
          <div className="space-y-4" role="status" aria-busy="true">
            <span className="sr-only">Loading comparison…</span>
            <Skeleton className="h-10 w-96 max-w-full bg-muted" />
            <RowsSkeleton rows={6} />
          </div>
        }
      >
        <Compare params={params} />
      </Suspense>
    </Shell>
  );
}

function id(raw: string): number {
  const n = Number(raw);
  if (!Number.isSafeInteger(n) || n < 1) notFound();
  return n;
}

async function Compare({
  params,
}: Pick<PageProps<"/players/[id]/vs/[other]">, "params">) {
  const p = await params;
  const a = id(p.id);
  const b = id(p.other);
  if (a === b) notFound();
  const h = await api.headToHead(a, b);
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
        <Summary h={h} />
      </header>
      <div className="mt-8 grid grid-cols-[minmax(0,1fr)] gap-x-12 gap-y-10 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <Section
          title="Meetings"
          action={<span className="num">{h.meetings} · newest first</span>}
        >
          {h.meetings === 0 ? (
            <p className="py-3 text-[14px] text-muted-foreground">
              No stored match has these two players on opposite sides.
            </p>
          ) : (
            <MatchHistory matches={h.matches} label="Meetings, newest first" />
          )}
          <p className="mt-3 text-[12px] text-subtle">
            From {h.a.name}’s side: their points are the top row, in blue. Only
            matches linked to these two exact player records are counted; a
            namesake in another source is a different record until identity
            linking proves otherwise. Each row names its source.
          </p>
        </Section>
        <aside className="min-w-0 space-y-8" aria-label="Comparison details">
          {h.by_discipline.length > 0 && (
            <Section title="By discipline">
              <table className="w-full text-[14px]">
                <caption className="sr-only">
                  Wins each, decided meetings, by discipline
                </caption>
                <thead className="sr-only">
                  <tr>
                    <th scope="col">Discipline</th>
                    <th scope="col">Wins each</th>
                  </tr>
                </thead>
                <tbody>
                  {h.by_discipline.map((d) => (
                    <tr key={d.discipline}>
                      <th
                        scope="row"
                        className="border-b border-border py-2 text-left font-normal"
                      >
                        {DISCIPLINES[d.discipline] ?? "Event not classified"}
                      </th>
                      <td className="num border-b border-border py-2 text-right">
                        {d.a_won}–{d.b_won}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Section>
          )}
          <Section title="Common opponents">
            {h.common_opponents.length === 0 ? (
              <p className="py-3 text-[14px] text-muted-foreground">
                None in decided matches.
              </p>
            ) : (
              <table className="w-full text-[14px]">
                <caption className="sr-only">
                  Each player’s record against opponents both have met
                </caption>
                <thead>
                  <tr className="text-[12px] text-muted-foreground">
                    <th scope="col" className="pb-1 text-left font-normal">
                      Opponent
                    </th>
                    <th
                      scope="col"
                      className="pb-1 pl-4 text-right font-normal"
                    >
                      {abbr(h.a.name)}
                    </th>
                    <th
                      scope="col"
                      className="pb-1 pl-4 text-right font-normal"
                    >
                      {abbr(h.b.name)}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {h.common_opponents.map((o) => (
                    <tr key={o.id}>
                      <th
                        scope="row"
                        className="border-b border-border py-2 text-left font-normal"
                      >
                        <Link
                          href={`/players/${o.id}`}
                          className="hover:underline"
                        >
                          {o.name}
                        </Link>
                      </th>
                      <td className="num border-b border-border py-2 pl-4 text-right">
                        {o.a_won}–{o.a_lost}
                      </td>
                      <td className="num border-b border-border py-2 pl-4 text-right">
                        {o.b_won}–{o.b_lost}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <p className="pt-2 text-[12px] text-subtle">
              Decided matches; each record from that player’s side.
            </p>
          </Section>
          <p className="text-[14px]">
            <Link
              href={`/players/${h.b.id}/vs/${h.a.id}`}
              className="underline"
            >
              See it from {h.b.name}’s side
            </Link>
          </p>
        </aside>
      </div>
    </>
  );
}

function abbr(name: string): string {
  return (
    name.split(/\s+/).find((w) => w === w.toUpperCase() && /[A-Z]/.test(w)) ??
    name.split(" ")[0]
  );
}

function Summary({ h }: { h: HeadToHead }) {
  return (
    <dl className="mt-4 flex flex-wrap items-baseline gap-x-8 gap-y-3 border-t-2 border-b border-t-form border-b-border py-3">
      <div
        className="flex items-baseline gap-2"
        title="Decided meetings only; walkovers included"
      >
        <dt className="text-[14px] text-muted-foreground">Wins</dt>
        <dd className="display num text-[28px] leading-none">
          {h.a_won}–{h.b_won}
        </dd>
      </div>
      <div className="flex items-baseline gap-2">
        <dt className="sr-only">Meetings</dt>
        <dd className="num text-[15px]">
          {h.meetings} {h.meetings === 1 ? "meeting" : "meetings"}
          {h.meetings !== h.decided && (
            <span className="text-muted-foreground">
              , {h.meetings - h.decided} without a result
            </span>
          )}
          {h.walkovers > 0 && (
            <span className="text-muted-foreground">
              , {h.walkovers} by walkover
            </span>
          )}
        </dd>
      </div>
      {h.last_met && (
        <div className="flex items-baseline gap-2">
          <dt className="text-[14px] text-muted-foreground">Last met</dt>
          <dd className="num text-[15px]">{formatDate(h.last_met)}</dd>
        </div>
      )}
    </dl>
  );
}

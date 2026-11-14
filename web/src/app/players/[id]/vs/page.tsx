import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { EmptyState, RowsSkeleton, Section } from "@/components/bits";
import { Shell } from "@/components/shell";
import { api } from "@/lib/api/client";
import { formatDate, one } from "@/lib/format";

export const metadata: Metadata = { title: "Compare players" };

/** Pick the second player for a comparison: a name search, each hit opening the comparison. */
export default function ComparePickPage({
  params,
  searchParams,
}: PageProps<"/players/[id]/vs">) {
  return (
    <Shell>
      <Suspense fallback={<RowsSkeleton rows={6} />}>
        <Pick params={params} searchParams={searchParams} />
      </Suspense>
    </Shell>
  );
}

async function Pick({ params, searchParams }: PageProps<"/players/[id]/vs">) {
  const id = Number((await params).id);
  if (!Number.isSafeInteger(id) || id < 1) notFound();
  const q = one((await searchParams).q)?.trim() ?? "";
  const player = await api.profile(id);
  const hits =
    q.length >= 2
      ? (await api.searchPlayers(q)).filter((h) => h.id !== player.id)
      : [];
  return (
    <>
      <h1 className="display text-[30px] leading-[1.05] sm:text-[38px]">
        Compare {player.name} with…
      </h1>
      <form
        method="get"
        role="search"
        aria-label="Find a player to compare"
        className="mt-4 flex max-w-xl gap-2"
      >
        <label className="min-w-0 flex-1">
          <span className="sr-only">Player name</span>
          <input
            name="q"
            type="search"
            defaultValue={q}
            required
            minLength={2}
            maxLength={100}
            autoComplete="off"
            placeholder="Player name"
            className="control w-full"
          />
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
              {hits.map((h) => (
                <li key={h.id} className="border-b border-border">
                  <Link
                    href={`/players/${player.id}/vs/${h.id}`}
                    className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-4 px-1 py-2.5 hover:bg-wash hover:no-underline"
                  >
                    <span className="truncate font-semibold">{h.name}</span>
                    <span className="num text-[13px] text-muted-foreground">
                      {h.matches} matches
                      {h.last_played
                        ? ` · last ${formatDate(h.last_played)}`
                        : ""}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Section>
        <p className="mt-4 text-[14px]">
          <Link href={`/players/${player.id}`} className="underline">
            Back to {player.name}
          </Link>
        </p>
      </div>
    </>
  );
}

import Link from "next/link";

import { ResultBadge } from "@/components/bits";
import { GameSheet, People, StatusNote } from "@/components/scoresheet";
import type { PlayerMatch } from "@/lib/api/client";
import { formatDate, statusNote } from "@/lib/format";

/** The history, grouped by tournament as it was played: a tournament line, then one row per
 * match with the scoresheet (this player's side on top, in blue) and the result mark. */
export function MatchHistory({
  matches,
  label = "Matches, newest first",
}: {
  matches: PlayerMatch[];
  label?: string;
}) {
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
    <section aria-label={label}>
      {groups.map((g, i) => {
        const won = g.rows.filter((m) => m.result === "won").length;
        const lost = g.rows.filter((m) => m.result === "lost").length;
        return (
          <div key={`${g.id}-${i}`} className="mt-3 first:mt-0">
            <div className="flex items-baseline justify-between gap-3 bg-wash px-2 py-1.5">
              <Link
                href={`/tournaments/${g.id}`}
                className="min-w-0 text-[14px] font-semibold hover:underline"
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
        <span className="block">
          <span className="text-subtle">vs </span>
          <People people={m.opponents} />
        </span>
        <span className="block text-[12px] text-subtle">
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

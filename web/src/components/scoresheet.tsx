import Link from "next/link";
import type { ReactNode } from "react";

import { ExpandableRow } from "@/components/expandable-row";
import type { Schemas, TournamentMatch } from "@/lib/api/client";
import { formatScore, statusNote } from "@/lib/format";
import { cn } from "@/lib/utils";

type Games = readonly (readonly [number, number])[];

/** The scoresheet cell: one ruled column per game actually played, the top row one side and the
 * bottom row the other. `you` marks the top row as the player being viewed (ballpoint blue);
 * a game's winning score is set in full ink, the losing one in pencil grey. */
export function GameSheet({
  games,
  you = false,
}: {
  games: Games;
  you?: boolean;
}) {
  if (games.length === 0) return null;
  const cell =
    "w-7 border-l border-sheet/70 text-center leading-[18px] first:border-l-0";
  return (
    <span
      title={formatScore(games)}
      className="inline-grid shrink-0 grid-flow-col grid-rows-2 overflow-hidden rounded-[3px] border border-sheet text-[13px]"
    >
      {games.map(([a, b], g) => (
        <span key={g} className="contents">
          <span
            className={cn(
              cell,
              "border-b border-b-sheet/70",
              a > b ? "font-bold" : "text-subtle",
              you ? "text-you" : a > b && "text-foreground",
            )}
          >
            {a}
          </span>
          <span
            className={cn(
              cell,
              b > a ? "font-bold text-foreground" : "text-subtle",
            )}
          >
            {b}
          </span>
        </span>
      ))}
      <span className="sr-only">Score {formatScore(games)}</span>
    </span>
  );
}

/** Names of one side; a withheld person is never linked. */
export function People({ people }: { people: Schemas["PlayerRef"][] }) {
  if (people.length === 0)
    return <span className="text-subtle">Not recorded</span>;
  return (
    <>
      {people.map((p, i) => (
        <span key={`${p.id}-${i}`}>
          {i > 0 && <span className="text-subtle"> / </span>}
          {p.withheld ? (
            <span className="text-subtle italic">{p.name}</span>
          ) : (
            <Link href={`/players/${p.id}`} className="hover:underline">
              {p.name}
            </Link>
          )}
        </span>
      ))}
    </>
  );
}

/** A status the scores cannot show, written out: walkover, retired, score unavailable… */
export function StatusNote({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-[3px] bg-wash px-1.5 py-0.5 text-[12px] whitespace-nowrap text-foreground">
      {children}
    </span>
  );
}

/** One tournament result in reference notation: winner first, "d.", the other side, the games.
 * The score opens the full scoresheet with the event and round. */
export function ResultRow({
  match: m,
  context,
}: {
  match: TournamentMatch;
  context?: string;
}) {
  const note = statusNote(m.status);
  const decided = m.winner_side === 1 || m.winner_side === 2;
  const [first, second] =
    m.winner_side === 2 ? [m.side2, m.side1] : [m.side1, m.side2];
  const games: Games =
    m.winner_side === 2 ? m.games.map(([a, b]) => [b, a] as const) : m.games;
  const text = games.map(([a, b]) => `${a}–${b}`).join("  ");
  return (
    <ExpandableRow
      label={`Scoresheet: ${note ?? (text || "no score")}`}
      main={
        <>
          {context && (
            <span className="block text-[12px] text-subtle">{context}</span>
          )}
          <span className={cn(decided && "font-semibold")}>
            <People people={first} />
          </span>
          <span className="px-1.5 text-subtle">{decided ? "d." : "v"}</span>
          <People people={second} />
          {decided && <span className="sr-only"> (first named won)</span>}
        </>
      }
      score={note ? <StatusNote>{note}</StatusNote> : text}
    >
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        {games.length > 0 ? (
          <span className="flex items-center gap-3">
            <span className="grid grid-rows-2 text-right leading-[20px]">
              <span className="font-semibold">{names(first)}</span>
              <span className="text-subtle">{names(second)}</span>
            </span>
            <GameSheet games={games} />
          </span>
        ) : (
          <span className="text-subtle">
            {m.status === "winner_only"
              ? "The source records the winner but publishes no score."
              : "No games were played."}
          </span>
        )}
        <span className="text-subtle">
          {m.event}
          {m.round ? ` · ${m.round}` : ""}
        </span>
      </div>
    </ExpandableRow>
  );
}

// in the opened sheet the names are labels for its rows; the links are in the row above
function names(people: Schemas["PlayerRef"][]) {
  return people.map((p) => p.name).join(" / ") || "Not recorded";
}

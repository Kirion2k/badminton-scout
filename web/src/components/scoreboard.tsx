import Link from "next/link";

import type { TournamentMatch } from "@/lib/api/client";
import { formatDate, formatScore, statusNote } from "@/lib/format";
import { cn } from "@/lib/utils";

/** A broadcast-style scoreboard: a header strip (event, round, status), then one row per side
 * with a lime lane bar on the winner and one fixed column per game actually played. The won
 * game is bold navy; nothing is drawn for a game that was not played. */
export function Scoreboard({
  match: m,
  showEvent = false,
  showRound = true,
}: {
  match: TournamentMatch;
  showEvent?: boolean;
  showRound?: boolean;
}) {
  const note = statusNote(m.status);
  const side1 = m.games.map(([a]) => a);
  const side2 = m.games.map(([, b]) => b);
  const context = [showEvent && m.event, showRound && m.round]
    .filter(Boolean)
    .join(" · ");
  return (
    <li className="group overflow-hidden rounded-[10px] bg-card ring-1 ring-border transition-shadow duration-150 hover:shadow-[0_6px_20px_-12px_rgb(11_21_38/0.35)] hover:ring-foreground/20">
      <div className="flex items-center justify-between gap-3 border-b border-border/70 px-3.5 py-2">
        <span className="label-quiet min-w-0 truncate text-[11px]">
          {context || formatDate(m.played_on)}
        </span>
        {note ? (
          <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 font-display text-[11px] font-semibold tracking-[0.1em] text-foreground uppercase">
            {note}
          </span>
        ) : (
          <span className="label-quiet shrink-0 text-[11px]">
            {context ? formatDate(m.played_on) : "Completed"}
          </span>
        )}
      </div>
      <Side
        people={m.side1}
        points={side1}
        opponent={side2}
        won={m.winner_side === 1}
      />
      <Side
        people={m.side2}
        points={side2}
        opponent={side1}
        won={m.winner_side === 2}
      />
      <p className="sr-only">
        Score:{" "}
        {m.status === "winner_only"
          ? "unavailable"
          : m.games.length
            ? formatScore(m.games)
            : "none recorded"}
      </p>
    </li>
  );
}

function Side({
  people,
  points,
  opponent,
  won,
}: {
  people: TournamentMatch["side1"];
  points: number[];
  opponent: number[];
  won: boolean;
}) {
  return (
    <div className="grid min-h-11 grid-cols-[4px_minmax(0,1fr)_auto] items-center gap-3 pr-2">
      <span
        aria-hidden
        className={cn("h-full self-stretch", won && "bg-lime")}
      />
      <span
        className={cn(
          "min-w-0 truncate py-2 text-[15px] leading-snug",
          won ? "font-semibold text-foreground" : "text-muted-foreground",
        )}
      >
        {people.length === 0
          ? "Not recorded"
          : people.map((p, i) => (
              <span key={`${p.id}-${i}`}>
                {i > 0 && <span className="text-subtle"> / </span>}
                {p.withheld ? (
                  <span className="text-subtle italic">{p.name}</span>
                ) : (
                  <Link
                    href={`/players/${p.id}`}
                    className="underline-offset-[3px] hover:text-foreground hover:underline"
                  >
                    {p.name}
                  </Link>
                )}
              </span>
            ))}
        {won && <span className="sr-only"> (winner)</span>}
      </span>
      <span className="num flex shrink-0" aria-hidden>
        {points.map((pt, g) => (
          <span
            key={g}
            className={cn(
              "reveal w-8 text-center font-display text-[21px] leading-none sm:w-9",
              pt > opponent[g]
                ? "font-bold text-foreground"
                : "font-medium text-subtle",
            )}
            style={{ animationDelay: `${g * 40}ms` }}
          >
            {pt}
          </span>
        ))}
      </span>
    </div>
  );
}

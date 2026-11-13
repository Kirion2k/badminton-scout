// Pure display helpers: every label the UI shows for a result or status comes from here.

const dateFormat = new Intl.DateTimeFormat("en-AU", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "Date not recorded";
  return dateFormat.format(new Date(`${iso.slice(0, 10)}T00:00:00Z`));
}

export function formatDateRange(
  start: string | null | undefined,
  end: string | null | undefined,
) {
  if (!start) return "Dates not recorded";
  if (!end || end === start) return formatDate(start);
  return `${formatDate(start)} – ${formatDate(end)}`;
}

export function formatRetrieved(iso: string | null | undefined): string {
  if (!iso) return "not yet retrieved";
  return `retrieved ${formatDate(iso)}`;
}

/** "13 Nov 2026, 00:30 UTC": sync times are shown in UTC, the day the request budget uses. */
export function formatMoment(
  iso: string | null | undefined,
): string | undefined {
  if (!iso) return undefined;
  const d = new Date(iso);
  const time = d.toLocaleTimeString("en-AU", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  });
  return `${d.toLocaleDateString("en-AU", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" })}, ${time} UTC`;
}

/** The scheduler's planned next run; a time already past means the schedule is not running. */
export function formatNextSync(
  iso: string | null | undefined,
  now = new Date(),
): string {
  if (!iso) return "No schedule configured";
  return new Date(iso) < now
    ? `Overdue: was due ${formatMoment(iso)}`
    : formatMoment(iso)!;
}

/** "21–15 · 21–18". `games` is already ordered from the viewer's side. */
export function formatScore(
  games: readonly (readonly [number, number])[],
): string {
  return games.map(([a, b]) => `${a}–${b}`).join(" · ");
}

export type Outcome = "won" | "lost" | null;

export interface ResultLabel {
  text: string;
  tone: "win" | "loss" | "neutral";
  title: string;
}

/** A match's outcome for one side. A cancelled or unplayed match is never a loss. */
export function resultLabel(status: string, result: Outcome): ResultLabel {
  if (status === "not_played") {
    return {
      text: "Not played",
      tone: "neutral",
      title: "Cancelled or not played: no result",
    };
  }
  if (result === null)
    return {
      text: "No result",
      tone: "neutral",
      title: "Outcome not recorded",
    };
  const won = result === "won";
  const tone = won ? "win" : "loss";
  if (status === "walkover") {
    return {
      text: won ? "W/O" : "L w/o",
      tone,
      title: won ? "Won by walkover" : "Lost by walkover",
    };
  }
  if (status === "winner_only") {
    return {
      text: won ? "W" : "L",
      tone,
      title: won ? "Won (score unavailable)" : "Lost (score unavailable)",
    };
  }
  if (status === "disqualified") {
    return {
      text: won ? "W DQ" : "L DQ",
      tone,
      title: won ? "Won: opponent disqualified" : "Lost: disqualified",
    };
  }
  if (status === "retired") {
    return {
      text: won ? "W ret." : "L ret.",
      tone,
      title: won ? "Won: opponent retired" : "Lost: retired",
    };
  }
  return { text: won ? "W" : "L", tone, title: won ? "Won" : "Lost" };
}

export function statusNote(status: string): string | null {
  switch (status) {
    case "walkover":
      return "Walkover";
    case "disqualified":
      return "Disqualified";
    case "winner_only":
      return "Score unavailable";
    case "retired":
      return "Retired";
    case "not_played":
      return "Not played";
    default:
      return null;
  }
}

export const DISCIPLINES: Record<string, string> = {
  MS: "Men's singles",
  WS: "Women's singles",
  MD: "Men's doubles",
  WD: "Women's doubles",
  XD: "Mixed doubles",
};

/** One string or the first of several, from a Next.js searchParams value. */
export function one(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

/** A page number: junk or absurd values fall back, so the API never sees an out-of-range offset. */
export function positiveInt(
  value: string | undefined,
  fallback: number,
  max = 10_000,
): number {
  const n = Number.parseInt(value ?? "", 10);
  return Number.isFinite(n) && n > 0 && n <= max ? n : fallback;
}

/** A year the API accepts (1900–2100), else undefined. */
export function validYear(value: string | undefined): string | undefined {
  const n = Number(value);
  return /^\d{4}$/.test(value ?? "") && n >= 1900 && n <= 2100
    ? value
    : undefined;
}

// Server-side access to the Badminton Scout API. Never imported by client components: the API
// base URL and every response stay on the server, and nothing here is cached (docs/design.md).
import "server-only";

import { notFound, permanentRedirect } from "next/navigation";

import type { components } from "./schema";

export type Schemas = components["schemas"];
export type PlayerHit = Schemas["PlayerHit"];
export type PlayerProfile = Schemas["PlayerProfile"];
export type PlayerMatch = Schemas["PlayerMatch"];
export type MatchPage = Schemas["MatchPage"];
export type TournamentPage = Schemas["TournamentPage"];
export type TournamentSummary = Schemas["TournamentSummary"];
export type TournamentDetail = Schemas["TournamentDetail"];
export type TournamentMatchPage = Schemas["TournamentMatchPage"];
export type TournamentMatch = Schemas["TournamentMatch"];
export type Coverage = Schemas["Coverage"];
export type HeadToHead = Schemas["HeadToHead"];
export type Matchup = Schemas["Matchup"];

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly path: string,
  ) {
    super(`The data service answered ${status}.`);
  }
}

const base = () => process.env.SCOUT_API_URL ?? "http://127.0.0.1:8000";

type Query = Record<string, string | number | undefined | null>;

function url(path: string, query: Query = {}): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "")
      params.set(key, String(value));
  }
  const qs = params.toString();
  return `${base()}${path}${qs ? `?${qs}` : ""}`;
}

/** GET a JSON resource. 404 becomes the not-found page; a merged player's 308 becomes a
 * permanent redirect to its canonical page; anything else non-2xx throws ApiError. */
async function get<T>(path: string, query?: Query): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url(path, query), {
      cache: "no-store",
      redirect: "manual",
    });
  } catch {
    throw new ApiError(503, path);
  }
  if (response.status === 404) notFound();
  if (response.status === 308) {
    const location = response.headers.get("location") ?? "";
    // a merged id: the comparison keeps its pair, a profile goes to the canonical player
    const matchup = location.match(/\/v1\/matchups\/compare\?(.*)$/);
    if (matchup) permanentRedirect(`/compare?${matchup[1]}`);
    const pair = location.match(/\/v1\/players\/(\d+)\/head-to-head\/(\d+)/);
    if (pair) permanentRedirect(`/players/${pair[1]}/vs/${pair[2]}`);
    const target = location.match(/\/v1\/players\/(\d+)/);
    if (target) permanentRedirect(`/players/${target[1]}`);
  }
  if (!response.ok) throw new ApiError(response.status, path);
  return (await response.json()) as T;
}

/** The canonical id for a (possibly merged) player, without leaving the current page: a merged
 * id answers 308 to its canonical profile. Unknown or withheld players are not found. */
async function canonicalPlayer(id: number): Promise<number> {
  let response: Response;
  try {
    response = await fetch(url(`/v1/players/${id}`), {
      cache: "no-store",
      redirect: "manual",
    });
  } catch {
    throw new ApiError(503, `/v1/players/${id}`);
  }
  if (response.status === 404) notFound();
  if (response.status === 308) {
    const target = (response.headers.get("location") ?? "").match(
      /\/v1\/players\/(\d+)/,
    );
    if (target) return Number(target[1]);
  }
  if (!response.ok) throw new ApiError(response.status, `/v1/players/${id}`);
  return id;
}

export const api = {
  canonicalPlayer,
  searchPlayers: (q: string, limit = 20) =>
    get<PlayerHit[]>("/v1/players", { q, limit }),
  profile: (id: number) => get<PlayerProfile>(`/v1/players/${id}`),
  playerMatches: (id: number, query: Query) =>
    get<MatchPage>(`/v1/players/${id}/matches`, query),
  tournaments: (query: Query) => get<TournamentPage>("/v1/tournaments", query),
  tournament: (id: number) => get<TournamentDetail>(`/v1/tournaments/${id}`),
  tournamentMatches: (id: number, query: Query) =>
    get<TournamentMatchPage>(`/v1/tournaments/${id}/matches`, query),
  coverage: () => get<Coverage>("/v1/coverage"),
  headToHead: (a: number, b: number) =>
    get<HeadToHead>(`/v1/players/${a}/head-to-head/${b}`),
  matchup: (a: number, b: number, discipline: "MS" | "WS") =>
    get<Matchup>("/v1/matchups/compare", { a, b, discipline }),
};

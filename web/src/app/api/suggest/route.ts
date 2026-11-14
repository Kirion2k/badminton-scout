import { NextResponse } from "next/server";

import { api } from "@/lib/api/client";

export type Suggestion = {
  id: number;
  name: string;
  matches: number;
  last_played: string | null;
};

/** Name suggestions for the search box: the API's player search, server-side, trimmed to what a
 * suggestion shows. Withheld players are dropped: a suggestion would only say "Name withheld". */
export async function GET(request: Request) {
  const q = new URL(request.url).searchParams.get("q")?.trim() ?? "";
  if (q.length < 2 || q.length > 100) return NextResponse.json([]);
  try {
    const hits = await api.searchPlayers(q, 8);
    const body: Suggestion[] = hits
      .filter((h) => !h.withheld)
      .map((h) => ({
        id: h.id,
        name: h.name,
        matches: h.matches,
        last_played: h.last_played ?? null,
      }));
    return NextResponse.json(body, {
      headers: { "cache-control": "no-store" },
    });
  } catch {
    // suggestions are a convenience: a failure shows none, the form still searches
    return NextResponse.json([]);
  }
}

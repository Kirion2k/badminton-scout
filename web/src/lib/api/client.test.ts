import { afterEach, describe, expect, it, vi } from "vitest";

const navigation = vi.hoisted(() => ({
  notFound: vi.fn(() => {
    throw new Error("NOT_FOUND");
  }),
  permanentRedirect: vi.fn((to: string) => {
    throw new Error(`REDIRECT ${to}`);
  }),
}));
vi.mock("next/navigation", () => navigation);
// the guard throws outside a server environment by design; this test runs the logic in jsdom
vi.mock("server-only", () => ({}));

import { ApiError, api } from "./client";

function respond(
  status: number,
  body: unknown = {},
  headers: Record<string, string> = {},
) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status, headers })),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("never caches and never follows redirects silently", async () => {
    respond(200, []);
    await api.searchPlayers("tester");
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(init).toMatchObject({ cache: "no-store", redirect: "manual" });
  });
  it("turns 404 into the not-found page", async () => {
    respond(404);
    await expect(api.profile(1)).rejects.toThrow("NOT_FOUND");
  });
  it("turns a merged player's 308 into a canonical redirect", async () => {
    respond(308, {}, { location: "/v1/players/42" });
    await expect(api.profile(7)).rejects.toThrow("REDIRECT /players/42");
  });
  it("reports server failures without their body", async () => {
    respond(500, { detail: "internal secret" });
    const error = await api.coverage().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(String((error as Error).message)).not.toContain("secret");
  });
  it("reports an unreachable API as unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Promise.reject(new TypeError("fetch failed"))),
    );
    await expect(api.coverage()).rejects.toMatchObject({ status: 503 });
  });
});

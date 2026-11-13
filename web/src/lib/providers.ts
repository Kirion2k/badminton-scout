// Labels for the provider statuses the API derives from real ingest results (GET /v1/coverage).
import type { Schemas } from "@/lib/api/client";

export type ProviderStatus = Schemas["ProviderCoverage"]["status"];

export const PROVIDER_STATUS: Record<
  ProviderStatus,
  { text: string; tone: "good" | "partial" | "waiting" | "bad" }
> = {
  connected_importing: { text: "Connected · importing", tone: "good" },
  connected_read_only: { text: "Connected · read only", tone: "partial" },
  partially_validated: { text: "Partially validated", tone: "partial" },
  pending_access: { text: "Pending technical access", tone: "waiting" },
  access_unavailable: { text: "Access unavailable", tone: "bad" },
  source_error: { text: "Source error", tone: "bad" },
};

// The last scheduled pass for a provider (GET /v1/coverage `last_sync_status`).
export const SYNC_STATUS: Record<string, string> = {
  succeeded: "completed",
  incomplete: "daily request allowance used up; continues on the next run",
  failed: "failed; retried on the next run",
  skipped: "skipped: another run was active",
};

// Short provider names for tournament rows and filters, keyed by source id.
export const PROVIDER_LABEL: Record<string, string> = {
  tournamentsoftware_ba: "Badminton Australia",
  tournamentsoftware_bnz: "Badminton New Zealand",
  tournamentsoftware_scotland: "Badminton Scotland",
  tournamentsoftware_dbv: "Germany (DBV)",
  tournamentsoftware_obv: "Austria (ÖBV)",
  tournamentsoftware_cbbd: "Brazil (CBBd)",
  tournamentsoftware: "Tournament Software (global)",
  tournamentsoftware_bwf: "BWF (Tournament Software)",
  bwf: "BWF",
};

export type ImportState = NonNullable<
  Schemas["TournamentSummary"]["import_state"]
>;

/** A short flag for a tournament whose results we hold only in part; null when complete. */
export function importFlag(
  state: ImportState | null | undefined,
): string | null {
  if (!state || state.status === "complete") return null;
  if (state.status === "in_progress") return "In progress";
  if (state.status === "partial") return "Partial results";
  const n = state.unimported_matches;
  return `${n} match${n === 1 ? "" : "es"} missing`;
}

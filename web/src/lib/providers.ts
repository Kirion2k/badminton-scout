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

// Each source's federation and the country it governs. A tournament's place is its own field:
// the global portal hosts tournaments from many countries, so it has no single country.
export const FEDERATION: Record<
  string,
  { label: string; country: string | null; code: string }
> = {
  tournamentsoftware_ba: {
    label: "Badminton Australia",
    country: "Australia",
    code: "AUS",
  },
  tournamentsoftware_bnz: {
    label: "Badminton New Zealand",
    country: "New Zealand",
    code: "NZL",
  },
  tournamentsoftware_scotland: {
    label: "Badminton Scotland",
    country: "Scotland",
    code: "SCO",
  },
  tournamentsoftware_dbv: {
    label: "Deutscher Badminton-Verband",
    country: "Germany",
    code: "GER",
  },
  tournamentsoftware_obv: {
    label: "Österreichischer Badmintonverband",
    country: "Austria",
    code: "AUT",
  },
  tournamentsoftware_cbbd: {
    label: "Confederação Brasileira de Badminton",
    country: "Brazil",
    code: "BRA",
  },
  tournamentsoftware_england: {
    label: "Badminton England",
    country: "England",
    code: "ENG",
  },
  tournamentsoftware_canada: {
    label: "Badminton Canada",
    country: "Canada",
    code: "CAN",
  },
  tournamentsoftware_badvla: {
    label: "Badminton Vlaanderen",
    country: "Belgium (Flanders)",
    code: "BEL",
  },
  tournamentsoftware: {
    label: "Tournament Software (global)",
    country: null,
    code: "INT",
  },
  tournamentsoftware_bwf: {
    label: "BWF (Tournament Software)",
    country: null,
    code: "BWF",
  },
  bwf: { label: "BWF", country: null, code: "BWF" },
};

// Short labels for rows and filters, keyed by source id.
export const PROVIDER_LABEL: Record<string, string> = Object.fromEntries(
  Object.entries(FEDERATION).map(([id, f]) => [id, f.country ?? f.label]),
);

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

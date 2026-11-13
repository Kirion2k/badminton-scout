import { readFileSync } from "node:fs";
import { join } from "node:path";

/** Database ids of the synthetic fixture, written by `scout seed e2e` when the backend starts. */
export function ids(): Record<
  | "alex"
  | "sam"
  | "kim"
  | "jordan"
  | "jordanMergedFrom"
  | "junior"
  | "para"
  | "spring"
  | "autumn"
  | "juniorTournament",
  number
> {
  return JSON.parse(readFileSync(join(__dirname, "fixture-ids.json"), "utf8"));
}

// Names that exist only in junior or para events: they must never reach a page.
export const RESTRICTED_NAMES = [
  "Junior PERSON",
  "Junior OTHER",
  "Para ATHLETE",
];

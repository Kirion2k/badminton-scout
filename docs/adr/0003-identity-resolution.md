# ADR-0003: Player identity: immutable source players, human-approved merges

Status: Accepted (revised 2026-11-12) · Schema implemented in M2/M4, not M0

## Context
Sources identify players differently. bwf-match-data uses display names only (9,251 strings). Of 31 pairs that share the same name words, most look like one person (`KIM Yong Hyun` / `Yong Hyun KIM`), and at least one likely isn't (`Yu Chen CHANG` / `Yu-Chang CHEN`). A wrong merge silently corrupts two players' records.

## Decision

### Tables
| Table | Purpose | Key constraints |
|---|---|---|
| `source_player` | One identity as a source states it. **Immutable** after insert | `UNIQUE (source_id, source_key)`. `source_key` is the native ID, or the exact raw name when the source has none |
| `player` | Canonical person | `merged_into_id` nullable FK → `player`. A merged player is a tombstone, never deleted |
| `player_link` | Current mapping source player → canonical player | `PRIMARY KEY (source_player_id)`, so each source player maps to exactly one player. FK `player_id`, FK `decision_id` |
| `identity_candidate` | A suggested link that needs a human | `UNIQUE (source_player_a_id, source_player_b_id)` with `CHECK (a < b)`. `rule` (e.g. `case_only`, `token_order`, `id_suffix`), `status` ∈ open/accepted/rejected, `decision_id` nullable |
| `identity_decision` | Append-only audit log | `action` ∈ link/merge/split/reject. `before` and `after` JSONB snapshots of affected `player_link` rows. `reason`, `decided_by`, `decided_at` |

### Rules
- Match participants reference `source_player`, never `player`. Identity changes never rewrite match rows.
- **Automatic linking only on exact identity:** a new `source_player` whose `(source_id, source_key)` is new gets a new `player` and a `player_link` with decision action `link`, `decided_by = 'system:exact'`.
- **Candidate generation may use fuzzy rules. Candidate acceptance is human only.** No code path writes `player_link` from a fuzzy score.
- **Merge A ← B:** in one transaction, write a decision with the before/after snapshot, re-point all of B's `player_link` rows to A, and set `B.merged_into_id = A`.
- **Split:** re-point named source players to a new or revived player, with its own decision row.
- **Undo:** apply the `before` snapshot of a decision, recorded as a new decision. History is never edited.
- API lookups of a merged player follow `merged_into_id` and redirect.

## Rejected
- Automatic fuzzy or embedding-based merging (see Context).
- Matches referencing `player` directly: a merge would then rewrite history and a split couldn't be done cleanly.

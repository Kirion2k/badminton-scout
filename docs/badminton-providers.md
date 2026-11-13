# Badminton provider feasibility (M1A, 2026-11-12)

What badminton data we could obtain, through API Anything or otherwise, and what blocks each source. Rights policy: `data-sources.md`. Operation stages: ADR-0007.

**Checked this session:** robots.txt of every host below, and the API Anything shared catalog searched by **words only** (`badminton`, `bwf`, `tournament software`, `shuttlecock`, `sports rankings`). Domains were not searched, because the catalog publicly records unmatched domain searches as demand. The catalog has **no badminton operations**. Its only sports sites are ESPN and Flashscore (football only).
**Not checked:** content pages of any badminton site (no permission), terms of service (BWF: 403; Tournament Software: cookie wall; federation sites: unread).

## Status after M1B (2026-11-12, authorisations recorded per ADR-0008)

| Source | Status | Evidence | Remaining dependency |
|---|---|---|---|
| **ba.tournamentsoftware.com** | **Working**: `tournament_search`, `match_days`, `matches_in_day`. 12 recent tournaments imported (about 3,800 matches, 1,325 players). 2 tournaments are login-restricted, and 2 international ones publish no matches on the BA portal | 3 tournaments used in learning and validation. 2 imported: 531 matches, 351 players, 0 rejects, re-import idempotent. 438/438 fields verified | Confirm Badminton Australia's consent covers redistribution (junior events contain minors) |
| www.tournamentsoftware.com | **Connected, importing (M3.1, 2026-11-12).** Operations `tournamentsoftware_www.find_badminton`, `.match_days`, `.matches_in_day` are registered under source `tournamentsoftware` (tier 1). Discovery via `DoSearch` with `SportID=2`; each tournament's owner is resolved by one no-redirect `GET /tournament/{guid}` on `www.` only. Two `www.`-owned tournaments imported (1,203 matches, all normalised) | Keep importing within the 300/day budget; tournaments owned by `bnz.`, `obv.`, `cbbd.` etc. stay unauthorised |
| bwf.tournamentsoftware.com | Blocked: the root redirects to `/user/login` | One request, 2026-11-12 | An authorised account or access method from BWF / Visual Reality. We do not get around logins |
| **bwfbadminton.com** | **Blocked**: plain HTTP gets a Cloudflare JavaScript challenge (HTTP 403, "Just a moment…") | One request to `/tournament/5284/al-ain-masters-2025`, 2026-11-12 | An authorised access method from BWF: an API or feed, an allowlisted client or token, or written approval to use a real browser (tier 3, which needs its own ADR). We do not solve or get around challenges |
| Wikidata | Supporting identity source, not started | CC0 | Owner grant (unchanged from M1A) |

## Original M1A assessment (superseded where it conflicts with the table above)

## Ranking

| # | Source | Usefulness | Permitted access | Technical feasibility | Expected reliability | Verdict |
|---|---|---|---|---|---|---|
| 1 | **Wikidata** (`wikidata` bundled spec) | Medium: player identity anchor (DOB, country, occupation), to tell apart players whose names collide | **Strong evidence:** structured data is CC0. Entity pages `/wiki/Q…` allowed by robots. `/w/api.php` (search) **disallowed** by robots, though Wikimedia's API policy invites API clients | High: bundled spec verified upstream 2026-11-01, tier 1, no login | High | **First integration**, once you approve the grant (see below) |
| 2 | **BWF** (bwfbadminton.com) | Highest: World Tour calendar, results, draws, rankings, player profiles, numeric player and tournament IDs | **Unknown.** robots.txt allows everything except `/24-live-blog/`. T&Cs **unread** (403). Exclusive commercial data deals exist (Stats Perform) | Unknown until a stage-1 capture, which needs `LOCAL_RESEARCH` evidence first | Unknown | **First core integration** when permission arrives |
| 3 | Licensed feeds (BWF Data Hub, Stats Perform, Sportradar for Badminton Europe, Datasports Group) | High | Yes, by contract | High: official APIs, no API Anything needed | High | Fallback if BWF declines. Cost unknown |
| 4 | Tournament Software (bwf., ba., www.) | Very high for amateur and university play: the only source | **No:** robots.txt disallows `/player/`, `/profile/`, `/player-profile/`, `/ranking/`, `/head-2-head`, `/match-info/` and `/sport/` on all three hosts. Personal data, possibly of minors | Not attempted | n/a | **Blocked pending a data agreement** (Visual Reality / Badminton Australia) |
| 5 | Federation sites (badminton.org.au, badmintoneurope.com, badmintonengland.co.uk) | Low: news and calendars. Results link out to Tournament Software | robots.txt permissive. T&Cs unread | Unknown | Unknown | Not worth an operation yet |
| — | bwf-match-data (CSV) | High historical depth | **No granted use** | Not an API Anything target | Static | Blocked (ADR-0002) |
| — | ShuttleSet | CV and tactics research | MIT repo; whether that covers the annotations is unconfirmed | Static files | Static | Not for acquisition |

## Capability matrix

`–` means the source doesn't offer it. Every API Anything operation listed is **not learned** unless marked otherwise.

| Capability (user feature) | Best source | Official API? | API Anything op | Auth | Update frequency [assumption] | Proposed normalized target |
|---|---|---|---|---|---|---|
| Player lookup (search, UC1) | Wikidata identity; BWF profile | Wikidata yes; BWF none documented | Wikidata `searchEntities` **bundled** (robots question). BWF none | none | rarely changes | `source_player(source='wikidata', source_key=Q-id)` linked to a canonical player by human decision (ADR-0003) |
| Player facts (DOB, country) | Wikidata | yes | Wikidata `getEntity` **bundled** | none | rarely changes | attributes on `source_player`, raw revision kept |
| Rankings | BWF | none documented | none | none expected | weekly | `ranking_entry(source, as_of_week, discipline, rank, points, source_player_id)`, raw revisioned |
| Tournament discovery | BWF calendar | none documented | none | none expected | weekly | `tournament(source, source_key=BWF tournament id, name, dates, tier, country)` |
| Tournament details | BWF tournament page | none documented | none | none expected | per event | as above |
| Match results (UC2) | BWF results; licensed feed | feeds yes | none | none expected | daily during events; corrections later | `raw_record` with locator key (ADR-0005), then `match` + `match_side` + `game` |
| Draws | BWF draws; Tournament Software (blocked) | feeds yes | none | none expected | per round | `draw_slot(tournament, event, round, position, source_player_id)` |
| Head-to-head (UC4) | **Derived** from our match table | n/a | not needed | n/a | n/a | computed. Never fetched (`/head-2-head` is robots-disallowed on Tournament Software) |

Data-quality concerns for every web source:
- display names change across eras (see the bwf-match-data profile in the kickoff report);
- retirements and walkovers are often not annotated;
- results get corrected after publication, which revisions handle;
- doubles pairs need per-player identity.

## Decision: first badminton integration

**Now (needs your approval of one grant): Wikidata `getEntity` as `wikidata.player_entity`.**
- It is the only badminton-relevant source with strong evidence for every use (CC0) and a robots-allowed path.
- It fills a real gap: telling apart players whose names collide (ADR-0003 candidates).
- It goes through the full pipeline today, `fetch` → `record_payload` → revisions, because CC0 permits `STORE`.

Approving it means two edits:
- an entry in `scout.sources.SOURCES` for `wikidata` granting all uses, with evidence "Wikidata structured data is CC0: wikidata.org/wiki/Wikidata:Licensing";
- a decision on whether Wikimedia's API policy may stand in for robots.txt on `/w/api.php`, so that `searchEntities` can be used too. Without that, only `getEntity` by known Q-id is used.

**Next, when permission arrives: BWF `tournament results` by BWF tournament id** (stages 1 → 3 in ADR-0007). It is the root of the MVP's match history, and tournament IDs are already visible in BWF's URLs.

Neither is integrated or tested live today: one waits on your grant decision, the other on BWF.

## Tournament Software badminton filter (investigated 2026-11-12, M3)

- `https://www.tournamentsoftware.com/find?…&SportID=2…` renders only the search **form**. Results load through **`POST /find/tournament/DoSearch`**, with form fields `Page`, `TournamentExtendedFilter.SportID`, `TournamentFilter.Q`, `TournamentFilter.DateFilterType`, `TournamentFilter.StartDate`, `TournamentFilter.EndDate` and more. The 5 tournament links on the `/find` page itself are the site's **LiveScore menu**, not results.
- **`SportID=2` is mostly, not only, badminton.** 20 results for 2025-08-10 → 2025-11-14, and the date window is respected. *Correction (M3.1):* an earlier note said 9 of 10 results carried a "Badminton" label; they do not. Result tags are levels and ages, and the earlier match was on names. `SportID` 1 and 3 return no results for the same window (inconclusive). Imports showed `SportID=2` also returns other sports (a lawn bowls and a footbag championship); their match pages do not have the badminton markup, the import fails with drift and stores nothing, and a score-plausibility check (`implausible_badminton_score`) rejects any non-badminton score that does parse.
- **Search results are not hosting.** A tournament found on `www.` belongs to one portal, and `www.` redirects to it (302):

| Tournament (sample) | Owner | Reachable for us |
|---|---|---|
| TOYOTA Thailand International Series 2025 | `bwf.tournamentsoftware.com` | No: login wall (credentials pending) |
| WBA Singles Ladder 2025 | `bnz.tournamentsoftware.com` | **No: host not in the authorisation** |
| 第125回小金井市バドミントン大会 (Koganei, JP) | `www.` | Yes |
| Yonex Sunrise Gujarat State Championships 2025 | `www.` | **Yes: matches retrieved and normalised** |

- **Next:** a `findTournaments` read operation over the `DoSearch` POST, which needs `--match method=POST`, learned in the documented workflow. Use its results only for tournaments `www.` owns, and route the rest to their owning source. Hosts like `bnz.` need their own recorded authorisation first (ADR-0008 §2).
- Requests used: 7 for this investigation (`www.` ledger), plus 2 verification calls.

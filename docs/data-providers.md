# BWF fixtures and results: provider comparison (M8.2, 2026-11-15)

**Purpose:** a legitimate stream of *upcoming* BWF singles fixtures and *verified* results, so
forecasts can be recorded before matches and scored after (ADR-0013). Fixtures before matches
matter most: historical scores alone cannot produce prospective evidence.

**How this was checked:** read-only, from public pages; nothing was registered, bought or
retried. Anything not confirmed by the provider in writing is marked **unverified**.

## Comparison

| | BWF Data Hub | Stats Perform | Sportradar | Curated bridge |
|---|---|---|---|---|
| **What it is** | BWF's data platform, built by PASS Consulting for BWF's clients (tournament hosts, member associations, "sports portals and apps") [1] | Announced as BWF's **exclusive** distributor of live streams and real-time data, 5 years from Jan 2022 [2] | Commercial sports data vendor; documented Badminton API v2 [3] | An operator enters fixtures and results by hand from bwfbadminton.com |
| **Access today** | **None.** `extranet-api.bwf.sport` returns 403 to a plain request; no public docs. Needs BWF to provision us | None; commercial | Trial needs registration (not done: owner decision) | **Available now** |
| **BWF World Tour coverage** | All BWF-sanctioned events (by design) [1] | All four World Tour levels, World Championships, team events, Super 100, Finals [2] | **Unverified.** "All major men's and women's competitions … singles and doubles" [3]; the coverage matrix needs a session; its documented deal is Badminton Europe (35+ European events) [4] | Whatever the operator enters |
| **MS / WS singles** | Expected (unverified) | Yes [2] | Claimed [3] | Yes |
| **Upcoming fixtures** | Expected: hosts publish draws through it (unverified) | Live data product; fixtures expected (unverified) | Documented: `not_started`, `unseeded_fixture` statuses, daily summaries [5] | Yes, from published draws and order of play |
| **Verified results** | Official source | Official distributor | Documented; matches without live coverage stay `not_started` until results are entered [5] | Entered by one person, verified by another |
| **Player ids** | BWF ids (used on bwfbadminton.com) | Unknown | Sportradar competitor ids; merge mappings feed [3] | BWF profile id from the page URL, when shown |
| **Match ids** | BWF match ids (the public site's API used them) | Unknown | Sport event ids [3] | The tournament, draw and round, plus the BWF match id when shown |
| **Update frequency** | Real time (stated) [1] | "Ultra-fast" / real time [2] | Live deltas every 10 s (live coverage only) [3] | Manual: at least once before each day's play |
| **Historical backfill** | Expected (unverified) | Unknown | At most 3 seasons per competition [3] | None |
| **Storage and display** | Covered by BWF's attested grant: all uses (agreement not on file) | Commercial terms, unknown | **Trial:** internal evaluation only, no commercial use. **Paid:** an order form, display only on listed properties, "powered by Sportradar" attribution, no competing products. **On termination:** licensed data **and derivatives** destroyed within 30 days [6] | BWF's attested grant; read by a person from the in-scope host |
| **Use to evaluate our ratings** | Covered by the grant (all uses) | Unknown | Terms bar using Sportradar's models or outputs to train models [6]. Using match data for our own ratings is not addressed; needs written confirmation | Yes |
| **Estimated cost** | Unknown; possibly none for authorised users | Commercial; unknown | No public price. A competitor claims $10,000+/month (**unverified**) [7] | Operator time: roughly 300 recurring World Tour singles players to link once, then a few minutes per tournament day |
| **Prerequisites** | BWF provisions credentials or an allowlist, plus API docs; the host is added to scope | Contract | Contract; our data rights don't extend to it | None |
| **Implementation** | Low once documented: a tier-1 provider adapter on the shared pipeline | Unknown | Medium: a REST adapter; the termination clause conflicts with permanent evidence | Done (`scout fixtures import`) |

## Recommendation
1. **BWF Data Hub,** under the authorisation BWF already gave. Ask BWF to provision it
   (`docs/bwf-data-hub-request.md`). This is the official source, with stable BWF ids.
2. **If BWF says the data must come through Stats Perform** (the announced exclusive
   distributor), send a written commercial enquiry for a non-betting fixtures and results feed
   that allows permanent storage of results and our own forecasts.
3. **Meanwhile, the curated bridge,** so the operational pilot can start: real fixtures entered
   before play, results verified by a second person.
4. **Sportradar is not pursued** (owner decision, 2026-11-15):
   - its World Tour coverage is unverified;
   - BWF's announced exclusive deal is with Stats Perform;
   - the termination clause (data and derivatives destroyed) conflicts with permanent evidence.

## Sources
1. PASS Consulting, "Data center for the Badminton World Federation":
   https://www.pass-consulting.com/en/news/data-center-for-the-badminton-world-federation/
2. iGaming Business, "Stats Perform scores exclusive streaming and data deal with Badminton World
   Federation" (20 July 2021):
   https://igamingbusiness.com/stats-perform-scores-exclusive-streaming-and-data-deal-with-badminton-world-federation/
3. Sportradar Badminton API overview:
   https://developer.sportradar.com/badminton/reference/badminton-overview
4. SportBusiness, "Badminton Europe signs comprehensive data and OTT deal with Sportradar":
   https://sportbusiness.com/news/badminton-europe-signs-comprehensive-data-and-ott-deal-with-sportradar
5. Sportradar Badminton FAQ: https://developer.sportradar.com/badminton/reference/badminton-faq
6. Sportradar terms and conditions (§2, §3.2, §5, §7.4):
   https://developer.sportradar.com/terms-and-conditions
7. SharpAPI, "Sportradar alternative" (a competitor's claim, unverified):
   https://sharpapi.io/compare/sportradar-alternative

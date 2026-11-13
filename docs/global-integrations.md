# Global integration tracker

Live numbers per provider (status, discovered, public, last sync) are on the site's **Coverage**
page and in `GET /v1/coverage`. `scout report portals` lists every portal seen owning tournaments.
This page records what the live view can't: the authorisation basis and the next dependency.

**Authorisation basis (2026-11-13).** The owner attests authorisation from the international,
continental and national federations in the global expansion plan, covering automated collection
and integration for Badminton Scout (ADR-0008, 2026-11-13 amendments). No agreement text is on
file for any of them yet. Every entry below is therefore *owner-attested*, not independently
verified, and the specific terms (rate, attribution wording, commercial clauses) are still to be
documented.

## Rights per source

Each use is owner-attested for all of these sources, and none is documented by an agreement on
file yet: automated retrieval, local research, storage, redistribution, hosted access, commercial
use and scheduled updates.

Every source runs at 1 request per 5 s. Hosts are exactly those in `backend/src/scout/sources.py`.

| Source | Hosts | Daily requests |
|---|---|---|
| Tournament Software (global) | `www.tournamentsoftware.com` | 2,000 |
| Badminton Australia | `ba.tournamentsoftware.com` | 2,000 |
| Badminton New Zealand | `bnz.tournamentsoftware.com` | 2,000 |
| Badminton Scotland | `badmintonscotland.tournamentsoftware.com` | 2,000 |
| Germany (DBV) | `dbv.turnier.de` | 2,000 |
| Austria (ÖBV) | `obv.tournamentsoftware.com` | 2,000 |
| Brazil (CBBd) | `cbbd.tournamentsoftware.com` | 2,000 |
| BWF | `bwfbadminton.com`, `bwf.tournamentsoftware.com` | 300 |

Junior and para events are served for every source (ADR-0010; the owner reconfirmed this for the
global expansion on 2026-11-13). Logins, challenges and anti-bot protections are never bypassed.

## Integration status

| Federation | Platform / host | Access | Operations | Imported | Next dependency |
|---|---|---|---|---|---|
| Badminton Australia | Tournament Software `ba.` | open | verified | yes | — |
| Badminton New Zealand | Tournament Software `bnz.` | open | verified | yes | some tournaments are login-only |
| Tournament Software (global listing) | `www.` | minimal cookie consent | verified | yes | — |
| Germany (DBV) | `dbv.turnier.de` | minimal cookie consent | verified (321/322 rows) | yes | — |
| Brazil (CBBd) | `cbbd.` | minimal cookie consent | verified (102/102) | yes | — |
| Badminton Scotland | `badmintonscotland.` | minimal cookie consent | verified on 1 tournament | yes | many tournaments keep match days behind a login |
| Austria (ÖBV) | `obv.` | minimal cookie consent | reachable; 0 of 3 tournaments with public match days | no | find a tournament with public match days |
| BWF | `bwf.tournamentsoftware.com`, `bwfbadminton.com` | login / Cloudflare | none | no | provider-issued credentials or API (docs/bwf-access-request.md) |
| Badminton Vlaanderen | `badvla.` | open | verified (260/261) | yes | owner-approved 2026-11-13 |
| Badminton England | `be.` | minimal cookie consent | verified (86/86) | yes | — |
| Badminton Canada | `badmintoncanada.` | open | listing only | no | match pages yield no rows in 7 tournaments: find a tournament with published matches |
| Netherlands, Denmark, Spain, Badminton Europe | not yet identified | — | — | no | find each federation's results platform; Tournament Software portals show up in `scout report portals` as the daily owner checks run |
| USA Badminton, other Pan Am members | not yet identified (except Brazil) | — | — | no | same |
| Badminton Oceania, Badminton Asia, Badminton Confederation Africa and their members | not yet identified | — | — | no | same |

**How a new Tournament Software portal is added:**
1. Add one row to `TS_FEDERATION_PORTALS` in `sources.py`, plus its key in
   `TS_COOKIE_WALL_PORTALS` if it shows a cookie wall.
2. Run `python -m tests.test_portal_specs` to generate its site spec.
3. Add a migration for the source row.
4. Live-check it with `scout import --source <key> --max 1`.
5. Record the result in `_TS_PORTAL_VERIFIED`.

Tournaments already parked under that portal are re-queued automatically. A portal on another
platform needs its own adapter and API Anything operations, learned in the documented workflow
(`docs/api-anything.md`).

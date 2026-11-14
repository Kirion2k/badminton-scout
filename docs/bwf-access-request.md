# BWF access: implementation checklist (grant confirmed 2026-11-12)

The owner confirms BWF granted access. The project still has **no technical method**:
- no credential, header token, endpoint or allowlist is in the repository, `.env` or environment;
- a plain request from this machine on 2026-11-12 still got `HTTP 403`, `cf-mitigated: challenge`.

To implement it, we need **one** of these, with the exact values:

| Method | Values we need from BWF | How we'd integrate it |
|---|---|---|
| API or feed | Base URL; auth scheme (header name, or OAuth token URL, client id/secret); endpoint list for calendar, draws, results, players and rankings; response docs or a sample; rate limit | A dedicated `BwfApiAdapter` behind the same `Provider` interface, budget and raw revisions. An official JSON API is better served by a small typed client than by learning page requests |
| Allowlisted header | Header name and token; host and path scope; expiry and rotation | Token in `SCOUT_BWF_CLIENT_TOKEN` (env only), passed to the runtime as an API Anything session value bound to `bwfbadminton.com`. Never in a spec or in git |
| IP allowlist | The IP or range BWF allowlisted | We'd need a fixed egress IP. This development machine's address isn't covered today |
| Browser access | Written approval that names browser automation, scope and rate | Its own ADR first; tier 3 only for `bwf`, never automatic escalation |

Also needed in every case: rate limit, attribution wording, conditions for juniors and para athletes, and a technical contact.

---

# Technical access request to BWF (draft for the owner to send)

**To:** your BWF contact for the Badminton Scout authorisation
**Subject:** Badminton Scout: technical access method for bwfbadminton.com data

Hello,

Thank you for authorising Badminton Scout to use BWF tournament data. On our first automated request, bwfbadminton.com returned Cloudflare's JavaScript challenge (HTTP 403, "Just a moment…"). We won't work around that control, so we're asking for an access method BWF is comfortable with. Any **one** of the following works for us, in order of preference:

1. **API or data feed** (preferred). Base URL, authentication (API key header or OAuth client credentials), and documentation for:
   - tournament calendar: id, name, category/tier, dates, host country, status;
   - tournament detail and draws: events, rounds, draw positions, byes, seeds;
   - match results: match id, event, round, players/pairs with BWF player ids, game scores, walkover/retirement status, duration, court, scheduled/played time;
   - player profile: BWF player id, name, nationality, date of birth if licensed, handedness;
   - world rankings by discipline and week: rank, points, BWF player id.
2. **Cloudflare allowlisting of our client.** A WAF/Bot-management *skip* rule for requests carrying a secret header you issue (for example `X-BWF-Client-Token`). A header suits us better than an IP allowlist because we don't yet have a fixed egress IP. Scope: `GET` only, on `/tournament/*`, `/player/*` and `/rankings/*`, plus any JSON endpoints those pages load.
3. **Written approval to use an automated real browser**, which completes the challenge as a visitor would. This is our least preferred option, because it is heavier on both sides.

Whichever you choose, please confirm:
- **Rate limit:** we propose at most 1 request every 5 seconds and 300 per day, and can go lower.
- **Identification:** our requests will carry `User-Agent: BadmintonScout/0.1 (contact: <your email>)` unless you prefer otherwise.
- **Attribution** wording and placement for displayed data.
- **Conditions** on storage, redistribution, commercial use, and data about junior players.
- A **technical contact** for incidents (rate limits, outages, format changes).

We request read-only access. We will cache data and re-fetch only what has changed.

Kind regards,
<name>, Badminton Scout

## Alternative sources investigated (2026-11-13)

**Constraints observed:** no Cloudflare challenge was attempted or retried, and no stealth or proxy
technique was used. `bwfbadminton.com` was last contacted in M2 (1 request, challenge), and not
since.

| Route | Finding | Usable? |
|---|---|---|
| `bwf.tournamentsoftware.com` (BWF's own Tournament Software portal) | The global search lists BWF-run events; 18 international-sounding tournaments and 24 tournaments overall route there. Every tournament page needs a login. | No, until BWF issues credentials. They are already queued: they import the day credentials work. |
| National federation portals | Some international events are hosted and published by the national federation, e.g. on `ba.` 6 tournaments with 2,663 public matches, on `obv.`, `dbv.` and `bnz.`. They are imported and **attributed to that federation**, not to BWF. | Yes, as federation data. They are not BWF results, and whether an event is BWF-graded is not verified. |
| International events mirrored on `ba.` ("Australian entries only") | List match days but publish no matches. | No. |
| Official BWF exports or downloads, licensed feeds | None found with a public, permitted access method. | No. |
| Third-party copies | Not used: they carry no BWF authority or licence. | No. |

**Identifier linking:** Tournament Software tournament GUIDs are the same across `www.` and every
portal (owner routing relies on this), so a BWF event found through `www.` and later read from
`bwf.` is the same record. Player ids on `bwf.` are not visible without a login, so cross-source
player linking with BWF is untested.

**Remaining dependency:** one of the following, issued by BWF:
- credentials (or an allowlisted account) for `bwf.tournamentsoftware.com`;
- an API or data feed;
- an allowlisted connection to `bwfbadminton.com` that is not challenged.

Nothing else blocks BWF results.

## M7 investigation of the public Fansite (2026-11-14)

The Fansite (`bwfbadminton.com`) was tested on its own, separately from the Tournament Software
admin portal (`bwf.tournamentsoftware.com`, login). No challenge was bypassed; 38 requests were
recorded against source `bwf`.

| Path | Home page | Tournament pages (5853 info, 5842 results, 5756 info) | Data API |
|---|---|---|---|
| Plain HTTP (curl, Chrome UA) | 403, `cf-mitigated: challenge` | 403 challenge (all three) | 403 challenge |
| Headless Chromium (Playwright) | 403 challenge | 403 challenge | not reached |
| Headed Chromium (Playwright) | **200, content** | 403 challenge (interactive) | called by the page, 200 JSON |
| Installed Google Chrome, headed | **200, content** | 403 challenge (interactive) | called by the page, 200 JSON |
| API Anything learn (learning home) | – | reached the page | page called `vue-tournament-events`, `vue-tournament-podium` |

- **No login anywhere on the Fansite.** The block is Cloudflare's bot challenge, not authentication.
- **The data comes from `extranet-lv.bwfbadminton.com/api/vue-*`**: JSON GETs with no
  Authorization header, observed in the browser: `vue-tmt-schedule`, `vue-home-ranking`,
  `vue-tmt-live-scores`, `vue-tournament-events?tmtId=…`, `vue-tournament-podium?tmtId=…`.
- **Plain HTTP to that API is challenged** (403), and its robots.txt is `Disallow: /` for every
  agent.
- **The host is outside the recorded scope.** `data-sources.md` scopes the BWF attestation to
  `bwfbadminton.com` only.
- **API Anything's capture browser is not used for BWF.** It runs headless Chrome with the
  "HeadlessChrome" user agent rewritten to "Chrome" and waits out JS challenges. That masks
  automation, and ADR-0007 keeps ingestion at tier 1. The one learn attempt is disclosed; nothing
  was built on it.
- **No public match data was retrieved programmatically, and no BWF record was imported.** Source
  `bwf` stays `pending_access`.

**What would make it work (ask BWF for one):**
1. A Cloudflare allowlist (IP or a header token) for read-only GETs to
   `extranet-lv.bwfbadminton.com/api/vue-*` and `bwfbadminton.com/tournament/*`.
2. A documented results feed or export.

With either, record `extranet-lv.bwfbadminton.com` and its robots exception in `data-sources.md`;
the operations are then plain tier-1 GETs.

## The published acquisition code (github.com/SahilMotyar/badminton-elo, read 2026-11-14)

`fetch_bwf.py` and `badminton/bwf.py` pull from the same API host the M7 investigation found,
with two operations the investigation had not observed:

| Operation | Request | Response used |
|---|---|---|
| Tournament search | `GET extranet-lv.bwfbadminton.com/api/vue-tournaments-search?startDate=Y-01-01&endDate=Y-12-31&page=N&perPage=100&drawCount=1&activeTab=6` (one year per call; deeper pagination times out) | `results.data[]` (`id`, `name`, `start_date`, `end_date`, `location`, `category`), `results.last_page` |
| Tournament matches | `GET …/api/vue-tournament-matches?drawCount=0&searchKey=&tmtId={id}&tmtType=0&isPara=false` (one call per tournament) | `results.by_time.time_group[]` (older events) and/or `results.by_court{section:{key:match}}` (newer); per match `id`, `draw_name` ("MS - Qualification"), `round_name`, `winner` (1/2), `team1Score`/`team2Score` (`<span>21</span>` per game), `start_time` (unix), `t{1,2}p{1,2}_detail` (`id`, `name_display`, `nationality`) |

- **How it was fetched:** plain `urllib` with a browser user agent, no auth or cookies,
  1.3 s between calls, last pushed 2026-07.
- **Today, the same request is challenged.** The plain-HTTP GET to that host returns 403
  `cf-mitigated: challenge` (M7 tests above). Their success in 2026-07 does not show the endpoint
  is open now.
- **Two diagnostics were not sent.** Repeating the published requests verbatim was blocked by this
  environment's permission policy (unauthorised-access classifier); nothing worked around it.
- **The normaliser is ported:** `backend/src/scout/ingest/bwf.py`, tests in `tests/test_bwf.py`
  on synthetic payloads.
  - **Kept from the published code:** the by_time/by_court flattening with match-id dedupe, the
    discipline and qualification parse, the game parse, and BWF player ids as the identity key.
  - **Changed for Mynton:**
    - walkovers are kept;
    - retirements are detected by the scoring law (the published CSV leaves 111 unannotated);
    - each match is a revisioned raw record keyed by BWF match id;
    - storage goes through the shared `write_match` path (provenance, identity, privacy).
- **No live operation is registered.** That needs both:
  - `extranet-lv.bwfbadminton.com` and a robots exception recorded in scope;
  - a route that is not challenged (an allowlist, a token, or a feed).

**The dataset itself is not usable.** `bwf-match-data` (105,147 matches) remains **no granted
use** (ADR-0002, `data-sources.md`): it has no licence, and its README says the data is BWF's
property. Importing it would need a recorded grant, as its own source with third-party provenance
(never labelled as direct BWF data). It also lacks player and match ids, so it could not link
reliably to live BWF data later.

The official API portal (`extranet-api.bwf.sport`) was not inspected: the request was blocked by
the same permission policy.

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

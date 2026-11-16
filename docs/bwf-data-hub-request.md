# Request to BWF: provision Data Hub access for Mynton (draft for Leo to send)

**Status:** draft, 2026-11-15. Nothing has been sent by the project. Leo sends this from his BWF
contact. Background: `docs/bwf-access-request.md` (the M7 investigation) and
`docs/data-providers.md`.

---

**Subject:** Technical access for Mynton under our existing BWF data authorisation

Dear [name],

Thank you again for authorising Mynton's use of BWF tournament data (your confirmation of
2026-11-12). We would now like to put it into practice through an approved technical channel,
and would be grateful for your help with the points below.

**What Mynton does with the data:** a badminton reference site, with player results,
head-to-head records and source attribution. We are also evaluating a rating model by recording
forecasts *before* matches and checking them against official results afterwards. Nothing is
published as a prediction until that evaluation passes.

**What we are asking for**, whichever is easiest for you:
1. **Client access to the BWF Data Hub** (`extranet-api.bwf.sport`): credentials and API
   documentation. Or:
2. **An allowlist** (IP address or header token) for read-only requests to the public results
   API used by bwfbadminton.com (`extranet-lv.bwfbadminton.com/api/vue-*`). These requests
   currently receive a security challenge. We have not tried to get past it and will not.

**The data we need** (BWF World Tour and championship events, men's and women's singles first):
- upcoming fixtures once draws and the order of play are published, with scheduled start time and
  timezone;
- match status (scheduled, live, completed, walkover, retired, postponed, cancelled) and final
  results with game scores;
- stable BWF tournament, match and player ids;
- if available, historical results with player ids from 2007, so we can link our existing
  historical records to BWF ids instead of names.

**How we would access it:**
- read-only;
- at most 1 request every 5 seconds;
- at a daily volume you set;
- identified by a user agent naming Mynton and a contact address;
- credentials kept in a secrets store, never in code.

**Three questions:**
1. Which host or hosts should we record as covered by the authorisation?
2. Is there a rate limit or attribution wording you would like us to use?
3. Should this data come through BWF directly, or through your data partner (we understand Stats
   Perform distributes BWF data)? If the latter, could you introduce us?

Could you also send the authorisation in writing, if convenient, so we can keep it on file?

Kind regards,
Leo Xu, Mynton

---

**When BWF answers:**
- record the host or hosts, rate limit and attribution in `data-sources.md` and `sources.py`
  (ADR-0008);
- add a `FixtureProvider` adapter (`backend/src/scout/fixtures/providers.py`);
- keep credentials in environment variables only.

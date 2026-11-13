# ADR-0008: Provider authorisations and robots.txt exceptions

Status: Accepted 2026-11-12, amended the same day (owner confirmation, consent walls, credentials) · Amends ADR-0002 (grant evidence) and ADR-0007 (stage gates)

## Context
The project owner reports that BWF and Tournament Software have authorised automated access and every use. The written agreements are not yet on file. Tournament Software's robots.txt disallows the paths that hold its results, draws and player data.

## Decision
1. **Owner attestation is acceptable interim evidence.** It must be dated and name the provider, hosts and uses. It is replaced by the agreement text, with clauses quoted in `data-sources.md`, when that arrives.
2. **Scope is per host.** `SourceRights.hosts` lists the hosts an authorisation names. Each Tournament Software host is its own source, because identifiers and routes are not assumed to be shared. A host that isn't listed is not covered, even if it is affiliated.
3. **A robots.txt exception is explicit and scoped.** Automated access to a robots-disallowed path is allowed only on a host whose recorded authorisation says so (`data-sources.md`). It never extends to bypassing logins, challenges or other technical controls. `blocked` and `auth` results are still never retried or escalated.
4. **The budget is enforced in code.** `SourceRights.min_interval_s` and `daily_budget` are applied by `ApiAnythingProvider` per source. The default is the conservative interim budget (1 request / 5 s, 300 / day).
   - Every ingest run records its `requests` in `ingest_run.counts`. The next run starts from today's total, so the daily cap spans runs. It does not span two runs executing **at the same time**; one ingest per source at a time is the operating rule.
   - A call that comes back not-ok may make the runtime send up to about 4 more site requests we can't see: a re-send, the op's example args, a rescan, a replay. The provider charges them to the budget and delays the next request to match. The ingest command also only asks for days the tournament actually has.
   - A **healed** answer (the runtime rewrote the op to fit a changed page) is treated as drift and rejected. The reviewed spec in the repository is the contract.
5. **Tier 1 still.** Browser tiers remain out of scope for execution (ADR-0007). Learning uses API Anything's documented capture, which loads pages in a browser, inside the budget.
6. **Consent walls.** A cookie-consent interstitial is not an access control. Under an authorisation that covers the host, the integration may submit the **minimum** consent: only the purpose the site marks as required (on `www.tournamentsoftware.com`, `CookiePurposes=1`, "Basic functionality"). Never analytics, advertising or social media. It is an explicit, logged step outside API Anything's read operations, because it changes state. It never touches an account.
7. **Provider-issued credentials** (API keys, allowlist tokens, logins) come only from the provider. They are kept outside the repository (environment or OS keychain) and sent only to the hosts they were issued for. A login wall without such credentials is a blocker to report, not something to work around.
8. **Owner confirmation is settled.** The general authorisation for BWF and Tournament Software is not re-asked. Work is blocked only by a specific missing scope (a host, an access method, a rate, minors' data), and that scope is named.

## Amendment 2026-11-12 (M2 completion): consent implemented, shared budget

**Consent, as observed on `www.tournamentsoftware.com`:**
- `GET /` answers `302 → /cookiewall/`.
- The form `POST /cookiewall/Save` has no anti-forgery token. Its fields are `ReturnUrl`, `SettingsOpen` and `CookiePurposes` (1 = Basic functionality, rendered checked and *disabled*; 2 analytics, 4 ads, 16 social).
- Posting `CookiePurposes=1` answers `302 → /` and sets cookie `st` (one-year expiry) whose `cp` field records the purposes. With purpose 1 only, `cp=1`.

**Implementation** (`scout.ingest.consent`):
- Posts `CookiePurposes=1` only.
- **Refuses** unless the site recorded exactly `cp=1`.
- Imports only the `st` cookie into the runtime's session for that site, through the documented `api-anything login <site> --cookies <file>`: a 0600 temporary file, deleted immediately. **This is the only allowed use of `login`.** Importing browser cookies or accounts stays forbidden.
- Records when consent was given, and renews after 300 days.
- Session files stay **sealed** by the runtime with the macOS keychain, as this home already was. A non-interactive host (CI, ssh) needs `API_ANYTHING_KEY` set from a secret store; otherwise the runtime fails with `SealError` rather than falling back to plaintext.
- The `www.` spec pins `loginCookies: ["st"]`, so the cookie import sends **no probe request** of its own. Consent costs exactly the 2 charged requests (POST + redirect).
- If a read meets the wall again (the site cleared the cookie early), `invalidate_consent` forgets the record, so the next start re-consents.

**Budget:** §4 per-process counting is replaced by `scout.budget.LedgerBudget`.
- One `request_ledger` row per source per UTC day.
- An atomic conditional upsert enforces the daily cap and hands out pacing slots, so it holds across processes and concurrent jobs.
- `request_event` audits every charge with its purpose: ingest, discovery, learning, verification, live_test, consent, backfill.
- Requests made outside the provider (curl discovery, browser learning) are recorded with `scout budget record`. They count toward the cap without moving pacing.

## Amendment 2026-11-13 (M3.1): owner check on www.

`www.tournamentsoftware.com` search results do not say which portal owns a tournament, and the
www tournament page 302-redirects to the owner. The API Anything runtime follows cross-origin
redirects, so asking it would send a request (and the consent cookie) to the owner's host, which
may be unauthorised (`bnz.`, `obv.`, …). This is the second, and only other, direct request
besides the consent POST (§6):

- `scout.ingest.runner.www_owner_probe`: one `GET https://www.tournamentsoftware.com/tournament/{guid}`
  with redirects **not** followed. It reads the status and the `Location` host only.
- It connects only to `www.` and sends only the minimal-consent cookie `st` (cp=1). Nothing goes
  to the redirect target.
- Each check is charged to the `tournamentsoftware` ledger (purpose `owner_check`).
- A 200 means www owns it. A redirect to another host names the owner. A www-to-www hop, a cookie
  wall or an error decides nothing: the row is marked failed, or consent is renewed.
- Only `ba.` and `www.` owners are imported. `bwf.` owners are recorded as login-required, and every
  other host as unauthorised: they are recorded, never contacted.

Replace it with an API Anything operation if the runtime gains a no-redirect option.

## Amendment 2026-11-13: Badminton New Zealand portal

The owner reports that **Badminton New Zealand** granted permission on 2026-11-13 covering all
uses of its data on `bnz.tournamentsoftware.com` ("access to everything"). This is a separate grant.
The BA and Tournament Software authorisations did not imply it, and this one implies nothing for
other regional portals (`obv.`, `cbbd.`, `badmintonscotland.`, `dbv.turnier.de`, …).

- Source `tournamentsoftware_bnz`, host `bnz.tournamentsoftware.com`, at most 1 request per 5 s
  and 2,000 a day. Its operations are the `ba.` ones on the `bnz.` host, verified live.
- "Everything" is recorded as covering robots-disallowed paths, like the other Tournament Software
  hosts (§3). As always, it never covers logins, challenges or consent walls.
- Tournaments found earlier as `bnz.`-owned were re-routed from `unauthorised_host` to the queue
  (migration 0014).
- The agreement text is not on file yet. File it, or the correspondence, in `docs/data-sources.md`.

## Amendment 2026-11-13: global federation authorisation

The owner attests authorisation from the international, continental and national badminton
federations in the global expansion plan: Oceania, Europe, Asia, North and South America and
Africa, including those named in `docs/global-integrations.md`. It covers automated collection
and integration for Badminton Scout. It does not cover third-party hosts, vendors, accounts or
unrelated services linked from those sites.

- A federation's portal is added as a source only once it has been seen owning tournaments, and
  only after a live check (`TS_FEDERATION_PORTALS`, `sources.py`). Addresses are never guessed.
- A portal is covered when it belongs to a named federation or to a national federation in a named
  region. Sub-national bodies are recorded as a scope gap until the owner confirms them; the first
  is Badminton Vlaanderen.
- Portals with a cookie wall get the same minimal consent as `www.` (§6, CookiePurposes=1 only).
  Tournaments behind a login stay out.
- No agreement text is on file yet. `docs/global-integrations.md` tracks the basis and status of
  each source.

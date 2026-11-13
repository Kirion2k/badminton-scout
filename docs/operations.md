# Operations: the scheduled sync

The database is kept current by one batch job, `scout sync`, run once a day. The web app only
reads Postgres. No page load ever contacts a provider.

## What one run does

For each provider we may import from (`ba.` and `www.tournamentsoftware.com`), in turn:

1. **Lock.** It takes a Postgres advisory lock for that provider. If another sync or `scout import`
   holds it, the pass is recorded as `skipped` and nothing is requested. The lock dies with its
   connection, so a killed run never leaves it held. The next pass marks the dead run `failed`
   ("interrupted").
2. **Discover**, at most once every 20 hours. This is one listing request: BA's 60 most recent
   tournaments, or www's badminton search for the last 30 and next 14 days. New tournaments join
   the queue, and ones seen before are deduplicated by GUID. Repeating an empty search can
   therefore never use up the budget.
3. **Route owners** (www only). One no-redirect check per new tournament, up to 800 a run (ADR-0008, M3.1
   amendment). Unauthorised and login-only owners are recorded and never contacted.
4. **Refresh** ongoing and recently finished tournaments. A tournament is fetched again, at most
   once every 20 hours, until one fetch happens at least 3 days after it ended. After that it is
   *settled* and never fetched again. Refreshes use at most half of a run's tournament slots, so
the backlog always moves. Unchanged records cost a request but add no revision. A changed
   score becomes a new revision and the match is corrected (ADR-0005).
5. **Search history** (www only): up to 40 older weeks per run, working back from where the
   previous run stopped, down to 2005. The global search also lists `ba.`-owned tournaments,
   which the BA pass then imports (www runs first for that reason). A week with a full page
   of results is split in half and searched again, so nothing is cut off.
6. **Resume the queue.** Finished tournaments that are new or partly imported, adult-looking names
   first, newest first. Each match day is committed as it is done.

Every request goes through the shared ledger: at least 5 s apart, and 2,000 a day for `www.` and `ba.` (300 for other sources). When a
source's budget runs out, its pass stops, is recorded as `incomplete`, and the next run continues
from the queue. Failed tournaments (another sport's page, a block) are not retried automatically:
`scout import --retry-empty` retries them on purpose.

Each pass is a `sync_run` row: status (`succeeded`, `incomplete`, `failed`, `skipped`), counts
(discovered, refreshed, imported, rejected, failed) and the next planned run. The Coverage page
shows the last successful sync, the next scheduled one, and how many tournaments are awaiting
import.

Privacy is unchanged. Every imported event goes through the ADR-0009 allowlist, and junior and
para records are stored but never served or counted publicly.

## Running it

```sh
make sync                 # one pass now (LIVE: uses today's budget)
make schedule-install     # macOS: daily at 00:30 UTC via launchd
make schedule-remove
tail -f .tools/sync.log
```

`--every 24` (set by `tools/scheduling/sync.sh`) records when the next run is due; that is how
the site knows a schedule exists. Without it the site says "No schedule configured"; once the planned time passes with no new
run, it says the sync is overdue.

**On this Mac** `sync.sh` keeps the Mac from idle-sleeping during a run (`caffeinate -i`; closing
the lid still sleeps it), and adds the usual `node` locations (`~/.local/bin`, Homebrew) to the PATH,
because launchd starts with a bare one. The job runs only while the Mac is on and you are logged in, and Postgres must be
running (`make db-up`; Docker Desktop started). launchd runs a missed time once after the Mac
wakes, not once per missed day. If the Mac sleeps during a run, the run pauses and carries on after wake (seen in
the first live run, 2026-11-13). The plist uses local time, so the hour shifts by one at daylight
saving changes until you run `make schedule-install` again.

## On a hosted machine

Use any always-on host with Postgres and this repo installed. Run the same script from the host's
scheduler, in UTC, shortly after the budget resets:

```ini
# /etc/systemd/system/scout-sync.service
[Service]
Type=oneshot
User=scout
WorkingDirectory=/srv/badminton-scout
ExecStart=/srv/badminton-scout/tools/scheduling/sync.sh

# /etc/systemd/system/scout-sync.timer
[Timer]
OnCalendar=*-*-* 00:30:00 UTC
Persistent=true

[Install]
WantedBy=timers.target
```

Or with cron: `30 0 * * * /srv/badminton-scout/tools/scheduling/sync.sh >> /var/log/scout-sync.log 2>&1`
(with the host clock in UTC). A platform scheduler (a scheduled container or job) works the same
way: run the script once a day, with network access and the database URL.

- **More than one host** is safe. The advisory lock lets only one worker import from a provider
  at a time, and the ledger caps requests across all of them.
- **API Anything** needs its runtime and the www consent record in `.tools/api-anything-home` on
  that host. The first run there consents again (ADR-0008 §6).
- **Monitoring:** alert when the latest `sync_run` per provider is `failed`, or when there has
  been no `succeeded` or `incomplete` run for 48 hours.

Nothing here needs Redis, Celery or a queue service. The queue is the `tournament_discovery`
table, and one run a day fits easily inside the request budget.

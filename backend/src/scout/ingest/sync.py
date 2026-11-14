"""Scheduled incremental sync (M3.2): `scout sync`, run daily by cron, launchd or a systemd timer.

One pass per provider, under a per-provider Postgres advisory lock, so two workers never import
from the same provider at once. Each pass: discover (at most once a day), route owners, refresh
ongoing and recently finished tournaments until they settle, then work through the queue. Every
request goes through the shared ledger budget, so a pass stops cleanly when the day's budget is
used up and the next pass resumes from the queue.
"""

from collections import Counter
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Engine, func, select, text, update
from sqlalchemy.orm import Session

from scout.budget import BudgetExhausted
from scout.ingest.operations import OPERATIONS
from scout.ingest.provider import ApiAnythingProvider, OperationFailed, ProviderError
from scout.ingest.runner import (
    CookieWall,
    Portal,
    Probe,
    discover,
    import_queue,
    import_tournament,
    reroute_parked,
    resolve_owners,
)
from scout.models import SyncRun, TournamentDiscovery

# A listing search costs one request but rarely changes within a day.
DISCOVER_EVERY = timedelta(hours=20)
DISCOVERY_PAGES = 3  # 60 most recent listings per portal
# Corrections arrive in the first days after a tournament. One fetched this long after its end
# is settled and never fetched again by the scheduler.
SETTLE_AFTER = timedelta(days=3)
REFRESH_EVERY = timedelta(hours=20)
REFRESH_LOOKBACK = timedelta(days=30)
# One request each, and each routes a tournament to its portal's own import budget (ba., bnz.)
OWNER_CHECKS = 4_000  # the budget stops it first; at 6,000 a day the backlog clears in a day
# History: each www pass also searches older weeks, back from where the last pass stopped. The
# www search is global, so it finds tournaments owned by ba. as well (routed to the BA source).
BACKFILL_FLOOR = date(2005, 1, 1)  # Tournament Software's results do not go back further
BACKFILL_WINDOW = timedelta(days=7)
# a national portal lists one federation, so a month rarely fills a search: four weeks a window
PORTAL_BACKFILL_WINDOW = timedelta(days=28)
BACKFILL_SEARCHES = 40  # windows per pass: about nine months of history a day
BACKFILL_PAGES = 15  # up to 300 listings per search; a full answer is split, never cut off


@contextmanager
def provider_lock(engine: Engine, source_id: str) -> Generator[bool]:
    """True while this process holds the provider's lock; False if another worker has it. The
    lock dies with the connection, so a killed worker never leaves it held."""
    with engine.connect() as conn:
        key = f"scout-sync:{source_id}"
        held = bool(conn.scalar(text("SELECT pg_try_advisory_lock(hashtext(:k))"), {"k": key}))
        conn.commit()  # the lock is session-level: don't sit idle in a transaction for the pass
        try:
            yield held
        finally:
            if held:
                conn.execute(text("SELECT pg_advisory_unlock(hashtext(:k))"), {"k": key})
            conn.commit()


def refresh_due(session: Session, source_id: str, now: datetime) -> list[TournamentDiscovery]:
    """Ongoing or recently finished tournaments not yet settled, oldest attempt first."""
    today = now.date()
    rows = session.scalars(
        select(TournamentDiscovery).where(
            TournamentDiscovery.owner_source == source_id,
            TournamentDiscovery.status.in_(
                ["new", "partial", "not_finished", "complete", "no_matches"]
            ),
            TournamentDiscovery.start_date <= today,
            TournamentDiscovery.end_date >= today - REFRESH_LOOKBACK,
        )
    ).all()

    def due(r: TournamentDiscovery) -> bool:
        last, end = r.last_attempt_at, r.end_date or today
        if end < today and r.status in ("new", "partial"):
            return False  # finished, never fully imported: the queue's job, not a refresh
        settled = last is not None and last.date() >= end + SETTLE_AFTER
        return not settled and (last is None or now - last >= REFRESH_EVERY)

    return sorted(
        (r for r in rows if due(r)),
        key=lambda r: r.last_attempt_at or datetime.min.replace(tzinfo=UTC),
    )


def sync_provider(
    engine: Engine,
    session: Session,
    provider: ApiAnythingProvider,
    portal: Portal,
    *,
    probe: Probe | None = None,
    max_tournaments: int = 25,
    next_run_at: datetime | None = None,
) -> SyncRun:
    """One scheduled pass over one provider. Never raises for source trouble: the outcome is
    recorded on the returned `SyncRun` (succeeded, incomplete, failed or skipped)."""
    run = SyncRun(source_id=portal.source_id, next_run_at=next_run_at)
    session.add(run)
    session.commit()
    counts: Counter[str] = Counter()
    with provider_lock(engine, portal.source_id) as held:
        if not held:
            run.status, run.note = "skipped", "another worker holds this provider"
            return _finish(session, run, counts)
        # we hold the lock, so any other 'running' pass for this provider died mid-way
        session.execute(
            update(SyncRun)
            .where(SyncRun.source_id == portal.source_id, SyncRun.status == "running")
            .where(SyncRun.id != run.id)
            .values(status="failed", note="interrupted", finished_at=datetime.now(UTC))
        )
        session.commit()
        try:
            counts += _pass(session, provider, portal, run, probe, max_tournaments)
            run.status = "incomplete" if _stopped(counts) else "succeeded"
        except BudgetExhausted:
            session.rollback()
            counts["stopped:budget_exhausted"] += 1
            run.status = "incomplete"
        except CookieWall:
            session.rollback()
            run.status, run.note = "failed", "cookie wall: consent must be renewed"
            _finish(session, run, counts)
            raise  # the caller renews consent
        except ProviderError as e:
            session.rollback()
            run.status, run.note = "failed", str(e)[:300]
        except Exception as e:
            session.rollback()
            run.status, run.note = "failed", f"unexpected {type(e).__name__}"
            _finish(session, run, counts)
            raise
        if run.status == "incomplete":
            run.note = "request budget used up: the next pass resumes the queue"
        if run.status != "failed":
            try:
                counts += _resolve_identities(session)
            except Exception as e:  # the import itself succeeded: keep it, note the miss
                session.rollback()
                counts[f"identity:failed:{type(e).__name__}"] += 1
        return _finish(session, run, counts)


def _pass(
    session: Session,
    provider: ApiAnythingProvider,
    portal: Portal,
    run: SyncRun,
    probe: Probe | None,
    max_tournaments: int,
) -> Counter[str]:
    counts: Counter[str] = Counter()
    if rerouted := reroute_parked(session):
        counts["rerouted_to_authorised_portals"] = rerouted
    now = datetime.now(UTC)
    recent = session.scalar(
        select(SyncRun.id).where(
            SyncRun.source_id == portal.source_id,
            SyncRun.discovered,
            SyncRun.started_at > now - DISCOVER_EVERY,
        )
    )
    if recent is None:
        run.discovered = True  # committed first: a failing search is tried once a day, not per run
        session.commit()
        try:
            found = discover(session, provider, portal, pages=DISCOVERY_PAGES)
            counts += {f"discovery:{k}": v for k, v in found.items()}
        except ProviderError as e:
            session.rollback()
            counts[f"discovery:failed:{type(e).__name__}"] += 1  # refresh and queue still run
    # owners first: a found-but-unchecked listing is the backlog; more history only adds to it
    if probe is not None:
        counts += resolve_owners(session, probe, limit=OWNER_CHECKS)
        if counts["owners:stopped_budget_exhausted"]:
            counts["stopped:budget_exhausted"] += 1
            return counts
    if has_history_search(portal):
        counts += _backfill(session, provider, portal, run)
    left = max_tournaments
    # at most half the slots: corrections must not starve the backlog
    for row in refresh_due(session, portal.source_id, now)[: max(1, max_tournaments // 2)]:
        left -= 1
        row.days_done = []  # fetch every day again: unchanged records cost no writes
        result = import_tournament(session, provider, portal, row)
        counts += {f"refresh:{k}" if k != "stopped:budget_exhausted" else k: v
                   for k, v in result.items()}  # fmt: skip
        counts["refreshed"] += 1
        if _stopped(counts):
            return counts
    if left:
        counts += import_queue(session, provider, max_tournaments=left, sources={portal.source_id})
    return counts


def has_history_search(portal: Portal) -> bool:
    """The global site and every portal whose own date search is an approved operation."""
    return portal.source_id == "tournamentsoftware" or (
        f"{portal.ops}.find_tournaments" in OPERATIONS
    )


def _backfill(
    session: Session, provider: ApiAnythingProvider, portal: Portal, run: SyncRun
) -> Counter[str]:
    """Search one week at a time back from the cursor; the cursor only moves past a week that
    was searched completely, so a stop (budget, error) resumes at the same week next time."""
    counts: Counter[str] = Counter()
    cursor = session.scalar(
        select(func.min(SyncRun.backfilled_to)).where(SyncRun.source_id == portal.source_id)
    ) or (datetime.now(UTC).date() - timedelta(days=30))  # where daily discovery begins
    for _ in range(BACKFILL_SEARCHES):
        if cursor <= BACKFILL_FLOOR:
            counts["backfill:reached_floor"] = 1
            break
        window = (
            BACKFILL_WINDOW if portal.source_id == "tournamentsoftware" else PORTAL_BACKFILL_WINDOW
        )
        start = max(cursor - window, BACKFILL_FLOOR)
        try:
            counts += _search(session, provider, portal, start, cursor)
        except ProviderError as e:
            session.rollback()
            counts[f"backfill:failed:{type(e).__name__}"] += 1
            break
        cursor = run.backfilled_to = start
        session.commit()
    return counts


def _search(
    session: Session, provider: ApiAnythingProvider, portal: Portal, start: date, end: date
) -> Counter[str]:
    # www pages are cumulative (page N lists the first 20*N); a federation portal rejects a page
    # past its results (class "input", seen 2026-11-14), so it reads page 1 and splits instead
    pages = BACKFILL_PAGES if portal.source_id == "tournamentsoftware" else 1
    try:
        found = discover(session, provider, portal, pages=pages, window=(start, end))
    except OperationFailed as e:
        if not (e.klass == "input" and "no results" in e.reason):
            raise
        # a week with no tournaments (the holiday break) is an empty answer, not a failure
        found = Counter({"listed": 0})
    counts = Counter({f"backfill:{k}": v for k, v in found.items()})
    counts["backfill:searches"] += 1
    if found["listed"] >= 20 * pages and end > start:
        # a full page may be cut off: search each half on its own
        middle = start + (end - start) / 2
        counts += _search(session, provider, portal, start, middle)
        counts += _search(session, provider, portal, middle + timedelta(days=1), end)
    elif found["listed"] >= 20 * pages:
        counts["backfill:day_over_limit"] += 1  # one day with more listings than a search shows
    return counts


def _resolve_identities(session: Session) -> Counter[str]:
    """New records may settle old doubts: re-run identity resolution (no requests, ADR-0011)."""
    from scout import identity, identity_auto

    identity.generate_candidates(session)
    report = identity_auto.resolve(session)
    session.commit()
    return Counter({f"identity:{k}": v for k, v in report.outcomes.items()})


def _stopped(counts: Counter[str]) -> bool:
    return counts["stopped:budget_exhausted"] > 0


def _finish(session: Session, run: SyncRun, counts: Counter[str]) -> SyncRun:
    run.counts = dict(counts)
    run.finished_at = datetime.now(UTC)
    session.commit()
    from scout.summary import refresh_quietly

    refresh_quietly(session)  # coverage counts follow every pass
    return run

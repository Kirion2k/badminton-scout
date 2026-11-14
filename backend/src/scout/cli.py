import argparse
import re
import shutil
import subprocess
import sys
from collections import Counter
from contextlib import ExitStack
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

if TYPE_CHECKING:
    pass

from scout.sources import SOURCES, Use


def _sources() -> None:
    for source_id, rights in SOURCES.items():
        granted = ", ".join(u.value for u in Use if u in rights.grants) or "none"
        print(f"{source_id}: {granted}  ({rights.evidence})")


def _doctor() -> int:
    """Report whether the API Anything runtime and every approved operation are usable."""
    import api_anything

    from scout.ingest.api_anything import DEFAULT_BINARY, DEFAULT_HOME, local_runtime
    from scout.ingest.operations import OPERATIONS
    from scout.ingest.provider import ProviderError

    problems = 0

    def report(ok: bool, what: str, detail: str) -> None:
        nonlocal problems
        problems += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {what}: {detail}")

    node = shutil.which("node")
    version = (
        # fixed argv, resolved path
        subprocess.run([node, "--version"], capture_output=True, text=True, check=False).stdout  # noqa: S603
        if node
        else ""
    )
    found = f"{node} {version.strip()}" if node else "not on PATH (need >= 22.13)"
    report(bool(node), "node", found)
    report(DEFAULT_BINARY.exists(), "api-anything binary", str(DEFAULT_BINARY))
    print(f"     home: {DEFAULT_HOME} (local-only, learning off)")
    if problems:
        return 1
    try:
        with local_runtime() as client:
            health = client.health()
            report(health.get("ok") is True, "runtime", f"version {health.get('version')}")
            for name, spec in OPERATIONS.items():
                ops = {o.get("name") for o in client.operations(spec.site).get("operations", [])}
                report(spec.op in ops, f"operation {name}", f"{spec.site}/{spec.op}")
    except (ProviderError, api_anything.ApiAnythingError) as e:
        report(False, "runtime", str(e))
    return 1 if problems else 0


_GUID = re.compile(r"^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_WWW_SITE = "tournamentsoftware-www"


def _portal_keys() -> list[str]:
    from scout.ingest.runner import PORTALS

    return sorted(p.key for p in PORTALS.values())


def _discover(args: argparse.Namespace) -> int:
    """Fill the import queue from a portal's tournament listing (no match requests)."""
    from datetime import date

    from sqlalchemy.orm import Session

    from scout.budget import BudgetExhausted, LedgerBudget
    from scout.db import get_engine
    from scout.ingest.api_anything import local_runtime
    from scout.ingest.provider import ApiAnythingProvider, ProviderError
    from scout.ingest.runner import PORTALS, discover

    if not 1 <= args.pages <= 50:
        print("--pages must be 1-50 (each page adds 20 tournaments)", file=sys.stderr)
        return 2
    window = None
    if args.portal == "www":
        if not (_DATE.match(args.start or "") and _DATE.match(args.end or "")):
            print("www discovery needs --from and --to as YYYY-MM-DD", file=sys.stderr)
            return 2
        window = (date.fromisoformat(args.start), date.fromisoformat(args.end))
    portal = next(p for p in PORTALS.values() if p.key == args.portal)
    budget = LedgerBudget(get_engine())
    runtime = local_runtime(sites=[portal.site], budget=budget)
    with runtime as client, Session(get_engine()) as s:
        provider = ApiAnythingProvider(client, budget=budget, purpose="discovery")
        try:
            counts = discover(s, provider, portal, pages=args.pages, window=window)
        except (ProviderError, BudgetExhausted) as e:
            print(f"discovery failed: {e}", file=sys.stderr)
            return 1
    print(f"{args.portal}: {dict(counts)}")
    return 0


def _import(args: argparse.Namespace) -> int:
    """Route owners, then import queued tournaments until the work or the budget runs out."""
    from sqlalchemy.orm import Session

    from scout.budget import LedgerBudget
    from scout.db import get_engine
    from scout.ingest.api_anything import local_runtime
    from scout.ingest.runner import PORTALS
    from scout.ingest.sync import provider_lock
    from scout.models import TournamentDiscovery

    if args.tournament and not _GUID.match(args.tournament):
        print("--tournament must be a GUID", file=sys.stderr)
        return 2
    sources = None if args.source == "all" else {
        p.source_id for p in PORTALS.values() if p.key == args.source
    }  # fmt: skip
    budget = LedgerBudget(get_engine())
    totals: Counter[str] = Counter()
    runtime = local_runtime(sites=[p.site for p in PORTALS.values()], budget=budget)
    with ExitStack() as locks:
        wanted = sources or {p.source_id for p in PORTALS.values()}
        if args.tournament:  # one tournament: only its own portal's lock
            with Session(get_engine()) as s:
                row = s.get(TournamentDiscovery, args.tournament.lower())
                wanted = {row.owner_source} if row and row.owner_source else wanted
        if not all(locks.enter_context(provider_lock(get_engine(), w)) for w in sorted(wanted)):
            print("another sync or import is running for this provider; try later", file=sys.stderr)
            return 1
        return _import_locked(args, sources, budget, runtime, totals, locked=wanted)


def _import_locked(
    args: argparse.Namespace,
    sources: set[str] | None,
    budget: Any,
    runtime: Any,
    totals: Counter[str],
    locked: set[str],
) -> int:
    from sqlalchemy.orm import Session

    from scout.budget import BudgetExhausted
    from scout.db import get_engine
    from scout.ingest.api_anything import DEFAULT_HOME
    from scout.ingest.consent import consent_cookie, invalidate_consent
    from scout.ingest.provider import ApiAnythingProvider
    from scout.ingest.runner import (
        PORTALS,
        CookieWall,
        import_queue,
        import_tournament,
        reroute_parked,
        resolve_owners,
        www_owner_probe,
    )
    from scout.models import TournamentDiscovery

    with runtime as client, Session(get_engine()) as s:
        provider = ApiAnythingProvider(client, budget=budget, purpose="ingest")
        try:
            if args.tournament:
                row = s.get(TournamentDiscovery, args.tournament.lower())
                if row is not None and row.owner_source not in locked:
                    print("the tournament's owner changed meanwhile: run again", file=sys.stderr)
                    return 1
                if row is None or row.owner_source not in {p.source_id for p in PORTALS.values()}:
                    print("not in the queue with an importable owner: run `scout discover` first",
                          file=sys.stderr)  # fmt: skip
                    return 2
                if args.renormalize:
                    # every day again; shortcut: a stopped renormalize resumes without it, rerun it
                    row.days_done = []
                portal = next(p for p in PORTALS.values() if p.source_id == row.owner_source)
                totals += import_tournament(s, provider, portal, row, renormalize=args.renormalize)
            else:
                if (sources is None or "tournamentsoftware" in sources) and args.owners:
                    cookie = consent_cookie(DEFAULT_HOME, _WWW_SITE)
                    if cookie is None:
                        # a record without the value (pre-M3.1) is renewed on the next start
                        invalidate_consent(DEFAULT_HOME, _WWW_SITE)
                        print("owner checks skipped: www consent will be renewed on the next run")
                    else:
                        try:
                            probe = www_owner_probe(cookie, budget)
                            totals += resolve_owners(s, probe, args.owners)
                        except CookieWall:
                            invalidate_consent(DEFAULT_HOME, _WWW_SITE)
                            print("owner checks stopped: the cookie wall is back; consent is "
                                  "renewed on the next run")  # fmt: skip
                totals["rerouted_to_authorised_portals"] += reroute_parked(s)
                totals += import_queue(
                    s, provider, max_tournaments=args.max, sources=sources, retry=args.retry_empty
                )
        except BudgetExhausted:
            totals["stopped:budget_exhausted"] += 1
    for name, n in sorted(totals.items()):
        print(f"  {name}: {n}")
    if totals["stopped:budget_exhausted"]:
        print("stopped: today's request budget is used up; progress is saved, run again tomorrow")
    return 0


def _sync(args: argparse.Namespace) -> int:
    """One scheduled pass per provider (see docs/operations.md). Exit 0 unless a pass failed."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy.orm import Session

    from scout.budget import LedgerBudget
    from scout.db import get_engine
    from scout.ingest.api_anything import DEFAULT_HOME, local_runtime
    from scout.ingest.consent import consent_cookie, invalidate_consent
    from scout.ingest.provider import ApiAnythingProvider
    from scout.ingest.runner import PORTALS, CookieWall, Probe, www_owner_probe
    from scout.ingest.sync import sync_provider
    from scout.models import SyncRun

    if not 1 <= args.max <= 200 or (args.every is not None and not 1 <= args.every <= 168):
        print("--max must be 1-200 and --every 1-168 hours", file=sys.stderr)
        return 2
    started = datetime.now(UTC)
    next_run = started + timedelta(hours=args.every) if args.every else None
    # www first: its search also finds older ba. tournaments, which the BA pass then imports
    portals = sorted(
        (p for p in PORTALS.values() if args.source in ("all", p.key)),
        key=lambda p: p.host != "www.tournamentsoftware.com",
    )
    engine = get_engine()
    budget = LedgerBudget(engine)
    failed = False
    runtime = local_runtime(sites=[p.site for p in portals], budget=budget)
    try:
        client = runtime.__enter__()
    except Exception as e:
        # no runtime (node missing, port in use, …): record it so Coverage shows the failure
        with Session(engine) as s:
            for portal in portals:
                s.add(SyncRun(source_id=portal.source_id, status="failed", next_run_at=next_run,
                              note=f"runtime did not start: {type(e).__name__}",
                              finished_at=datetime.now(UTC)))  # fmt: skip
            s.commit()
        print(f"runtime did not start: {e}", file=sys.stderr)
        return 1
    try:
        for portal in portals:
            probe: Probe | None = None
            if portal.source_id == "tournamentsoftware":
                cookie = consent_cookie(DEFAULT_HOME, _WWW_SITE)
                if cookie is None:
                    invalidate_consent(DEFAULT_HOME, _WWW_SITE)  # renewed on the next start
                else:
                    probe = www_owner_probe(cookie, budget)
            with Session(engine) as s:
                provider = ApiAnythingProvider(client, budget=budget, purpose="sync")
                try:
                    run = sync_provider(
                        engine, s, provider, portal, probe=probe,
                        max_tournaments=args.max, next_run_at=next_run,
                    )  # fmt: skip
                except CookieWall:
                    invalidate_consent(DEFAULT_HOME, _WWW_SITE)
                    print(f"{portal.host}: cookie wall; consent is renewed on the next run")
                    failed = True
                    continue
                except Exception as e:  # recorded as failed by sync_provider; go on to the next
                    print(f"{portal.host}: failed ({type(e).__name__}: {e})", file=sys.stderr)
                    failed = True
                    continue
                failed |= run.status == "failed"
                shown = {k: n for k, n in sorted(run.counts.items()) if "refresh:" not in k}
                print(f"{portal.host}: {run.status}{f' ({run.note})' if run.note else ''} {shown}")
    finally:
        runtime.__exit__(None, None, None)
    return 1 if failed else 0


def _portals() -> int:
    """The integration tracker's raw input: owners seen by the www owner checks (no requests)."""
    from sqlalchemy import func
    from sqlalchemy.orm import Session

    from scout.db import get_engine
    from scout.ingest.runner import LOGIN_HOSTS, PORTALS
    from scout.models import TournamentDiscovery as D

    with Session(get_engine()) as s:
        rows = s.execute(
            select(D.owner_host, D.status, func.count())
            .where(D.owner_host.is_not(None))
            .group_by(D.owner_host, D.status)
        ).all()
    seen: dict[str, Counter[str]] = {}
    for host, status, n in rows:
        seen.setdefault(host or "", Counter())[status] += n
    print(f"{'portal':45} {'access':16} tournaments by status")
    for host, statuses in sorted(seen.items(), key=lambda kv: -sum(kv[1].values())):
        access = ("authorised" if host in PORTALS
                  else "login only" if host in LOGIN_HOSTS else "NOT AUTHORISED")  # fmt: skip
        print(f"{host:45} {access:16} {dict(statuses.most_common())}")
    return 0


def _imports() -> int:
    """Completeness of every imported tournament (the same rule the site shows; no requests)."""
    from sqlalchemy import func
    from sqlalchemy.orm import Session

    from scout.api_v1 import _LOSS_KINDS, _import_states  # pyright: ignore[reportPrivateUsage]
    from scout.db import get_engine
    from scout.models import IngestIssue, Match, RawRecord, Tournament

    with Session(get_engine()) as s:
        tournaments = list(s.scalars(select(Tournament)))
        states = _import_states(s, tournaments)
        reasons = s.execute(
            select(RawRecord.source_id, IngestIssue.kind, func.count(func.distinct(RawRecord.id)))
            .join(IngestIssue, IngestIssue.raw_record_id == RawRecord.id)
            .where(
                IngestIssue.kind.in_(_LOSS_KINDS),
                ~select(Match.id).where(Match.raw_record_id == RawRecord.id).exists(),
            )
            .group_by(RawRecord.source_id, IngestIssue.kind)
        ).all()
    table: dict[str, Counter[str]] = {}
    for t in tournaments:
        state = states.get(t.id)
        table.setdefault(t.source_id, Counter())[state.status if state else "not via queue"] += 1
        if state:
            table[t.source_id]["missing matches"] += state.unimported_matches
    for source, counts in sorted(table.items()):
        print(f"{source}: {dict(counts)}")
    print("rejections of records never stored (a record can carry several over time):")
    for source, kind, n in sorted(reasons, key=lambda r: -r[2]):
        print(f"  {source:28} {kind:30} {n}")
    return 0


def _identity_report() -> int:
    """Identity quality (no requests): what was linked, why, and what remains separate."""
    from sqlalchemy import func
    from sqlalchemy.orm import Session

    from scout.db import get_engine
    from scout.identity_auto import duplicate_estimate
    from scout.models import IdentityCandidate, IdentityDecision, Player, SourcePlayer

    with Session(get_engine()) as s:
        records = s.scalar(select(func.count()).select_from(SourcePlayer)) or 0
        players = s.scalar(select(func.count()).where(Player.merged_into_id.is_(None))) or 0
        print(f"source records: {records}; players: {players}")
        actor_col = func.split_part(IdentityDecision.decided_by, ":", 1)
        for actor, action, n in s.execute(
            select(actor_col, IdentityDecision.action, func.count()).group_by(
                actor_col, IdentityDecision.action
            )
        ):
            print(f"  decisions by {actor}: {action} {n}")
        for status, note, n in s.execute(
            select(IdentityCandidate.status, IdentityCandidate.note, func.count())
            .group_by(IdentityCandidate.status, IdentityCandidate.note)
            .order_by(IdentityCandidate.status, func.count().desc())
        ):
            print(f"  candidates {status}: {n}{f' ({note})' if note else ''}")
        print(f"possible remaining duplicates (upper bound): {duplicate_estimate(s)}")
    return 0


def _coverage() -> int:
    """What is in the database, per source: synthetic test data is reported separately."""
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    from scout.db import get_engine
    from scout.models import (
        Event,
        Game,
        IngestIssue,
        IngestRun,
        Match,
        MatchSide,
        MatchSidePlayer,
        PlayerLink,
        RawRecord,
        SourcePlayer,
        Tournament,
    )

    with Session(get_engine()) as s:
        sources = s.scalars(select(RawRecord.source_id).distinct()).all()
        for source in sources:
            label = "TEST DATA" if source == "synthetic" else "source data"
            matches = select(Match.id).join(RawRecord).where(RawRecord.source_id == source)
            sides = (
                select(func.count(MatchSidePlayer.source_player_id))
                .join(MatchSide)
                .where(MatchSide.match_id.in_(matches), MatchSide.side == 1)
                .group_by(MatchSide.match_id)
            ).subquery()
            per_side = Counter(s.scalars(select(sides.c[0])).all())
            by_status = dict(
                s.execute(
                    select(Match.status, func.count())
                    .where(Match.id.in_(matches))
                    .group_by(Match.status)
                ).all()
            )
            no_games = s.scalar(
                select(func.count()).where(
                    Match.id.in_(matches),
                    Match.status == "completed",
                    ~select(Game.match_id).where(Game.match_id == Match.id).exists(),
                )
            )
            players = select(SourcePlayer.id).where(SourcePlayer.source_id == source)
            last = s.scalar(
                select(func.max(IngestRun.finished_at)).where(
                    IngestRun.source_id == source, IngestRun.status == "succeeded"
                )
            )
            # open issues: each record's latest issue, while the record still has no match
            latest = (
                select(IngestIssue.raw_record_id, IngestIssue.kind)
                .join(IngestRun)
                .where(IngestRun.source_id == source, IngestIssue.raw_record_id.is_not(None))
                .order_by(IngestIssue.raw_record_id, IngestIssue.id.desc())
                .distinct(IngestIssue.raw_record_id)
                .subquery()
            )
            issues = dict(
                s.execute(
                    select(latest.c.kind, func.count())
                    .where(~select(Match.id).where(Match.raw_record_id == latest.c[0]).exists())
                    .group_by(latest.c.kind)
                ).all()
            )
            tournaments = select(Tournament.id).where(Tournament.source_id == source)
            rows = {
                "tournaments": s.scalar(select(func.count()).where(Tournament.id.in_(tournaments))),
                "events": s.scalar(
                    select(func.count()).where(Event.tournament_id.in_(tournaments))
                ),
                "raw records": s.scalar(select(func.count()).where(RawRecord.source_id == source)),
                "matches": f"{sum(by_status.values())} {by_status}",
                "singles / doubles": f"{per_side.get(1, 0)} / {per_side.get(2, 0)}",
                "completed without game scores": no_games,
                "source players": s.scalar(
                    select(func.count()).where(SourcePlayer.id.in_(players))
                ),
                "canonical players linked": s.scalar(
                    select(func.count(func.distinct(PlayerLink.player_id))).where(
                        PlayerLink.source_player_id.in_(players)
                    )
                ),
                "open issues (records without a match)": issues or "none",
                "last successful retrieval": last,
            }
            print(f"{source} ({label})")
            for name, value in rows.items():
                print(f"  {name}: {value}")
    return 0


def _budget(args: argparse.Namespace) -> int:
    """Today's spend per source, or record requests made outside the provider (curl, learning)."""
    from sqlalchemy import func
    from sqlalchemy.orm import Session

    from scout.budget import BudgetExhausted, LedgerBudget
    from scout.db import get_engine
    from scout.models import RequestEvent
    from scout.sources import SOURCES

    engine = get_engine()
    if args.action == "record":
        if args.source not in SOURCES:
            print(f"unknown source {args.source!r}", file=sys.stderr)
            return 2
        try:  # already sent earlier: counted even past the cap; pacing untouched
            LedgerBudget(engine).charge(
                args.source, args.requests, purpose=args.purpose, note=args.note, historical=True
            )
        except BudgetExhausted as e:  # pragma: no cover - happened=True never refuses
            print(e, file=sys.stderr)
            return 1
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    with Session(engine) as s:
        rows = s.execute(
            select(RequestEvent.source_id, RequestEvent.purpose, func.sum(RequestEvent.requests))
            .where(RequestEvent.at >= today)
            .group_by(RequestEvent.source_id, RequestEvent.purpose)
            .order_by(RequestEvent.source_id)
        ).all()
    for source_id in sorted({r[0] for r in rows}):
        spent = LedgerBudget(engine).spent(source_id)
        cap = SOURCES[source_id].daily_budget if source_id in SOURCES else None
        parts = ", ".join(f"{p}: {n}" for sid, p, n in rows if sid == source_id)
        print(f"{source_id}: {spent}/{cap} today ({parts})")
    return 0


def _withhold(args: argparse.Namespace) -> int:
    """Withhold or restore one player (and anyone merged into them), with an audit entry."""
    import getpass
    from datetime import UTC, datetime

    from sqlalchemy import func
    from sqlalchemy.orm import Session

    from scout.db import get_engine
    from scout.models import Player, PrivacyAction

    with Session(get_engine()) as s:
        player = s.get(Player, args.player)
        while player is not None and player.merged_into_id is not None:
            player = s.get(Player, player.merged_into_id)  # act on the canonical record
        if player is None:
            print(f"no player {args.player}", file=sys.stderr)
            return 2
        merged = s.scalars(select(Player).where(Player.merged_into_id == player.id)).all()
        stamp = datetime.now(UTC) if args.action == "withhold" else None
        for p in (player, *merged):
            p.withheld_at = stamp
        s.add(PrivacyAction(player_id=player.id, action=args.action, reason=args.reason,
                            actor=getpass.getuser()))  # fmt: skip
        s.commit()
        print(f"player {player.id}: {args.action} recorded ({1 + len(merged)} record(s))")
        if args.action == "withhold":
            # tournament-scoped ids and other federations create separate records for one person
            same = s.scalars(
                select(Player.id).where(
                    func.lower(Player.display_name) == player.display_name.lower(),
                    Player.id != player.id,
                    Player.merged_into_id.is_(None),
                    Player.withheld_at.is_(None),
                )
            ).all()
            if same:
                print(f"other player records with the same name (check, then withhold each "
                      f"that is this person): {', '.join(map(str, same))}")  # fmt: skip
    return 0


def _minimise() -> int:
    """Rewrite stored payloads and player keys that hold national-identity member ids (no
    requests). Payload hashes are recomputed, so the next import sees no change."""
    from sqlalchemy.orm import Session

    from scout.config import get_settings
    from scout.db import get_engine
    from scout.ingest.raw import content_hash
    from scout.models import RawRecordRevision, SourcePlayer
    from scout.privacy import minimise_h2h, minimise_identifier

    secret = get_settings().identifier_key
    if secret is None:
        print("SCOUT_IDENTIFIER_KEY is not set: nothing rewritten", file=sys.stderr)
        return 2
    key = secret.get_secret_value()
    revisions = players = 0
    with Session(get_engine()) as s:
        taken = set(
            s.execute(select(RawRecordRevision.raw_record_id, RawRecordRevision.content_sha256))
            .tuples()
            .all()
        )
        for rev in s.scalars(
            select(RawRecordRevision).where(
                RawRecordRevision.payload["h2h"].astext.like("%MemberID=%")
            )
        ):
            payload = dict(rev.payload)
            minimal = minimise_h2h(payload.get("h2h"), key)
            if minimal == payload.get("h2h"):
                continue
            payload["h2h"] = minimal
            new_hash = content_hash(payload)
            rev.payload = payload
            # two revisions that differed only in this id now read the same: the identifier
            # must still go, but one record cannot hold two revisions with one hash
            if (rev.raw_record_id, new_hash) not in taken:
                taken.discard((rev.raw_record_id, rev.content_sha256))
                rev.content_sha256 = new_hash
                taken.add((rev.raw_record_id, new_hash))
            revisions += 1
        members = list(
            s.scalars(select(SourcePlayer).where(SourcePlayer.source_key.like("member:%")))
        )
        keys = {(sp.source_id, sp.source_key) for sp in members}
        for sp in members:
            issuer, _, member = sp.source_key[len("member:") :].partition("/")
            minimal = minimise_identifier(member, key)
            if minimal == member or minimal is None:
                continue
            target = f"member:{issuer}/{minimal}"
            if (sp.source_id, target) in keys:
                # one number written two ways: the same person. A marked key keeps the records
                # apart until identity resolution links them as a recorded decision (ADR-0011)
                target = f"{target}~{sp.id}"
            keys.discard((sp.source_id, sp.source_key))
            keys.add((sp.source_id, target))
            sp.source_key = target
            players += 1
        s.commit()
    print(f"payloads rewritten: {revisions}; player keys rewritten: {players}")
    return 0


def _reclassify() -> int:
    """Apply the current ADR-0009 rule to all events, e.g. after the rule was tightened."""
    from sqlalchemy.orm import Session

    from scout.db import get_engine
    from scout.ingest.tournamentsoftware import discipline_of
    from scout.models import Event
    from scout.privacy import is_redistributable_event

    with Session(get_engine()) as s:
        changed = Counter[str]()
        for e in s.scalars(select(Event)):
            if e.discipline is None and (found := discipline_of(e.name)):
                e.discipline = found  # a newly recognised spelling (privacy._ALIASES)
                changed["discipline recognised"] += 1
            allowed = is_redistributable_event(e.name, e.discipline)
            if allowed != e.redistributable:
                e.redistributable = allowed
                changed["now served" if allowed else "now private"] += 1
        s.commit()
    print(f"events reclassified: {dict(changed) or 'none changed'}")
    return 0


def _events(args: argparse.Namespace) -> int:
    """Discipline and category of every Tournament Software event, read in its tournament's
    language. Changes are counted by source and old->new discipline."""
    from sqlalchemy.orm import Session

    from scout.db import get_engine
    from scout.ingest.event_codes import reclassify

    with Session(get_engine()) as s:
        counts = reclassify(s, dry_run=args.dry_run)
        if args.dry_run:
            s.rollback()
        else:
            s.commit()
    for key, n in sorted(counts.items()):
        if not key.startswith("events "):
            print(f"{key}: {n}")
    print("dry run: nothing written" if args.dry_run else "applied")
    return 0


def _identity(args: argparse.Namespace) -> int:
    """Review identity candidates (ADR-0003). Every decision is recorded and reversible."""
    import getpass

    from sqlalchemy.orm import Session

    from scout import identity
    from scout.db import get_engine
    from scout.models import IdentityCandidate, SourcePlayer

    who = f"human:{getpass.getuser()}"
    with Session(get_engine()) as s:
        try:
            if args.action == "resolve":
                from scout import identity_auto

                identity.generate_candidates(s)
                report = identity_auto.resolve(s)
                s.commit()
                e = report.evaluation
                state = "enabled" if report.tier_b_enabled else "disabled"
                print(f"tier B evaluation: recall {e.recall:.1%} on {e.positives} same-member "
                      f"pairs; false links {e.false_link_rate:.1%} on {e.negatives} namesake "
                      f"pairs; tier B {state}")  # fmt: skip
                for outcome, n in sorted(report.outcomes.items()):
                    print(f"  {outcome}: {n}")
            elif args.action == "candidates":
                print(f"new candidates: {identity.generate_candidates(s)}")
                s.commit()
                rows = s.scalars(
                    select(IdentityCandidate)
                    .where(IdentityCandidate.status.in_(["open", "deferred"]))
                    .order_by(IdentityCandidate.id)
                ).all()
                for c in rows:
                    a = s.get(SourcePlayer, c.source_player_a_id)
                    b = s.get(SourcePlayer, c.source_player_b_id)
                    if a and b:
                        print(f"  #{c.id} {c.status} {c.rule}: {a.display_name!r} "
                              f"({a.source_key}) ~ {b.display_name!r} ({b.source_key})"
                              f"{f' [{c.note}]' if c.note else ''}")  # fmt: skip
                print(f"open or deferred: {len(rows)}")
            elif args.action == "merge":
                d = identity.merge(s, args.id, args.reason, who, allow_deferred=True)
                s.commit()
                print(f"merged: decision {d.id} (undo with: scout identity undo {d.id})")
            elif args.action == "reject":
                d = identity.reject(s, args.id, args.reason, who, allow_deferred=True)
                s.commit()
                print(f"rejected: decision {d.id}")
            else:
                d = identity.undo(s, args.id, args.reason, who)
                s.commit()
                print(f"undone: decision {d.id}")
        except ValueError as e:
            print(e, file=sys.stderr)
            return 1
    return 0


def _import_compilation(args: argparse.Namespace) -> int:
    """The third-party BWF compilation, from a local checkout; no network (ADR-0002 grant)."""
    from pathlib import Path

    from sqlalchemy.orm import Session

    from scout.db import get_engine
    from scout.ingest import bwf_compilation
    from scout.models import IngestRun

    rows, index = bwf_compilation.read(Path(args.path))
    if args.limit:
        rows = rows[: args.limit]
    with Session(get_engine()) as s:
        run = IngestRun(source_id=bwf_compilation.SOURCE)
        s.add(run)
        s.flush()
        counts = bwf_compilation.ingest(
            s, run, rows, index, commit_every=None if args.dry_run else 20
        )
        if args.dry_run:
            s.rollback()
        else:
            from datetime import UTC, datetime

            run.status, run.counts = "succeeded", dict(counts)
            run.finished_at = datetime.now(UTC)
            s.commit()
    print(f"{'DRY RUN (rolled back): ' if args.dry_run else ''}{len(rows)} rows")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="scout", description="Badminton Scout backend tools")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("sources", help="list data sources and their granted uses")
    discover = commands.add_parser("discover", help="queue tournaments from a portal's listing")
    discover.add_argument("portal", choices=_portal_keys())
    discover.add_argument("--pages", type=int, default=5, help="20 tournaments per page (1-50)")
    discover.add_argument("--from", dest="start", help="www: first day, YYYY-MM-DD")
    discover.add_argument("--to", dest="end", help="www: last day, YYYY-MM-DD")
    sync = commands.add_parser("sync", help="scheduled pass: discover, refresh, import (daily)")
    sync.add_argument("--source", choices=[*_portal_keys(), "all"], default="all")
    sync.add_argument("--max", type=int, default=200, help="tournaments per provider (1-200)")
    sync.add_argument("--every", type=int, help="hours until the scheduler runs this again")
    imp = commands.add_parser("import", help="import queued tournaments within today's budget")
    imp.add_argument("--source", choices=[*_portal_keys(), "all"], default="all")
    imp.add_argument("--max", type=int, default=10, help="tournaments this run (default 10)")
    imp.add_argument("--owners", type=int, default=20, help="www owner checks this run")
    imp.add_argument("--retry-empty", action="store_true", help="retry tournaments with no matches")
    imp.add_argument("--tournament", help="import one queued tournament now (GUID)")
    imp.add_argument(
        "--renormalize", action="store_true", help="with --tournament: re-apply current rules"
    )
    comp = commands.add_parser(
        "import-compilation", help="import the bwf-match-data files (bwf_historical_compilation)"
    )
    comp.add_argument("path", help="a checkout of github.com/SahilMotyar/bwf-match-data")
    comp.add_argument("--dry-run", action="store_true", help="import, report, then roll back")
    comp.add_argument("--limit", type=int, help="only the first N rows (a representative sample)")
    commands.add_parser("openapi", help="print the API's OpenAPI document (frontend type source)")
    seed = commands.add_parser("seed", help="synthetic fixtures")
    seed_e2e = seed.add_subparsers(dest="action", required=True).add_parser(
        "e2e", help="reset a *_e2e database to the frontend test fixture"
    )
    seed_e2e.add_argument("--ids-out", help="write the fixture's ids as JSON to this file")
    budget = commands.add_parser("budget", help="provider request budgets (ADR-0008)")
    budget_actions = budget.add_subparsers(dest="action", required=True)
    budget_actions.add_parser("status", help="today's requests per source and purpose")
    record = budget_actions.add_parser("record", help="record requests made outside the provider")
    record.add_argument("--source", required=True)
    record.add_argument("--requests", type=int, required=True)
    record.add_argument("--purpose", required=True, help="discovery, learning, verification, ...")
    record.add_argument("--note")
    privacy = commands.add_parser("privacy", help="ADR-0009/0010 controls")
    privacy_actions = privacy.add_subparsers(dest="action", required=True)
    privacy_actions.add_parser(
        "reclassify", help="re-apply the redistribution rule to every stored event (no requests)"
    )
    privacy_actions.add_parser(
        "minimise", help="replace stored national-identity member ids with keyed tokens"
    )
    for action, what in (("withhold", "act on a removal request"), ("restore", "undo a withhold")):
        p = privacy_actions.add_parser(action, help=f"{what}: one player, audited")
        p.add_argument("player", type=int, help="player id (as in /players/<id>)")
        p.add_argument("--reason", required=True, help="who asked and why: kept in the audit log")
    events = commands.add_parser("events", help="event classification")
    reclassify = events.add_subparsers(dest="action", required=True).add_parser(
        "reclassify", help="re-read disciplines and categories from codes (docs/event-codes.md)"
    )
    reclassify.add_argument("--dry-run", action="store_true", help="report changes, write nothing")
    ident = commands.add_parser("identity", help="review player identity candidates (ADR-0003)")
    ident_actions = ident.add_subparsers(dest="action", required=True)
    ident_actions.add_parser("candidates", help="find and list open candidates")
    ident_actions.add_parser(
        "resolve", help="link on stable ids, separate conflicts, defer the rest (ADR-0011)"
    )
    review = (("merge", "candidate"), ("reject", "candidate"), ("undo", "merge decision"))
    for action, what in review:
        p = ident_actions.add_parser(action, help=f"{action} a {what}")
        p.add_argument("id", type=int, help=f"{what} id")
        p.add_argument("--reason", required=True, help="why: kept in the audit log")
    report = commands.add_parser("report", help="data reports")
    reports = report.add_subparsers(dest="report", required=True)
    reports.add_parser("coverage", help="per-source coverage and data quality")
    reports.add_parser("portals", help="every portal seen owning tournaments, and its status")
    reports.add_parser("imports", help="import completeness per source, and what is missing")
    reports.add_parser("identity", help="identity links, conflicts, deferrals and undo history")
    aa = commands.add_parser("api-anything", help="API Anything runtime tools")
    aa.add_subparsers(dest="action", required=True).add_parser(
        "doctor", help="check node, the pinned runtime and approved operations"
    )
    args = parser.parse_args(argv)
    if args.command == "sources":
        _sources()
    elif args.command == "api-anything":
        sys.exit(_doctor())
    elif args.command == "discover":
        sys.exit(_discover(args))
    elif args.command == "import":
        sys.exit(_import(args))
    elif args.command == "sync":
        sys.exit(_sync(args))
    elif args.command == "seed":
        from pathlib import Path

        from sqlalchemy.orm import Session

        from scout.config import get_settings
        from scout.db import get_engine
        from scout.seed import seed

        if get_settings().env == "production":
            sys.exit("refusing to seed with SCOUT_ENV=production")
        with Session(get_engine()) as s:
            ids = seed(s, Path(args.ids_out) if args.ids_out else None)
        print(f"seeded e2e fixture: {ids}")
    elif args.command == "import-compilation":
        sys.exit(_import_compilation(args))
    elif args.command == "openapi":
        import json

        from scout.main import create_app

        print(json.dumps(create_app().openapi(), indent=2, sort_keys=True))
    elif args.command == "budget":
        sys.exit(_budget(args))
    elif args.command == "privacy":
        actions = {"reclassify": _reclassify, "minimise": _minimise}
        sys.exit(actions[args.action]() if args.action in actions else _withhold(args))
    elif args.command == "events":
        sys.exit(_events(args))
    elif args.command == "identity":
        sys.exit(_identity(args))
    elif args.command == "report":
        reports_by_name = {
            "portals": _portals,
            "imports": _imports,
            "coverage": _coverage,
            "identity": _identity_report,
        }
        sys.exit(reports_by_name[args.report]())

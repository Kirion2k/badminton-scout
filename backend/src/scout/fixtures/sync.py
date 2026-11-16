"""One pass of the fixture pipeline (ADR-0014): fetch, store, issue forecasts, reconcile
outcomes, report. A provider failure is recorded with its class and nothing is issued."""

import re
from collections import Counter
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scout.budget import Budget, BudgetExhausted
from scout.fixtures import store
from scout.fixtures.providers import FixtureProvider
from scout.ingest.provider import ProviderError
from scout.models import Fixture, ForecastEvent, IngestRun, IssuedPrediction
from scout.ratings import prospective
from scout.sources import SOURCES


def sync(
    session: Session,
    provider: FixtureProvider,
    *,
    entered_by: str,
    budget: Budget | None = None,
    issue: bool = True,
) -> dict[str, Any]:
    run = IngestRun(source_id=provider.source_id)
    session.add(run)
    session.flush()
    report: dict[str, Any] = {"run": str(run.id)}
    try:
        if SOURCES[provider.source_id].hosts:  # an automated provider spends its budget
            if budget is None:
                raise ProviderError("an automated provider needs a request budget")
            budget.charge(provider.source_id, provider.requests_per_fetch, purpose="fixtures")
        rows, rejected = provider.fetch()
    except (ProviderError, BudgetExhausted) as e:
        run.status, run.finished_at = "failed", func.now()
        run.counts = report["failure"] = {"class": type(e).__name__, "detail": str(e)}
        session.flush()
        return report
    now = session.execute(select(func.now())).scalar_one()
    future = [r for r in rows if r.retrieved_at > now + timedelta(minutes=5)]
    # a check time in the future would keep a fixture "fresh" until then: never accepted
    report["rejected"] = [f"line {r.line}: {r.reason}" for r in rejected] + [
        f"{r.key}: checked_at is in the future" for r in future
    ]
    stored = [store.upsert(session, run, row, entered_by) for row in rows if row not in future]
    fixtures = [f for f in stored if f is not None]
    report["fixtures"] = len(fixtures)
    report["older_readings_ignored"] = len(stored) - len(fixtures)
    issued, refused = 0, Counter[str]()
    if issue:
        forecast = set(session.scalars(select(IssuedPrediction.fixture_id)))
        for f in fixtures:
            if f.status != "scheduled" or f.id in forecast:
                continue
            try:
                with session.begin_nested():
                    prospective.issue_for_fixture(session, f.id)
                issued += 1
            except prospective.NotEligible as e:
                refused[_category(str(e))] += 1
                _refused(session, f, str(e))
    report.update(issued=issued, refused=dict(refused), voided=prospective.reconcile(session))
    run.status, run.finished_at = "succeeded", func.now()
    run.counts = {k: v for k, v in report.items() if k != "run"}
    session.flush()
    return report


def _category(reason: str) -> str:
    """A refusal's kind, without the ids and times that make each message unique."""
    return re.split(r"[:(]", re.sub(r"\d+", "N", reason))[0].strip()


def _refused(session: Session, f: Fixture, reason: str) -> None:
    """Record why a fixture got no forecast, once per reason and revision (the missed-fixture
    audit), never on every pass."""
    last = session.scalars(
        select(ForecastEvent).where(ForecastEvent.fixture_id == f.id,
                                    ForecastEvent.kind == "refused")
        .order_by(ForecastEvent.id.desc()).limit(1)
    ).first()  # fmt: skip
    if last is None or (last.reason, last.fixture_revision_id) != (reason, f.revision_id):
        session.add(ForecastEvent(kind="refused", reason=reason, fixture_id=f.id,
                                  fixture_revision_id=f.revision_id))  # fmt: skip
        session.flush()


def status(session: Session) -> dict[str, Any]:
    """Freshness, missed fixtures and failures, per fixture source."""
    out: dict[str, Any] = {}
    for source in sorted(prospective.EVIDENCE_SOURCES):
        runs = list(session.scalars(
            select(IngestRun).where(IngestRun.source_id == source)
            .order_by(IngestRun.started_at.desc()).limit(20)
        ))  # fmt: skip
        fixtures = list(session.scalars(select(Fixture).where(Fixture.source_id == source)))
        forecast = set(session.scalars(select(IssuedPrediction.fixture_id)))
        now = session.execute(select(func.now())).scalar_one()
        missed = [f for f in fixtures if f.id not in forecast and store.fixture_cutoff(f) <= now]
        reasons = Counter[str]()
        for f in missed:
            last = session.scalar(
                select(ForecastEvent.reason).where(ForecastEvent.fixture_id == f.id,
                                                   ForecastEvent.kind == "refused")
                .order_by(ForecastEvent.id.desc()).limit(1)
            )  # fmt: skip
            reasons[_category(last or "never considered")] += 1
        out[source] = {
            "last_success": next((r.finished_at for r in runs if r.status == "succeeded"), None),
            "failures": Counter(r.counts.get("class", "?") for r in runs if r.status == "failed"),
            "fixtures": len(fixtures),
            "newest_check": max((f.retrieved_at for f in fixtures), default=None),
            "awaiting_verification": sum(
                f.status in store.TERMINAL and not store.is_verified(f) for f in fixtures
            ),
            "missed": dict(reasons),
        }
    return out


def pilot(session: Session) -> dict[str, Any]:
    """The operational pilot (M8.2): issuance, lead time, identity match rate and outcomes. The
    first 100 forecasts show whether the pipeline works; they are not release evidence alone."""
    fixtures = list(session.scalars(
        select(Fixture).where(Fixture.source_id.in_(prospective.EVIDENCE_SOURCES))
    ))  # fmt: skip
    run_id = prospective.production.latest_run(session)
    resolved = 0
    for f in fixtures:
        if run_id is not None and all(
            store.resolved(session, sp, run_id, f.discipline) is not None
            for sp in (f.side_a_player_id, f.side_b_player_id)
        ):
            resolved += 1
    preds = list(session.scalars(
        select(IssuedPrediction).join(Fixture, Fixture.id == IssuedPrediction.fixture_id)
        .where(Fixture.source_id.in_(prospective.EVIDENCE_SOURCES))
    ))  # fmt: skip
    leads = sorted((p.cutoff_at - p.issued_at).total_seconds() / 3600 for p in preds)
    return {
        "fixtures": len(fixtures),
        "both_players_resolved": resolved,
        "identity_match_rate": round(resolved / len(fixtures), 3) if fixtures else None,
        "forecasts": len(preds),
        "median_hours_before_cutoff": leads[len(leads) // 2] if leads else None,
        "results_verified": sum(store.is_verified(f) for f in fixtures),
        "evaluation": prospective.score(session),
    }

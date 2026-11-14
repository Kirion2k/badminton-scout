"""Event codes read in the tournament's language (docs/event-codes.md). Synthetic names only."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from scout.ingest.event_codes import Classified, classify, discipline, fits, reclassify
from scout.ingest.event_codes import tournament_language as language
from scout.models import Event, Tournament

DBV, OBV, BADVLA, CBBD = (f"tournamentsoftware_{k}" for k in ("dbv", "obv", "badvla", "cbbd"))


@pytest.mark.parametrize(
    ("source", "name", "expected"),
    [
        (DBV, "HE A - Gruppe 1", Classified("MS", "adult")),
        (DBV, "DE Kl 1", Classified("WS", "adult")),
        (DBV, "GD", Classified("XD", "adult")),  # Gemischtes Doppel, not girls' doubles
        (DBV, "MD U15", Classified("WD", "junior")),  # Maedchendoppel, not men's doubles
        (DBV, "JE U19 - Gruppe A", Classified("MS", "junior")),
        (DBV, "Herrendoppel C - Gruppe E", Classified("MD", "adult")),
        (DBV, "MS A", Classified("MS", "adult")),  # an unambiguous English code
        (OBV, "MD", Classified(None, "adult")),  # seen as mixed and as girls': left unknown
        (BADVLA, "SM 9/10 - Group A", Classified("MS", "adult")),
        (BADVLA, "DMx 7-8", Classified("XD", "adult")),
        (BADVLA, "Simples Filles U17", Classified("WS", "junior")),
        (BADVLA, "G-badminton Enkel - rolstoel", Classified(None, "para")),
        (CBBD, "SF_AdultoMaster - Group B", Classified("WS", "adult")),
        (CBBD, "SMB - Group W", Classified("MS", "adult")),
        (CBBD, "SM_Sub17B", Classified("MS", "junior")),
        (CBBD, "DX WH", Classified("XD", "para")),
        ("tournamentsoftware_ba", "DMS - Group O", Classified("MS", "adult")),  # D grade
        ("tournamentsoftware_bnz", "U15 GD - Group A", Classified("WD", "junior")),
        ("tournamentsoftware", "TPA", Classified("MS", "adult")),
        ("tournamentsoftware", "TAPA - U13", Classified("MS", "junior")),
        ("tournamentsoftware_canada", "CAD SM - Groupe M", Classified("MS", "junior")),
        ("tournamentsoftware_canada", "SDC", Classified("WS", "adult")),
    ],
)
def test_codes_by_source(source: str, name: str, expected: Classified) -> None:
    assert discipline(source, name) == expected


def test_a_german_tournament_in_english_codes_reads_english() -> None:
    english = ["MS A", "WS A", "XD A", "GD U13"]
    assert language(DBV, english) == "en"
    assert classify(DBV, "GD U13", "en") == Classified("WD", "junior")  # girls' doubles here
    assert language(DBV, ["HE A", "DE A", "GD"]) == "source"
    assert language("tournamentsoftware_ba", ["HE"]) == "source"  # only mixed-language sources


def test_english_words_count_but_english_codes_do_not_cross_languages() -> None:
    assert discipline(DBV, "Men's Singles - Group 01").discipline == "MS"
    assert discipline(DBV, "Mon U13 Boys Sgls").discipline == "MS"
    assert discipline(DBV, "GD").discipline == "XD"


def test_two_disciplines_in_one_name_is_unknown() -> None:
    assert classify(DBV, "HE/DE Open").discipline is None


def test_a_code_must_fit_the_draw() -> None:
    assert fits("MS", {1}) and fits("XD", {2}) and fits(None, {1, 2}) and fits("MS", set())
    assert not fits("MS", {2}) and not fits("WD", {1, 2})


def test_reclassify_corrects_stored_events_in_context(session: Session) -> None:
    german = Tournament(source_id=DBV, source_key="t-de", name="Synthetic Open")
    english = Tournament(source_id=DBV, source_key="t-en", name="Synthetic Cup")
    session.add_all([german, english])
    session.flush()
    events = {
        ("t-de", "HE A"): None,
        ("t-de", "GD A"): "WD",  # what the English-only reading stored
        ("t-de", "MD U15"): "MD",
        ("t-en", "MS A"): "MS",
        ("t-en", "GD U13"): "WD",
    }
    for (t, name), stored in events.items():
        tid = german.id if t == "t-de" else english.id
        session.add(Event(tournament_id=tid, source_key=name, name=name, discipline=stored))
    session.flush()
    dry = reclassify(session, [german.id, english.id], dry_run=True)
    assert dry["events tournamentsoftware_dbv WD->XD"] == 1
    assert session.scalar(select(Event.discipline).where(Event.name == "GD A")) == "WD"
    reclassify(session, [german.id, english.id])
    got = {e.name: (e.discipline, e.category) for e in session.scalars(select(Event))}
    assert got["HE A"] == ("MS", "adult")
    assert got["GD A"] == ("XD", "adult")
    assert got["MD U15"] == ("WD", "junior")
    assert got["MS A"] == ("MS", "adult")
    assert got["GD U13"] == ("WD", "junior")


def test_review_visibility_follows_the_corrected_reading(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scout.privacy

    monkeypatch.setattr(scout.privacy, "PUBLISH_RESTRICTED_EVENTS", False)
    t = Tournament(source_id=DBV, source_key="t-vis", name="Synthetic")
    session.add(t)
    session.flush()
    # stored by the English-only reading: "MD" as men's doubles, so adult and served
    e = Event(tournament_id=t.id, source_key="MD U15", name="MD", discipline="MD",
              redistributable=True)  # fmt: skip
    other = Event(tournament_id=t.id, source_key="HE", name="HE", discipline=None)
    session.add_all([e, other])
    session.flush()
    counts = reclassify(session, [t.id])
    assert (e.discipline, e.category, e.redistributable) == ("WD", "junior", False)
    assert counts["now private"] == 1

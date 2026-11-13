import pytest

import scout.privacy
from scout.privacy import is_adult_event, is_redistributable_event

# real adult event names seen on ba.tournamentsoftware.com, 2026-11-12
ADULT = [
    "MS C - Group A",
    "MD A Reserve",
    "XD Open (Combined Mixed)",
    "MD A/B (Sat 24/10) Please see conditions",
    "MD B/Cs 35 plus (Sun 1/11) Please see conditions",
    "XD 35 (Sat24/10) saturday 31/10 Please see c",
    "XD 35 C Grade 35 plus (Friday 30/10)",
    "WS Division 2 (B & C )",
    "MS 35+",
    "WD Open (Sat)",
    # www.tournamentsoftware.com, Vietnam and Japan, 2026-11-13
    "Đơn Nam", "Đơn Nữ N3", "Đôi Nam N4", "Đôi Nam Nữ N5", "Đôi nam N3", "Đôi Nữ N3 - Group A",
    "Men\u2019sSingles\u20102 - Group A", "Women\u2019sDoubles\u20101",
    "MixedDoubles\u20102 - Position 01-16",
    "Men\u2019sDoubles\u20103 - Position 5-8",
]  # fmt: skip
# must never be served: juniors (several spellings and languages) and para sport classes
PRIVATE = [
    "BS U11 - Group B", "GS U13", "Mon U13 Boys Sgls - Group A", "MD Junior", "MS Under 15",
    "MS Under-17", "MS U-15", "MSU15", "GU15 Singles", "Youth MS", "MS Jnr", "JMS",
    "Jeugd HE", "Junioren DE", "MS Jugend", "MS Minimes", "MS Cadets", "XD U19 (Sat)",
    "MS (U17)", "MS U23",  # U23 is adult in some places: hidden on purpose (fail closed)
    "MS SL3", "WS SU5", "Para MS WH1", "SH6 Singles", "WH1/2 Doubles", "MS 17", "MS Open U19",
    "Teams", "",
    # Vietnamese age bands and unspecified-gender events stay private
    "Đơn Nam U13", "Đôi Nam Nữ U13 - Group A", "Đơn Nữ U11-13 - Group A", "Đơn U9 - Group A",
    "Đơn N1", "3x3 Nữ N7", "Men\u2019sSingles\u2010U15", "Đơn Nam N9",
]  # fmt: skip


@pytest.mark.parametrize("name", ADULT)
def test_real_adult_events_are_served(name: str) -> None:
    assert is_adult_event(name, "MS")


@pytest.mark.parametrize("name", PRIVATE)
def test_junior_para_and_unknown_events_are_restricted(name: str) -> None:
    assert not is_adult_event(name, "MS")


def test_unknown_discipline_stays_private() -> None:
    assert not is_adult_event("MS A", None)


def test_restricted_events_are_served_while_the_owner_publishes_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert is_redistributable_event("BS U15", "MS")  # ADR-0010: published
    assert is_redistributable_event("SL3 Singles", None)
    monkeypatch.setattr(scout.privacy, "PUBLISH_RESTRICTED_EVENTS", False)
    assert not is_redistributable_event("BS U15", "MS")  # the switch back still works
    assert is_redistributable_event("MS A", "MS")


def test_national_identity_numbers_are_never_stored_in_clear() -> None:
    from scout.privacy import minimise_h2h, minimise_identifier

    cpf = "123.456.789-09"  # an invented number in the CPF shape
    token = minimise_identifier(cpf, "k")
    assert token and token.startswith("h-") and "123" not in token
    assert minimise_identifier(cpf, "k") == token  # same person, same key: identity still works
    assert minimise_identifier(cpf, "other key") != token
    assert minimise_identifier(cpf, None) is None  # no key: dropped, not kept
    # wrapped in invisible characters, raw or percent-encoded: the same token
    assert minimise_identifier(f"\u200b{cpf}\u00a0", "k") == token
    assert minimise_identifier("%e2%80%8b" + cpf + "%c2%a0", "k") == token
    assert minimise_identifier("QA1001", "k") == "QA1001"  # ordinary member ids unchanged
    url = f"https://x/h2h?OrganizationCode=O&T1P1MemberID={cpf}&T2P1MemberID=QA1"
    kept = minimise_h2h(url, "k") or ""
    assert cpf not in kept and "T2P1MemberID=QA1" in kept
    assert "T1P1MemberID" not in (minimise_h2h(url, None) or "")


def test_head_to_head_links_without_national_ids_are_untouched() -> None:
    from scout.privacy import minimise_h2h

    url = "https://x/h2h?OrganizationCode=O&T1P1MemberID=AB%2012&T2P1MemberID=QA+1"
    assert minimise_h2h(url, "k") == url  # byte for byte: re-encoding would split players


@pytest.mark.parametrize("shape", ["12345678909", "880101-14-5678", "123.456.789-09"])
def test_other_national_id_shapes_are_tokenised(shape: str) -> None:
    from scout.privacy import minimise_identifier

    token = minimise_identifier(shape, "k")
    assert token and token.startswith("h-")
    assert minimise_identifier("12345678909", "k") == minimise_identifier("123.456.789-09", "k")

"""Minimal-consent adapter against a local stand-in for the consent endpoint. No network."""

import threading
import urllib.parse
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from scout.ingest.consent import (
    ConsentError,
    _submit_minimal_consent,  # pyright: ignore[reportPrivateUsage]
    consent_is_current,
)

posted: list[dict[str, list[str]]] = []


def server_recording(purposes: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers["Content-Length"])
            posted.append(urllib.parse.parse_qs(self.rfile.read(length).decode()))
            self.send_response(302)
            value = urllib.parse.quote(f"l=1033&exp=46337.5&c=1&cp={purposes}")
            self.send_header("Set-Cookie", f"st={value}; path=/")
            self.send_header("Location", "/")
            self.end_headers()

        def do_GET(self) -> None:
            self.send_response(200)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            pass

    return Handler


@pytest.fixture
def site(request: pytest.FixtureRequest) -> Iterator[str]:
    posted.clear()
    httpd = HTTPServer(("127.0.0.1", 0), server_recording(request.param))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


@pytest.mark.parametrize("site", ["1"], indirect=True)
def test_submits_only_basic_functionality(site: str) -> None:
    cookie = _submit_minimal_consent(site)
    assert cookie.name == "st"
    assert posted == [{"SettingsOpen": ["false"], "CookiePurposes": ["1"]}]


@pytest.mark.parametrize("site", ["7", "1,2", ""], indirect=True)
def test_refuses_when_the_site_records_more_than_basic(site: str) -> None:
    with pytest.raises(ConsentError, match="not exactly basic"):
        _submit_minimal_consent(site)


def test_consent_record_expires_and_must_be_basic(tmp_path: Path) -> None:
    record = tmp_path / "consent" / "s.json"
    record.parent.mkdir()
    now = datetime.now(UTC)
    record.write_text(f'{{"given_at": "{now.isoformat()}", "purposes": "1"}}')
    assert consent_is_current(tmp_path, "s", now)
    assert not consent_is_current(tmp_path, "s", now + timedelta(days=301))
    record.write_text(f'{{"given_at": "{now.isoformat()}", "purposes": "7"}}')
    assert not consent_is_current(tmp_path, "s", now)
    assert not consent_is_current(tmp_path, "missing", now)

"""Minimal cookie consent for Tournament Software hosts (ADR-0008 §6).

Consent changes state on the site, so it is not an API Anything read operation. This adapter
submits only "Basic functionality" (CookiePurposes=1), checks that the site recorded exactly
that, and hands the resulting consent cookie to the runtime's session for the site through the
documented `api-anything login <site> --cookies <file>`. No browser cookies, no account.
"""

import http.cookiejar
import json
import os
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

from scout.budget import Budget

CONSENT_COOKIE = "st"
BASIC_FUNCTIONALITY = "1"  # the only purpose the form marks as required
# the site's consent cookie lasts a year; renew well before it lapses
RENEW_AFTER = timedelta(days=300)
USER_AGENT = "BadmintonScout/0.1 (authorised integration)"


class ConsentError(Exception):
    pass


def _record(home: Path, site: str) -> Path:
    return home / "consent" / f"{site}.json"


def consent_is_current(home: Path, site: str, now: datetime | None = None) -> bool:
    try:
        data = json.loads(_record(home, site).read_text())
        given = datetime.fromisoformat(data["given_at"])
    except (OSError, ValueError, KeyError):
        return False
    fresh = (now or datetime.now(UTC)) - given < RENEW_AFTER
    return data.get("purposes") == BASIC_FUNCTIONALITY and fresh


def consent_cookie(home: Path, site: str) -> str | None:
    """The stored minimal-consent value, for the owner probe; None means consent again."""
    if not consent_is_current(home, site):
        return None
    value = json.loads(_record(home, site).read_text()).get("cookie")
    return value if isinstance(value, str) and value else None


def invalidate_consent(home: Path, site: str) -> None:
    """Forget the consent record, e.g. when a read meets the wall again: next start re-consents."""
    _record(home, site).unlink(missing_ok=True)


def _submit_minimal_consent(base_url: str) -> http.cookiejar.Cookie:
    """POST the consent form with Basic functionality only; return the consent cookie it sets."""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    body = urllib.parse.urlencode(
        {"ReturnUrl": "", "SettingsOpen": "false", "CookiePurposes": BASIC_FUNCTIONALITY}
    ).encode()
    request = urllib.request.Request(  # noqa: S310 - base_url comes from CONSENT_SITES only
        f"{base_url}/cookiewall/Save",
        data=body,
        method="POST",
        headers={"User-Agent": USER_AGENT, "Referer": f"{base_url}/cookiewall/"},
    )
    try:
        with opener.open(request, timeout=20):  # follows the 302 back to the home page
            pass
    except OSError as e:
        raise ConsentError(f"consent request failed: {e}") from None
    cookie = next((c for c in jar if c.name == CONSENT_COOKIE), None)
    if cookie is None or cookie.value is None:
        raise ConsentError("the site set no consent cookie")
    # refuse anything but the minimal consent, whatever the form's defaults become
    recorded = urllib.parse.parse_qs(urllib.parse.unquote(cookie.value)).get("cp")
    if recorded != [BASIC_FUNCTIONALITY]:
        raise ConsentError(f"site recorded consent purposes {recorded}, not exactly basic")
    return cookie


def establish_consent(
    *, site: str, base_url: str, binary: Path, home: Path, env: dict[str, str], budget: Budget,
    source_id: str,
) -> None:  # fmt: skip
    """Give minimal consent once, store the cookie in the runtime session, record when."""
    # the POST and its redirect to the home page. The site spec pins loginCookies=["st"], so the
    # cookie import below sends no probe request of its own (runtime login.js knownGuests)
    budget.charge(source_id, 2, purpose="consent", note=f"{site}: CookiePurposes=1")
    cookie = _submit_minimal_consent(base_url)
    export = [{
        "name": cookie.name, "value": cookie.value, "domain": cookie.domain,
        "path": cookie.path or "/", "expires": cookie.expires or int(time.time()) + 365 * 86400,
        "httpOnly": False, "secure": bool(cookie.secure), "sameSite": "Lax",
    }]  # fmt: skip
    fd, name = tempfile.mkstemp(prefix="consent-", suffix=".json", dir=home)  # 0600 by default
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(export, f)
        done = subprocess.run(  # noqa: S603 - fixed argv; the pinned binary
            [str(binary), "login", site, "--cookies", name],
            env=env, capture_output=True, text=True, timeout=60, check=False,
        )  # fmt: skip
    finally:
        Path(name).unlink(missing_ok=True)
    if done.returncode != 0:
        raise ConsentError(f"importing the consent cookie failed: {done.stderr.strip()[:200]}")
    record = _record(home, site)
    record.parent.mkdir(exist_ok=True, mode=0o700)
    record.touch(mode=0o600)  # private before the value is written
    record.chmod(0o600)
    record.write_text(
        json.dumps(
            {
                "given_at": datetime.now(UTC).isoformat(),
                "purposes": BASIC_FUNCTIONALITY,
                # the consent preference itself (cp=1), not a session or credential
                "cookie": cookie.value,
            }
        )
    )

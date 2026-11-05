"""Save your Yahoo login (cookies from your logged-in browser: Brave, Chrome, Arc, Edge or Chromium) as the
GitHub secret YAHOO_COOKIES.

Run on your Mac; macOS asks once to allow Keychain access (e.g. "Brave Safe Storage"):

    uv run --group local yahoo_session.py

Only the main Yahoo login cookies are saved (the ones on .yahoo.com / login.yahoo.com, which last about
six months), each with its domain and expiry. The Fantasy sites' own short-lived session is re-issued
from that login on every run, the same way a browser does it, so the saved login keeps working until
the main cookies expire (or Yahoo signs you out). Nothing is printed except the expiry date.
"""
import datetime
import json
import subprocess
import sys

import browser_cookie3

REPO = "robSanders818/fantasy-desk"
LOGIN_DOMAINS = {".yahoo.com", "yahoo.com", ".login.yahoo.com", "login.yahoo.com"}

BROWSERS = [("Brave", browser_cookie3.brave), ("Chrome", browser_cookie3.chrome),
            ("Arc", getattr(browser_cookie3, "arc", None)), ("Edge", browser_cookie3.edge),
            ("Chromium", browser_cookie3.chromium)]


def main() -> None:
    cookies, used = [], None
    for name, loader in BROWSERS:
        if loader is None:
            continue
        try:
            jar = loader(domain_name="yahoo.com")
        except Exception:
            continue                      # browser not installed / no cookie store
        found = [{"name": c.name, "value": c.value, "domain": c.domain, "path": c.path or "/",
                  "expires": c.expires, "secure": bool(c.secure)}
                 for c in jar if c.domain in LOGIN_DOMAINS]
        if any(c["name"] in ("T", "Y") for c in found):
            cookies, used = found, name
            break
    if not cookies:
        sys.exit("No Yahoo login found in Brave/Chrome/Arc/Edge/Chromium. Log in to Yahoo Fantasy in your browser first.")
    login_exp = [c["expires"] for c in cookies if c["name"] in ("T", "Y") and c["expires"]]
    good_until = datetime.date.fromtimestamp(min(login_exp)).isoformat() if login_exp else "unknown"
    subprocess.run(["gh", "secret", "set", "YAHOO_COOKIES", "--repo", REPO],
                   input=json.dumps(cookies).encode(), check=True)
    print(f"Saved the Yahoo login from {used} ({len(cookies)} cookies) to {REPO} as YAHOO_COOKIES.")
    print(f"Login cookies are valid until {good_until} unless Yahoo signs you out sooner.")


if __name__ == "__main__":
    main()

"""Scrape the Yahoo basketball league pages with the saved session (no browser needed).

Pages (league 13126, my team 9), about 30-45 requests paced 2.5 s apart:
  /{t}?stat1=AS&stat2=AS_2026         10 team rosters with 2026-27 per-game stats, slots, statuses
  /players?status=A&pos=P&...          top 150 free agents, 2026-27 and 2025-26 per-game stats
  /                                    this week's opponent (scoreboard matchup links)
  /{t}?date=D&stat1=S&stat2=D          each day's active-lineup stats (today's live) -> week-to-date totals
                                       (the matchup page only loads its scores with JavaScript)
  /transactions                        my adds this week

Nothing here prints player or team data (Actions logs on a public repo are public).
"""
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime

import requests
from bs4 import BeautifulSoup

LEAGUE, ME, N_TEAMS = 13126, 9, 10
BASE = f"https://basketball.fantasysports.yahoo.com/nba/{LEAGUE}"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
PAUSE = 2.5
STATUS = re.compile(r"^(INJ|O|GTD|DTD|NA|SUSP|OFS|IL|D|Q|P)$")
TEAM_POS = re.compile(r"^[A-Za-z]{2,4} - [A-Z,]+$")
PLAYER_HREF = re.compile(r"/nba/players/(\d+)$")
STATS = ["GP*", "MPG", "FGM/A*", "FTM/A*", "3PTM", "PTS", "REB", "AST", "ST", "BLK", "TO"]


class SessionExpired(Exception):
    pass


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", "".join(ch for ch in s if not 0xE000 <= ord(ch) <= 0xF8FF)).strip()


@dataclass
class Yahoo:
    cookies: dict
    s: requests.Session = field(init=False)
    requests_made: int = 0

    def __post_init__(self):
        self.s = requests.Session()
        self.s.cookies.update(self.cookies)
        self.s.headers["User-Agent"] = UA

    @classmethod
    def from_env(cls) -> "Yahoo":
        return cls(json.loads(os.environ["YAHOO_COOKIES"]))

    def get(self, path: str) -> BeautifulSoup:
        if self.requests_made:
            time.sleep(PAUSE)
        r = self.s.get(f"{BASE}{path}", timeout=30)
        self.requests_made += 1
        if r.status_code == 999:
            raise RuntimeError("Yahoo rate limit (999)")
        if "login.yahoo.com" in r.url:
            raise SessionExpired()
        r.raise_for_status()
        return BeautifulSoup(r.text, "lxml")


def _player(row) -> tuple[int, str, str, str] | None:
    a = next((a for a in row.select("a[href]") if PLAYER_HREF.search(a["href"])), None)
    if a is None:
        return None
    texts = [clean(e.get_text()) for e in row.select("span, abbr")]
    team_pos = next((t for t in texts if TEAM_POS.match(t)), "")
    status = next((t for t in texts if STATUS.match(t)), "")
    return int(PLAYER_HREF.search(a["href"]).group(1)), clean(a.get_text()), team_pos, status


def rosters(y: Yahoo) -> list[dict]:
    """Every team's roster with 2026-27 per-game stats (the stats_*.psv format)."""
    out = []
    for t in range(1, N_TEAMS + 1):
        doc = y.get(f"/{t}?stat1=AS&stat2=AS_2026")
        tbl = doc.select_one("#statTable0")
        if tbl is None:
            raise RuntimeError(f"no roster table for team {t}")
        hdr = [clean(c.get_text()) for c in tbl.select("thead tr")[-1].find_all(["th", "td"])]
        for row in tbl.select("tbody tr"):
            p = _player(row)
            if p is None:
                continue
            cells = [clean(c.get_text()) for c in row.find_all("td")]
            off = len(cells) - len(hdr)
            g = {k: cells[hdr.index(k) + off] for k in STATS}
            out.append({"team_id": t, "slot": cells[0], "player_id": p[0], "name": p[1], "team_pos": p[2],
                        "status": p[3], "GP": g["GP*"], "MPG": g["MPG"], "FGMA": g["FGM/A*"], "FTMA": g["FTM/A*"],
                        **{k: g[k] for k in ["3PTM", "PTS", "REB", "AST", "ST", "BLK", "TO"]}})
    return out


def _fa_line(c: list[str]) -> str:
    n = len(c)
    return ",".join([c[n - 17], c[n - 12], c[n - 10], *c[n - 8:n - 1]])


def free_agents(y: Yahoo, n: int = 150) -> list[dict]:
    """Top available players by current rank, with 2026-27 and 2025-26 per-game lines."""
    cur, ly, meta = {}, {}, {}
    for stat, store in (("S_AS_2026", cur), ("S_AS_2025", ly)):
        for off in range(0, n, 25):
            doc = y.get(f"/players?status=A&pos=P&stat1={stat}&sort=AR&sdir=1&count={off}")
            for row in doc.select("tbody tr"):
                p = _player(row)
                if p is None:
                    continue
                c = [clean(x.get_text()) for x in row.find_all("td")]
                gp = c[len(c) - 17]
                store[p[0]] = "" if gp in ("", "-") else _fa_line(c)
                avail = c[len(c) - 18]
                meta.setdefault(p[0], (p[1], p[2], p[3], re.sub(r"W \((\w+ \d+)\)", r"W\1", avail)))
    return [{"player_id": pid, "name": m[0], "team_pos": m[1], "status": m[2], "avail": m[3],
             "cur": cur.get(pid, ""), "ly": ly.get(pid, "")} for pid, m in meta.items()]


def _pairs(doc) -> tuple[int | None, list[list[int]]]:
    week, pairs = None, []
    for a in doc.select("a[href]"):
        m = re.search(r"matchup\?week=(\d+)&mid1=(\d+)&mid2=(\d+)", a["href"])
        if m:
            week = int(m.group(1))
            p = sorted([int(m.group(2)), int(m.group(3))])
            if p not in pairs:
                pairs.append(p)
    return week, pairs


def matchup_pairs(y: Yahoo, week: int) -> list[list[int]]:
    """Every [team_a, team_b] matchup in a given week (from that week's scoreboard)."""
    return _pairs(y.get(f"/?matchup_week={week}"))[1]


def league_home(y: Yahoo) -> tuple[int, int, list[dict], list[list[int]]]:
    """(week number, opponent team id, standings, this week's matchup pairs) from the league home page."""
    doc = y.get("/")
    week, pairs = _pairs(doc)
    mine = next((p for p in pairs if ME in p), None)
    if mine is None:
        raise RuntimeError("couldn't find this week's matchup on the scoreboard")
    opp = mine[0] if mine[1] == ME else mine[1]
    standings = []
    for t in doc.select("table"):
        rows = t.select("tr")
        hdr = [clean(c.get_text()) for c in rows[0].find_all(["th", "td"])] if rows else []
        if "W-L-T" not in hdr or "Rank" not in hdr:
            continue
        for r in rows[1:]:
            links = [a for a in r.select("a[href]") if re.search(rf"/nba/{LEAGUE}/\d+$", a["href"])]
            link = next((a for a in links if clean(a.get_text())), links[0] if links else None)   # skip the logo link
            if link is None:
                continue
            c = dict(zip(hdr, [clean(x.get_text()) for x in r.find_all(["td", "th"])]))
            standings.append({"team_id": int(re.search(r"(\d+)$", link["href"]).group(1)), "team": clean(link.get_text()),
                              "rank": int(c["Rank"]) if c.get("Rank", "").isdigit() else None, "record": c.get("W-L-T", "")})
        break
    return week, opp, standings, pairs


# Game status next to a player on a day's lineup: "W, 130-103 vs SAC" (final), "Q1 2:25, 26-33 @ LAL" (live),
# "7:00 pm @ CHA" (not started), or nothing (no game).
STARTED = re.compile(r"(?:^|\s)(?:[WL], \d+-\d+|Q[1-4]\b|OT\b|\dOT\b|Half|End of|Final)")


def day_totals(y: Yahoo, team: int, day: date) -> tuple[list[float], set[str]]:
    """Counting stats a team has banked on one date (live for today): players in active slots only
    (bench/IL don't count). Returns ([FGM, FGA, FTM, FTA, 3PTM, PTS, REB, AST, ST, BLK, TO], names
    of the team's players whose game that day has started or finished)."""
    doc = y.get(f"/{team}?date={day.isoformat()}&stat1=S&stat2=D")
    tbl = doc.select_one("#statTable0")
    hdr = [clean(c.get_text()) for c in tbl.select("thead tr")[-1].find_all(["th", "td"])]
    tot = [0.0] * 11
    started = set()
    for row in tbl.select("tbody tr"):
        p = _player(row)
        if p is None:
            continue
        cell = next((td for td in row.find_all("td") if td.select_one("a[href*='/nba/players/']")), None)
        game = re.sub(r".*?[A-Z]{2,4} - [A-Z,]+", "", clean(cell.get_text(" "))) if cell else ""
        if STARTED.search(game):
            started.add(p[1])
        c = [clean(x.get_text()) for x in row.find_all("td")]
        if c[0] in ("BN", "IL", "IL+"):
            continue
        off = len(c) - len(hdr)
        g = lambda k: c[hdr.index(k) + off]
        fg, ft = g("FGM/A*"), g("FTM/A*")
        if "/" not in fg or fg.startswith("-"):
            continue                               # no game that day
        vals = [*fg.split("/"), *ft.split("/")] + [g(k) for k in ["3PTM", "PTS", "REB", "AST", "ST", "BLK", "TO"]]
        tot = [t + (float(v) if v not in ("-", "") else 0.0) for t, v in zip(tot, vals)]
    return tot, started


def fmt_banked(t: list[float]) -> str | None:
    """[FGM, FGA, FTM, FTA, ...] -> stream.py's --banked string (None if nothing banked yet)."""
    if not any(t):
        return None
    t = [int(round(v)) for v in t]
    return f"{t[0]}/{t[1]},{t[2]}/{t[3]}," + ",".join(str(v) for v in t[4:])


def banked(y: Yahoo, team: int, days: list[date], today: date) -> tuple[str | None, set[str]]:
    """Week-to-date totals in stream.py's --banked format: finished days plus today's live stats.
    Also returns the players whose game today has already started (the model skips them today)."""
    tot, started = [0.0] * 11, set()
    for d in days + [today]:
        day_tot, s = day_totals(y, team, d)
        tot = [a + b for a, b in zip(tot, day_tot)]
        if d == today:
            started = s
    if not any(tot):
        return None, started
    t = [int(round(v)) for v in tot]
    return f"{t[0]}/{t[1]},{t[2]}/{t[3]}," + ",".join(str(v) for v in t[4:]), started


def adds_this_week(y: Yahoo, week_start: date, season_year: int) -> int:
    """My adds (from free agents or waivers) since the week started."""
    doc = y.get("/transactions")
    n = 0
    for row in doc.select("table tr"):
        if not any(re.search(rf"/nba/{LEAGUE}/{ME}$", a["href"]) for a in row.select("a[href]")):
            continue
        text = clean(row.get_text(" "))
        m = re.search(r"([A-Z][a-z]{2}) (\d{1,2}), \d{1,2}:\d{2} [ap]m", text)
        if not m:
            continue
        mon = datetime.strptime(m.group(1), "%b").month
        when = date(season_year + (1 if mon < 7 else 0), mon, int(m.group(2)))
        if when >= week_start and ("Free Agent" in text or "Waivers" in text.replace("To Waivers", "")):
            n += 1
    return n

"""Scrape the Yahoo hockey league (What the Puck, 41313; my team 1) with the saved session.

  /{t}?stat1=P&stat2=PSR|PS7           rosters with Yahoo's rest-of-season / next-7-days projections
  /players?status=A&pos=P|G&stat1=P_PSR  free agents with Yahoo's rest-of-season projection
  /                                    this week's number, matchup pairs, standings
  /?matchup_week=W                     every matchup's live points and Yahoo projection for week W
  /{t}?date=D&stat1=S&stat2=D          a team's lineup that day: each player's slot, fantasy points,
                                       raw stats, and whether his game has started
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

LEAGUE, ME = 41313, 1
TEAM_IDS = [1, 2, 3, 4, 6, 7, 8, 9]          # there is no team 5
BASE = f"https://hockey.fantasysports.yahoo.com/hockey/{LEAGUE}"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
PAUSE = 2.5
STATUS = re.compile(r"^(IR|IR\+|IR-LT|IR-NR|O|DTD|NA|SUSP)$")
TEAM_POS = re.compile(r"^[A-Za-z]{2,4} - [A-Z,]+$")
PLAYER_HREF = re.compile(r"/nhl/players/(\d+)$")
SKATER_STATS = ["G", "A", "+/-", "PIM", "PPP", "SHG", "SHA", "SOG", "FW", "FL", "HIT", "BLK"]
GOALIE_STATS = ["W", "GA", "SV", "SHO"]
STARTED = re.compile(r"(?:^|\s)(?:[WL], \d+-\d+|(?:OT|SO)?L?, \d+-\d+|P[1-3]\b|1st|2nd|3rd|OT\b|SO\b|Int\b|End|Final)")


class SessionExpired(Exception):
    pass


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", "".join(ch for ch in s if not 0xE000 <= ord(ch) <= 0xF8FF)).strip()


def num(x: str) -> float:
    x = (x or "").replace(",", "").strip()
    try:
        return float(x)
    except ValueError:
        return 0.0


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
        for attempt in range(3):                 # Yahoo occasionally stalls; retry timeouts / resets
            try:
                r = self.s.get(f"{BASE}{path}", timeout=30)
                break
            except (requests.Timeout, requests.ConnectionError):
                if attempt == 2:
                    raise
                time.sleep(5 * (attempt + 1))
        self.requests_made += 1
        if r.status_code == 999:
            raise RuntimeError("Yahoo rate limit (999)")
        if "login.yahoo.com" in r.url:
            raise SessionExpired()
        r.raise_for_status()
        return BeautifulSoup(r.text, "lxml")


def _player(row):
    a = next((a for a in row.select("a[href]") if PLAYER_HREF.search(a["href"])), None)
    if a is None:
        return None
    texts = [clean(e.get_text()) for e in row.select("span, abbr")]
    team_pos = next((t for t in texts if TEAM_POS.match(t)), "")
    status = next((t for t in texts if STATUS.match(t)), "")
    return int(PLAYER_HREF.search(a["href"]).group(1)), clean(a.get_text()), team_pos, status


def _table_rows(tbl):
    """Yield (header map, cells, player, row) for each player row; header-aligned from the right."""
    hdr = [clean(c.get_text()) for c in tbl.select("thead tr")[-1].find_all(["th", "td"])]
    for row in tbl.select("tbody tr"):
        p = _player(row)
        if p is None:
            continue
        cells = [clean(c.get_text(" ")) for c in row.find_all("td")]
        off = len(cells) - len(hdr)
        g = {h: cells[i + off] for i, h in enumerate(hdr) if 0 <= i + off < len(cells)}
        yield g, cells, p, row


def rosters(y: Yahoo) -> list[dict]:
    """Every team's roster with Yahoo's rest-of-season and next-7-days fantasy points (the
    rosters_*.psv columns model.py reads)."""
    out = {}
    for t in TEAM_IDS:
        for view in ("PSR", "PS7"):
            doc = y.get(f"/{t}?stat1=P&stat2={view}")
            for tbl in doc.select("table[id^=statTable]"):
                for g, cells, p, _ in _table_rows(tbl):
                    r = out.setdefault((t, p[0]), {"team_id": t, "slot": cells[0], "yid": p[0], "name": p[1],
                                                   "team_pos": p[2], "status": p[3]})
                    if view == "PSR":
                        r.update(y_ros_fp=num(g.get("Fan Pts")), y_ros_sog=g.get("SOG", ""), y_ros_fw=g.get("FW", ""))
                    else:
                        r["y_next7_fp"] = num(g.get("Fan Pts"))
    return list(out.values())


def free_agents(y: Yahoo, skaters: int = 200, goalies: int = 50) -> list[dict]:
    out = []
    for pos, n in (("P", skaters), ("G", goalies)):
        for off in range(0, n, 25):
            doc = y.get(f"/players?status=A&pos={pos}&stat1=P_PSR&sort=AR&sdir=1&count={off}")
            tbl = doc.select_one("table")
            if tbl is None:
                continue
            for g, cells, p, _ in _table_rows(tbl):
                out.append({"slot": g.get("Roster Status", "FA"), "yid": p[0], "name": p[1], "team_pos": p[2],
                            "status": p[3], "y_ros_fp": num(g.get("Fan Pts")), "y_ros_fw": g.get("FW", "")})
    return out


def _pairs_and_scores(doc) -> tuple[int | None, list[dict]]:
    week, games = None, []
    for li in doc.select("li"):
        a = li.select_one("a[href*='matchup?week=']")
        m = a and re.search(r"matchup\?week=(\d+)&mid1=(\d+)&mid2=(\d+)", a["href"])
        if not m:
            continue
        week = int(m.group(1))
        nums = [float(x) for x in re.findall(r"\d+\.\d\d", clean(li.get_text(" ")))]
        g = {"a": int(m.group(2)), "b": int(m.group(3))}
        if len(nums) >= 4:
            g.update(pts_a=nums[0], proj_a=nums[1], pts_b=nums[2], proj_b=nums[3])
        if not any(x["a"] == g["a"] and x["b"] == g["b"] for x in games):
            games.append(g)
    return week, games


def scoreboard(y: Yahoo, week: int) -> list[dict]:
    """Every matchup in a week: {a, b, pts_a, proj_a, pts_b, proj_b} (live for the current week)."""
    return _pairs_and_scores(y.get(f"/?matchup_week={week}"))[1]


def league_home(y: Yahoo) -> dict:
    doc = y.get("/")
    week, games = _pairs_and_scores(doc)
    mine = next((g for g in games if ME in (g["a"], g["b"])), None)
    if mine is None:
        raise RuntimeError("couldn't find this week's matchup")
    standings = []
    for t in doc.select("table"):
        rows = t.select("tr")
        hdr = [clean(c.get_text()) for c in rows[0].find_all(["th", "td"])] if rows else []
        if "W-L-T" not in hdr:
            continue
        for r in rows[1:]:
            links = [a for a in r.select("a[href]") if re.search(rf"/hockey/{LEAGUE}/\d+$", a["href"])]
            link = next((a for a in links if clean(a.get_text())), None)
            if link is None:
                continue
            c = dict(zip(hdr, [clean(x.get_text()) for x in r.find_all(["td", "th"])]))
            standings.append({"team_id": int(re.search(r"(\d+)$", link["href"]).group(1)), "team": clean(link.get_text()),
                              "rank": int(c["Rank"]) if c.get("Rank", "").isdigit() else None,
                              "record": c.get("W-L-T", ""), "pf": num(c.get("Pts", ""))})
        break
    return {"week": week, "opp": mine["b"] if mine["a"] == ME else mine["a"], "games": games, "standings": standings}


def day(y: Yahoo, team: int, d: date) -> dict:
    """A team's lineup on one date: per-player fantasy points and stats, active-slot team totals
    (what counts in the matchup), and which players' games have started."""
    doc = y.get(f"/{team}?date={d.isoformat()}&stat1=S&stat2=D")
    players, totals, pts, started = {}, {k: 0.0 for k in SKATER_STATS + GOALIE_STATS}, 0.0, []
    for tbl, keys in ((doc.select_one("#statTable0"), SKATER_STATS), (doc.select_one("#statTable1"), GOALIE_STATS)):
        if tbl is None:
            continue
        for g, cells, p, row in _table_rows(tbl):
            slot = cells[0]
            active = slot not in ("BN", "IR", "IR+", "NA")
            fp = num(g.get("Fan Pts"))
            stats = {k: num(g.get(k)) for k in keys}
            cell = next((td for td in row.find_all("td") if td.select_one("a[href*='/nhl/players/']")), None)
            game = re.sub(r".*?[A-Z]{2,4} - [A-Z,]+", "", clean(cell.get_text(" "))) if cell else ""
            has_stats = any(g.get(k, "-") not in ("-", "") for k in keys)
            if STARTED.search(game) or has_stats:
                started.append(p[0])
            players[str(p[0])] = [p[1], round(fp, 2), active, slot]
            if active:
                pts += fp
                for k, v in stats.items():
                    totals[k] += v
    return {"pts": round(pts, 2), "stats": totals, "players": players, "started": started}


def adds_this_week(y: Yahoo, week_start: date, season_year: int) -> int:
    doc = y.get("/transactions")
    n = 0
    for row in doc.select("table tr"):
        if not any(re.search(rf"/hockey/{LEAGUE}/{ME}$", a["href"]) for a in row.select("a[href]")):
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

"""Daily basketball update: scrape Yahoo -> run the week planner -> write the league JSON.

    uv run pipeline/run_basketball.py                 # CI: $YAHOO_COOKIES, $FD_PASSPHRASE
    uv run --group local pipeline/run_basketball.py --local    # on the Mac: cookies from Brave

Writes pipeline/out/basketball.json (gitignored). scripts/encrypt.py turns it into the page's
data file. Logs only counts and timings -- never player or team data (public Actions logs).
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
BB = ROOT / "basketball"
OUT = ROOT / "out"
sys.path.insert(0, str(BB))
import yahoo as Y  # noqa: E402

SEASON_YEAR = 2026
SEASON_START = date(2026, 10, 20)
ADDS_PER_WEEK = 3
IL_SLOTS = 6
LONG_OUT = {"INJ", "OFS", "SUSP", "NA"}     # out all week
SHORT_OUT = {"O"}                           # Yahoo "Out": treat as out today only


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def week_bounds(today: date) -> tuple[date, date]:
    monday = today - timedelta(days=today.weekday())
    return max(monday, SEASON_START), monday + timedelta(days=6)


def write_psv(path: Path, rows: list[dict], cols: list[str]) -> None:
    with path.open("w") as f:
        f.write("|".join(cols) + "\n")
        for r in rows:
            f.write("|".join(str(r.get(c, "")).replace("|", "/") for c in cols) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true", help="use Yahoo cookies from Brave instead of $YAHOO_COOKIES")
    ap.add_argument("--today", help="override today's date (YYYY-MM-DD, Eastern)")
    a = ap.parse_args()
    t0 = time.time()
    OUT.mkdir(exist_ok=True)
    status = {"yahoo": "ok", "errors": []}

    if not (BB / "data" / "league").exists():
        subprocess.run([sys.executable, str(ROOT / "inputs.py"), "unpack", "basketball"], check=True)

    if a.local:
        import browser_cookie3
        y = Y.Yahoo({c.name: c.value for c in browser_cookie3.brave(domain_name="yahoo.com")})
    else:
        y = Y.Yahoo.from_env()

    today = date.fromisoformat(a.today) if a.today else datetime.now(ZoneInfo("America/New_York")).date()
    wk_start, wk_end = week_bounds(today)
    played = [wk_start + timedelta(days=i) for i in range((today - wk_start).days)]

    try:
        rosters = Y.rosters(y)
        log(f"rosters: {len(rosters)} players")
        fas = Y.free_agents(y)
        log(f"free agents: {len(fas)}")
        week_no, opp, standings = Y.league_home(y)
        bank_me, started_me = Y.banked(y, Y.ME, played, today)
        bank_opp, started_opp = Y.banked(y, opp, played, today)
        log(f"week {week_no}: banked {len(played)} finished day(s) + today ({len(started_me | started_opp)} players' games already started)")
        adds_used = Y.adds_this_week(y, wk_start, SEASON_YEAR)
    except Y.SessionExpired:
        status["yahoo"] = "expired"
        log("Yahoo session expired -- re-run yahoo_session.py")
        (OUT / "status.json").write_text(json.dumps(status))
        sys.exit(2)
    log(f"Yahoo: {y.requests_made} requests in {time.time() - t0:.0f}s")

    season_dir = BB / "data" / "season"
    season_dir.mkdir(parents=True, exist_ok=True)
    stats_path, fa_path = season_dir / "stats_today.psv", season_dir / "fa_today.psv"
    rostered = {r["player_id"] for r in rosters}
    write_psv(stats_path, rosters, ["team_id", "slot", "player_id", "name", "team_pos", "status", "GP", "MPG",
                                    "FGMA", "FTMA", "3PTM", "PTS", "REB", "AST", "ST", "BLK", "TO"])
    write_psv(fa_path, [f for f in fas if f["player_id"] not in rostered and f["status"] not in LONG_OUT | SHORT_OUT],
              ["player_id", "name", "team_pos", "status", "avail", "cur", "ly"])

    # Yahoo "O" on a player still in an active/bench slot: out today, back after. IL slot or INJ: out all week.
    mine = [r for r in rosters if r["team_id"] == Y.ME]
    theirs = [r for r in rosters if r["team_id"] == opp]
    # ...and anyone whose game today has already started is counted in the live totals, not simulated again.
    started = started_me | started_opp
    out_days = [f"{r['name']}={today.isoformat()}" for r in mine + theirs
                if (r["status"] in SHORT_OUT and r["slot"] not in ("IL", "IL+"))
                or (r["name"] in started and r["status"] not in LONG_OUT and r["slot"] not in ("IL", "IL+"))]
    adds_left = max(ADDS_PER_WEEK - adds_used, 0)

    alerts = []
    il_used = sum(r["slot"] in ("IL", "IL+") for r in mine)
    for r in mine:
        if r["slot"] not in ("IL", "IL+") and r["status"] in LONG_OUT | SHORT_OUT and il_used < IL_SLOTS:
            alerts.append({"kind": "il", "text": f"Move {r['name']} to IL (listed {r['status']}) to open a roster spot."})
        if r["slot"] in ("IL", "IL+") and r["status"] not in LONG_OUT | SHORT_OUT | {"IL"}:
            alerts.append({"kind": "activate", "text": f"{r['name']} is no longer listed out -- activate him from IL."})
    if adds_left == 0:
        alerts.append({"kind": "info", "text": "No adds left this week -- free-agent values shown for planning only."})

    standings_path = season_dir / "standings.json"
    standings_path.write_text(json.dumps(standings))

    json_path = OUT / "basketball.json"
    cmd = [sys.executable, str(BB / "stream.py"), "--opp", str(opp),
           "--start", today.isoformat(), "--end", wk_end.isoformat(), "--first-add", today.isoformat(),
           "--adds", str(adds_left), "--stats", str(stats_path), "--fa", str(fa_path), "--json", str(json_path)]
    if bank_me and bank_opp:
        cmd += ["--banked", bank_me, bank_opp]
    if out_days:
        cmd += ["--out-days", *out_days]
    t1 = time.time()
    r = subprocess.run(cmd, cwd=BB, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        # The traceback can name players; keep only the exception type in the public log.
        last = (r.stderr.strip().splitlines() or ["?"])[-1].split(":")[0]
        log(f"model failed: {last}")
        sys.exit(1)
    log(f"model: {time.time() - t1:.0f}s")

    t2 = time.time()
    rank_path = OUT / "rankings.json"
    r = subprocess.run([sys.executable, str(BB / "rankings.py"), str(stats_path), str(standings_path), str(rank_path)],
                       cwd=BB, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        log(f"rankings failed: {(r.stderr.strip().splitlines() or ['?'])[-1].split(':')[0]}")
        status["errors"].append("rankings")
    else:
        log(f"rankings: {time.time() - t2:.0f}s")

    d = json.loads(json_path.read_text())
    d["rankings"] = json.loads(rank_path.read_text()) if rank_path.exists() and r.returncode == 0 else []
    d["my_team_id"] = Y.ME
    d["week"] = {"number": week_no, "start": wk_start.isoformat(), "end": wk_end.isoformat(), "sim_from": today.isoformat()}
    d["adds_used"] = adds_used
    d["alerts"] = alerts
    d["status"] = {**status, "scraped_at": datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="minutes"),
                   "days_banked": len(played), "live_today": len(started)}
    json_path.write_text(json.dumps(d, ensure_ascii=False))
    log(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()

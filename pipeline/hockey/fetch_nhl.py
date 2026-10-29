"""Pull NHL stats and the schedule from the public NHL API (no auth).

    uv run fetch_nhl.py [--seasons 20232024 20242025 20252026 20262027]

Writes:
    data/nhl/skaters.csv   one row per player-season (regular season): every stat the league scores
    data/nhl/goalies.csv   one row per goalie-season
    data/nhl/schedule.csv  2026-27 regular-season games: date, home, away, game_id, state
    data/nhl/goalie_games.csv  2026-27 goalie game logs so far (who started each game)
"""
import argparse, json, time, urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
OUT = ROOT / "data" / "nhl"
STATS = "https://api.nhle.com/stats/rest/en"
WEB = "https://api-web.nhle.com/v1"
TEAMS = ["ANA", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI", "COL", "DAL", "DET", "EDM", "FLA", "LAK", "MIN",
         "MTL", "NJD", "NSH", "NYI", "NYR", "OTT", "PHI", "PIT", "SEA", "SJS", "STL", "TBL", "TOR", "UTA",
         "VAN", "VGK", "WPG", "WSH"]


def get(url):
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            time.sleep(2 * (i + 1))
    raise RuntimeError(url)


def report(kind, name, season):
    rows, start = [], 0
    while True:
        exp = f"seasonId={season}%20and%20gameTypeId=2"
        # A stable sort is required: unsorted pages repeat some players and skip others.
        sort = "%5B%7B%22property%22:%22playerId%22,%22direction%22:%22ASC%22%7D%5D"
        d = get(f"{STATS}/{kind}/{name}?limit=100&start={start}&sort={sort}&cayenneExp={exp}")
        rows += d["data"]
        start += 100
        if start >= d["total"]:
            return pd.DataFrame(rows).drop_duplicates("playerId")


def skaters(season):
    s = report("skater", "summary", season)
    r = report("skater", "realtime", season)[["playerId", "hits", "blockedShots"]]
    f = report("skater", "faceoffwins", season)[["playerId", "totalFaceoffWins", "totalFaceoffLosses"]]
    df = s.merge(r, on="playerId", how="left").merge(f, on="playerId", how="left")
    df = df.rename(columns={"skaterFullName": "name", "teamAbbrevs": "teams", "positionCode": "pos",
                            "gamesPlayed": "GP", "goals": "G", "assists": "A", "plusMinus": "PM",
                            "penaltyMinutes": "PIM", "ppPoints": "PPP", "shGoals": "SHG", "shots": "SOG",
                            "totalFaceoffWins": "FW", "totalFaceoffLosses": "FL", "hits": "HIT",
                            "blockedShots": "BLK", "timeOnIcePerGame": "TOI"})
    df["SHA"] = df["shPoints"] - df["SHG"]
    df["season"] = season
    return df[["season", "playerId", "name", "pos", "teams", "GP", "TOI", "G", "A", "PM", "PIM", "PPP",
               "SHG", "SHA", "SOG", "FW", "FL", "HIT", "BLK"]]


def goalies(season):
    g = report("goalie", "summary", season).rename(columns={
        "goalieFullName": "name", "teamAbbrevs": "teams", "gamesPlayed": "GP", "gamesStarted": "GS",
        "wins": "W", "goalsAgainst": "GA", "saves": "SV", "shutouts": "SHO", "shotsAgainst": "SA"})
    g["season"] = season
    return g[["season", "playerId", "name", "teams", "GP", "GS", "W", "GA", "SV", "SA", "SHO"]]


def schedule(season):
    seen, rows = set(), []
    for t in TEAMS:
        for g in get(f"{WEB}/club-schedule-season/{t}/{season}")["games"]:
            if g["gameType"] != 2 or g["id"] in seen:
                continue
            seen.add(g["id"])
            rows.append({"game_id": g["id"], "date": g["gameDate"], "home": g["homeTeam"]["abbrev"],
                         "away": g["awayTeam"]["abbrev"], "state": g["gameState"]})
        time.sleep(0.3)
    return pd.DataFrame(rows).sort_values(["date", "game_id"])


def goalie_games(season, ids):
    rows = []
    for pid in ids:
        d = get(f"{WEB}/player/{pid}/game-log/{season}/2")
        for g in d.get("gameLog", []):
            rows.append({"playerId": pid, "date": g["gameDate"], "team": g["teamAbbrev"],
                         "GS": g.get("gamesStarted", 0), "decision": g.get("decision", ""),
                         "SA": g.get("shotsAgainst", 0), "GA": g.get("goalsAgainst", 0),
                         "SHO": g.get("shutouts", 0)})
        time.sleep(0.2)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="*", type=int, default=[20212022, 20222023, 20232024, 20242025, 20252026, 20262027])
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    sk = pd.concat([skaters(s) for s in args.seasons])
    go = pd.concat([goalies(s) for s in args.seasons])
    sk.to_csv(OUT / "skaters.csv", index=False)
    go.to_csv(OUT / "goalies.csv", index=False)
    cur = max(args.seasons)
    sched = schedule(cur)
    sched.to_csv(OUT / "schedule.csv", index=False)
    gg = goalie_games(cur, go[go.season == cur].playerId.unique())
    gg.to_csv(OUT / "goalie_games.csv", index=False)
    print(f"skaters {len(sk)}, goalies {len(go)}, games {len(sched)} "
          f"({(sched.state.isin(['FINAL', 'OFF'])).sum()} played), goalie game logs {len(gg)}")


if __name__ == "__main__":
    main()

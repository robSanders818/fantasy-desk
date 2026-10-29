"""Daily hockey update (What the Puck, Yahoo 41313): NHL refresh -> Yahoo scrape -> models -> hockey.json.

    uv run pipeline/run_hockey.py                          # CI: $YAHOO_COOKIES, $FD_PASSPHRASE
    uv run --group local pipeline/run_hockey.py --local    # on the Mac: cookies from Brave

Writes pipeline/out/hockey.json. Logs only counts and timings (public Actions logs).
"""
import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
HK = ROOT / "hockey"
OUT = ROOT / "out"
sys.path.insert(0, str(HK))
sys.path.insert(0, str(ROOT))
import cache as C  # noqa: E402
import fetch_nhl as F  # noqa: E402
import yahoo_hk as Y  # noqa: E402
from scoring import GOALIE, SKATER  # noqa: E402

SEASON_YEAR = 2026
CUR = 20262027
WEEK1_START, WEEK2_START = date(2026, 9, 29), date(2026, 10, 5)
REG_WEEKS, PLAYOFF_SPOTS, ADDS_PER_WEEK = 24, 4, 5
# Yahoo stat label -> scoring weight
WEIGHTS = {"G": SKATER["G"], "A": SKATER["A"], "+/-": SKATER["PM"], "PIM": SKATER["PIM"], "PPP": SKATER["PPP"],
           "SHG": SKATER["SHG"], "SHA": SKATER["SHA"], "SOG": SKATER["SOG"], "FW": SKATER["FW"], "FL": SKATER["FL"],
           "HIT": SKATER["HIT"], "BLK": SKATER["BLK"], "W": GOALIE["W"], "GA": GOALIE["GA"], "SV": GOALIE["SV"],
           "SHO": GOALIE["SHO"]}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def week_of(d: date) -> int:
    return 1 if d < WEEK2_START else 2 + (d - WEEK2_START).days // 7


def week_bounds(w: int) -> tuple[date, date]:
    if w == 1:
        return WEEK1_START, WEEK2_START - timedelta(days=1)
    s = WEEK2_START + timedelta(days=7 * (w - 2))
    return s, s + timedelta(days=6)


def refresh_nhl() -> None:
    """Current-season NHL stats, the schedule, and goalie starts (history CSVs are committed)."""
    out = HK / "data" / "nhl"
    for name, fn in (("skaters", F.skaters), ("goalies", F.goalies)):
        path = out / f"{name}.csv"
        old = pd.read_csv(path)
        pd.concat([old[old.season != CUR], fn(CUR)]).to_csv(path, index=False)
    F.schedule(CUR).to_csv(out / "schedule.csv", index=False)
    go = pd.read_csv(out / "goalies.csv")
    F.goalie_games(CUR, go[go.season == CUR].playerId.unique()).to_csv(out / "goalie_games.csv", index=False)


def write_psv(path: Path, rows: list[dict], cols: list[str]) -> None:
    with path.open("w") as f:
        f.write("|".join(cols) + "\n")
        for r in rows:
            f.write("|".join(str(r.get(c, "")).replace("|", "/") for c in cols) + "\n")


def stat_points(stats: dict) -> dict:
    return {k: round(stats.get(k, 0.0) * w, 1) for k, w in WEIGHTS.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--today")
    ap.add_argument("--skip-nhl", action="store_true", help="reuse the NHL files already on disk")
    a = ap.parse_args()
    t0 = time.time()
    OUT.mkdir(exist_ok=True)

    today = date.fromisoformat(a.today) if a.today else datetime.now(ZoneInfo("America/New_York")).date()
    week_no = week_of(today)
    wk_start, wk_end = week_bounds(week_no)

    if not a.skip_nhl:
        refresh_nhl()
        log(f"NHL refresh: {time.time() - t0:.0f}s")

    if a.local:
        import browser_cookie3
        y = Y.Yahoo({c.name: c.value for c in browser_cookie3.brave(domain_name="yahoo.com")})
    else:
        y = Y.Yahoo.from_env()

    store = C.load("hockey")
    store.setdefault("weeks", {})
    store.setdefault("days", {})
    try:
        ros = Y.rosters(y)
        fas = Y.free_agents(y)
        home = Y.league_home(y)
        log(f"rosters {len(ros)}, free agents {len(fas)}")
        week_no, opp = home["week"], home["opp"]
        wk_start, wk_end = week_bounds(week_no)
        names = {s["team_id"]: s["team"] for s in home["standings"]}
        store["weeks"][str(week_no)] = home["games"]
        # finished weeks' final scores and future weeks' pairs: fetched once, cached
        for w in range(1, REG_WEEKS + 1):
            if w == week_no:
                continue
            g = store["weeks"].get(str(w))
            if g is None or (w < week_no and not g[0].get("final")):
                g = Y.scoreboard(y, w)
                if w < week_no:
                    for x in g:
                        x["final"] = True
                store["weeks"][str(w)] = g
        # this week's daily lineups for every team (player points, stat breakdown, who's started)
        d = wk_start
        while d <= today:
            key = d.isoformat()
            if key not in store["days"] or d >= today - timedelta(days=1):
                store["days"][key] = {str(t): Y.day(y, t, d) for t in Y.TEAM_IDS}
            d += timedelta(days=1)
        adds_used = Y.adds_this_week(y, wk_start, SEASON_YEAR)
    except Y.SessionExpired:
        log("Yahoo session expired -- re-run yahoo_session.py")
        sys.exit(2)
    log(f"Yahoo: {y.requests_made} requests in {time.time() - t0:.0f}s")
    C.save("hockey", store)

    # ---------- model inputs ----------
    ydir = HK / "data" / "yahoo"
    ydir.mkdir(parents=True, exist_ok=True)
    write_psv(ydir / "rosters.psv", ros, ["team_id", "slot", "name", "team_pos", "status", "y_ros_fp", "y_next7_fp",
                                         "y_ros_sog", "y_ros_fw"])
    rostered = {r["yid"] for r in ros}
    write_psv(ydir / "fa.psv", [f for f in fas if f["yid"] not in rostered],
              ["slot", "name", "team_pos", "status", "y_ros_fp", "y_ros_fw"])
    res = [{"week": int(w), "team_a": g["a"], "team_b": g["b"], "pts_a": g["pts_a"], "pts_b": g["pts_b"]}
           for w, gs in store["weeks"].items() for g in gs if g.get("final") and "pts_a" in g]
    results = pd.DataFrame(res)

    import model  # noqa: E402
    from league import League, OUT_STATUS  # noqa: E402

    t1 = time.time()
    L = League(today.isoformat(), ydir / "rosters.psv", ydir / "fa.psv", results=results, teams=names)
    pl = L.pl
    by_name = {model.norm(n): pid for pid, n in pl.name.items()}
    today_day = store["days"].get(today.isoformat(), {})
    started_names = {pl_[0] for t in (Y.ME, opp) for yid, pl_ in today_day.get(str(t), {}).get("players", {}).items()
                     if int(yid) in today_day[str(t)]["started"]}
    L.skip_today = {by_name[model.norm(n)] for n in started_names if model.norm(n) in by_name}
    # Anyone (free agents too) whose NHL team's game today has already started can't help today.
    sch = pd.read_csv(HK / "data" / "nhl" / "schedule.csv")
    gone = sch[(sch.date == today.isoformat()) & ~sch.state.isin(["FUT", "PRE"])]
    started_teams = set(gone.home) | set(gone.away)
    L.skip_today |= set(pl.index[pl.team.isin(started_teams)])

    cur_games = {(g["a"], g["b"]): g for g in home["games"]}
    live = {}
    for g in home["games"]:
        live[g["a"]], live[g["b"]] = g.get("pts_a", 0.0), g.get("pts_b", 0.0)

    days, pm = L.plays(today.isoformat(), wk_end.isoformat())
    first_add = days[0] if days else None
    w0 = L.week(opp, today.isoformat(), wk_end.isoformat(), banked=(live[Y.ME], live[opp])) if days else None

    adds_left = max(ADDS_PER_WEEK - adds_used, 0)
    plan = L.stream(opp, today.isoformat(), wk_end.isoformat(), first_add, adds=adds_left, S=400) if days else None
    w1 = L.week(opp, today.isoformat(), wk_end.isoformat(), plan=plan["plan"], banked=(live[Y.ME], live[opp])) if plan else w0
    # The plan shown: maximize this week's points by cycling only the rotatable spots (no rest-of-season
    # cost) -- in practice, fitting the most games into the lineup.
    rot_ids = {p for p, v in plan["V"].items() if v <= 0.5} if plan else set()
    gplan = L.stream(opp, today.isoformat(), wk_end.isoformat(), first_add, adds=adds_left, S=400,
                     objective="week", drop_only=rot_ids) if days and rot_ids else None
    w2 = L.week(opp, today.isoformat(), wk_end.isoformat(), plan=gplan["plan"], banked=(live[Y.ME], live[opp])) if gplan else w0
    log(f"model: {time.time() - t1:.0f}s")

    def player(pid: int) -> dict:
        r = pl.loc[pid]
        return {"id": int(pid), "name": str(r["name"]), "team": str(r.team), "pos": str(r.elig), "status": str(r.status or "")}

    def games_from(pid: int, d: int) -> int:
        return int(pm.get(pl.at[pid, "team"], np.zeros(len(days), bool))[d:].sum()) if days else 0

    V = plan["V"] if plan else pd.Series(0.0, index=pl.index)

    # ---------- week so far: points by player and by stat ----------
    week_days = [k for k in sorted(store["days"]) if wk_start.isoformat() <= k <= today.isoformat()]
    team_stats, player_pts = {}, {}
    for t in Y.TEAM_IDS:
        tot = {k: 0.0 for k in WEIGHTS}
        pp = {}
        for k in week_days:
            day = store["days"][k].get(str(t))
            if not day:
                continue
            for s_, v in day["stats"].items():
                tot[s_] = tot.get(s_, 0.0) + v
            for yid, (nm, fp, act, slot) in day["players"].items():
                e = pp.setdefault(yid, {"name": nm, "pts": 0.0, "bench_pts": 0.0, "games": 0})
                if act:
                    e["pts"] += fp
                elif fp:
                    e["bench_pts"] += fp
                if fp:
                    e["games"] += 1
        team_stats[t] = stat_points(tot)
        player_pts[t] = sorted(({**v, "pts": round(v["pts"], 1), "bench_pts": round(v["bench_pts"], 1)}
                                for v in pp.values()), key=lambda r: -r["pts"])

    # ---------- this week vs every team; season; luck; playoff odds ----------
    vs = [{"team_id": t, "team": names.get(t, str(t)), "pts": live.get(t, 0.0), "opponent": t == opp,
           "result": "W" if live[Y.ME] > live.get(t, 0) else "L" if live[Y.ME] < live.get(t, 0) else "T",
           "by_stat": team_stats[t]} for t in Y.TEAM_IDS if t != Y.ME]
    vs.sort(key=lambda r: (-r["opponent"], r["pts"]))

    rank_df, sd = L.rank()
    mu = dict(zip(rank_df["id"], rank_df["proj_week"]))
    season = {t: {"w": 0, "l": 0, "t": 0, "pf": 0.0, "pa": 0.0, "ap_w": 0, "ap_l": 0, "ap_t": 0, "weeks": []} for t in Y.TEAM_IDS}
    for w in range(1, week_no + 1):
        gs = store["weeks"].get(str(w), [])
        pts = {}
        for g in gs:
            if "pts_a" in g:
                pts[g["a"]], pts[g["b"]] = g["pts_a"], g["pts_b"]
        for g in gs:
            if "pts_a" not in g:
                continue
            for me_, op_, mp, op in ((g["a"], g["b"], g["pts_a"], g["pts_b"]), (g["b"], g["a"], g["pts_b"], g["pts_a"])):
                s_ = season[me_]
                s_["weeks"].append({"week": w, "pts": mp, "opp_pts": op, "opp": op_, "final": w < week_no})
                if w < week_no:
                    s_["pf"] += mp
                    s_["pa"] += op
                    s_["w" if mp > op else "l" if mp < op else "t"] += 1
                    for o, p_ in pts.items():
                        if o != me_:
                            s_["ap_w" if mp > p_ else "ap_l" if mp < p_ else "ap_t"] += 1
    season_rows = []
    for t, s_ in season.items():
        n_ap = s_["ap_w"] + s_["ap_l"] + s_["ap_t"]
        ap_pct = (s_["ap_w"] + s_["ap_t"] / 2) / n_ap if n_ap else 0.0
        games = s_["w"] + s_["l"] + s_["t"]
        season_rows.append({"team_id": t, "team": names.get(t, str(t)), "record": [s_["w"], s_["l"], s_["t"]],
                            "pf": round(s_["pf"], 1), "pa": round(s_["pa"], 1),
                            "allplay": [s_["ap_w"], s_["ap_l"], s_["ap_t"]], "allplay_pct": round(ap_pct, 4),
                            "luck": round((s_["w"] + s_["t"] / 2) - ap_pct * games, 2), "weeks": s_["weeks"]})

    # Playoff odds: finish this week from the live score + projection, then simulate the rest.
    rng = np.random.default_rng(11)
    N = 20000
    base_w = np.array([season[t]["w"] + season[t]["t"] / 2 for t in Y.TEAM_IDS], float)
    base_pf = np.array([season[t]["pf"] for t in Y.TEAM_IDS], float)
    idx = {t: i for i, t in enumerate(Y.TEAM_IDS)}
    wins = np.repeat(base_w[None, :], N, 0)
    pf = np.repeat(base_pf[None, :], N, 0)
    frac_left = len(days) / 7 if days else 0.0
    for w in range(week_no, REG_WEEKS + 1):
        gs = store["weeks"].get(str(w), [])
        for g in gs:
            ia, ib = idx[g["a"]], idx[g["b"]]
            if w == week_no:
                ma = g.get("pts_a", 0.0) + mu[g["a"]] * frac_left
                mb = g.get("pts_b", 0.0) + mu[g["b"]] * frac_left
                s_ = sd * np.sqrt(max(frac_left, 0.05))
            else:
                ma, mb, s_ = mu[g["a"]], mu[g["b"]], sd
            pa_ = ma + rng.normal(size=N) * s_
            pb_ = mb + rng.normal(size=N) * s_
            wins[:, ia] += pa_ > pb_
            wins[:, ib] += pb_ > pa_
            pf[:, ia] += pa_
            pf[:, ib] += pb_
    order = np.lexsort((-pf, -wins), axis=-1) if False else np.argsort(-(wins * 1e6 + pf), axis=1)
    in_playoffs = np.zeros(len(Y.TEAM_IDS))
    seed1 = np.zeros(len(Y.TEAM_IDS))
    for k in range(PLAYOFF_SPOTS):
        np.add.at(in_playoffs, order[:, k], 1)
    np.add.at(seed1, order[:, 0], 1)
    for r in season_rows:
        i = idx[r["team_id"]]
        r["playoff_odds"] = round(float(in_playoffs[i] / N), 4)
        r["first_seed"] = round(float(seed1[i] / N), 4)
        r["proj_wins"] = round(float(wins[:, i].mean()), 1)
    season_rows.sort(key=lambda r: -r["allplay_pct"])

    rankings = [{"rank": i + 1, "team_id": int(r.id), "team": names.get(int(r.id), r.team),
                 "proj_week": round(float(r.proj_week), 1), "win_pct": round(float(r.win_pct), 4)}
                for i, r in enumerate(rank_df.itertuples())]

    # ---------- moves, roster, lineup ----------
    base_ids = [p for p in L.roster(Y.ME) if pl.at[p, "status"] not in OUT_STATUS]
    base_plan = [list(base_ids)] * len(days)

    def apply(pln, add, drop, d):
        return [r if i < d else [q for q in r if q != drop] + [add] for i, r in enumerate(pln)]

    def detail(res, wk_res):
        """Per move: lineup games added (skaters / goalie starts) and points added this week."""
        if not res:
            return None
        cur = base_plan
        g0 = L.lineup_games(cur, days, pm)
        p0 = float(L.points(cur, days, pm, 400).mean())
        prev_g, prev_p, rows = g0, p0, []
        for p, dd, x, g, wk in res["steps"]:
            cur = apply(cur, p, x, dd)
            gm = L.lineup_games(cur, days, pm)
            pt = float(L.points(cur, days, pm, 400).mean())
            rows.append({"day": days[dd], "add": player(p), "drop": player(x), "week_pts": round(pt - prev_p, 1),
                         "games_added": round(gm["total"] - prev_g["total"], 1),
                         "skater_games": round(gm["skaters"] - prev_g["skaters"], 1),
                         "goalie_starts": round(gm["goalies"] - prev_g["goalies"], 1),
                         "total": round(g, 1)})
            prev_g, prev_p = gm, pt
        final = cur[-1] + [q for q in L.roster(Y.ME) if pl.at[q, "status"] in OUT_STATUS]
        return {"steps": rows, "ros_after": round(L.ros_week(final), 1),
                "games": {"before": round(g0["total"], 1), "after": round(prev_g["total"], 1),
                          "goalies_before": round(g0["goalies"], 1), "goalies_after": round(prev_g["goalies"], 1)},
                "points": {"before": round(p0 + live[Y.ME], 1), "after": round(prev_p + live[Y.ME], 1)},
                "p_win": round(float(wk_res["p_win"]), 4) if wk_res else None}

    plans = {"week": detail(gplan, w2)}
    steps = plans["week"]["steps"] if plans["week"] else []
    singles = []
    if plan:
        for g, p, dd, x, wk in plan["singles"][:30]:
            singles.append({**player(p), "exp_fp": round(float(pl.at[p, "exp_fp"]), 2), "day": days[dd],
                            "drop": player(x), "week_pts": round(wk, 1), "total": round(g, 1),
                            "games": games_from(p, dd), "games_added": games_from(p, dd) - games_from(x, dd),
                            "avail": str(L.fa_status.get(pl.at[p, "key"], "FA"))})
    my_pts = {r["name"]: r for r in player_pts[Y.ME]}
    roster = []
    for p in L.roster(Y.ME):
        r = pl.loc[p]
        roster.append({**player(p), "slot": str(r.slot), "exp_fp": round(float(r.exp_fp), 2),
                       "p_play": round(float(r.p_play), 2), "keep_value": round(float(V.get(p, 0.0)), 1),
                       "rotatable": bool(V.get(p, 0.0) <= 0.5 and r.status not in OUT_STATUS),
                       "games_left": games_from(p, 0), "goalie": r.grp == "G",
                       "week_pts": my_pts.get(str(r["name"]), {}).get("pts", 0.0)})
    roster.sort(key=lambda r: -r["exp_fp"])
    lineup = L.lineup_today()
    for k in ("starters", "bench"):
        for e in lineup[k]:
            e.update(player(e["id"]))
    lineup["no_game"] = [player(p) for p in lineup["no_game"]]
    lineup["started"] = [player(p) for p in lineup.get("started", [])]

    out = {
        "league": "hockey", "scoring": "points",
        "team": names.get(Y.ME, "Me"), "opponent": names.get(opp, str(opp)), "my_team_id": Y.ME, "opp_id": opp,
        "week": {"number": week_no, "start": wk_start.isoformat(), "end": wk_end.isoformat(), "sim_from": today.isoformat()},
        "adds_used": adds_used, "adds_left": adds_left,
        "live": {"me": live[Y.ME], "opp": live[opp],
                 "yahoo_proj_me": cur_games.get((min(Y.ME, opp), max(Y.ME, opp)), {}).get("proj_a" if Y.ME < opp else "proj_b"),
                 "yahoo_proj_opp": cur_games.get((min(Y.ME, opp), max(Y.ME, opp)), {}).get("proj_b" if Y.ME < opp else "proj_a")},
        "projected": {"me": round(w0["me"], 1) if w0 else live[Y.ME], "opp": round(w0["opp"], 1) if w0 else live[opp]},
        "p_win": round(float(w0["p_win"]), 4) if w0 else float(live[Y.ME] > live[opp]),
        "with_plan": {"p_win": round(float(w2["p_win"]), 4) if w2 else None, "me": round(w2["me"], 1) if w2 else None},
        "ros": {"before": round(L.ros_week([p for p in L.roster(Y.ME)]), 1),
                "after": round(L.ros_week(plan["plan"][-1] + [p for p in L.roster(Y.ME) if pl.at[p, "status"] in OUT_STATUS]), 1)
                if plan and plan["steps"] else None},
        "by_stat": {"me": team_stats[Y.ME], "opp": team_stats[opp]},
        "player_pts": {"me": player_pts[Y.ME], "opp": player_pts[opp]},
        "lineup_today": lineup,
        "plan": steps, "plans": plans, "free_agents": singles, "roster": roster,
        "replacement": {k: round(float(v), 2) for k, v in plan["repl"].items()} if plan else {},
        "this_week_vs": {"rows": vs, "me_by_stat": team_stats[Y.ME], "me_pts": live[Y.ME]},
        "rankings": rankings, "season": season_rows, "weekly_sd": round(float(sd), 1),
        "status": {"yahoo": "ok", "scraped_at": datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="minutes"),
                   "live_today": len(L.skip_today)},
    }
    (OUT / "hockey.json").write_text(json.dumps(out, ensure_ascii=False, default=float))
    log(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()

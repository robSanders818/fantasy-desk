"""Shared in-season setup: Engine with per-game rates updated from 2026-27 stats.

    e, s = setup(stats_path, recency=2, actual_only=False, through="2026-10-25")
Blend weight on a player's 2026-27 averages, by games played (GP):
    recency r (default): w = r*GP / (r*GP + (82 - GP)) -- the preseason projection stands in for
        the games not yet played, played games count r times (recency bias). 3 GP, r=2 -> 7%.
    k (if given):        w = GP / (GP + k)             -- preseason counts as k games.
e.pg holds the updated per-game rates; s is the scraped roster table (team_id, player_id, slot, status...).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import draft_engine
from draft_engine import Engine, COUNT
from lineups import eligible, ESPN_TO_YAHOO


def num(x):
    try: return float(x)
    except ValueError: return np.nan


# Prior per-game rates before 2026-27 games. "ly": last season leads, 2024-25 behind it; Yahoo's
# 2026-27 projection only fills in for players with no NBA history (rookies). Games-played
# (availability) keeps model.py's projection/history blend either way.
PRIORS = {
    "ly": {"ly": 0.80, "py": 0.20, "proj": 0.001},
    "draft": dict(draft_engine.WEIGHTS),   # draft model: projection 50 / last season 35 / 2024-25 15
}


def make_engine(prior="ly"):
    draft_engine.WEIGHTS = PRIORS[prior]
    return Engine()


def setup(stats, k=None, actual_only=False, through="2026-10-25", e=None, recency=2.0, prior="ly"):
    e = e or make_engine(prior)
    df, sim = e.df, e.sim
    # ---------- current rosters + 2026-27 stats ----------
    s = pd.read_csv(stats, sep="|", dtype=str).fillna("")
    s["player_id"] = s.player_id.astype(int); s["team_id"] = s.team_id.astype(int)

    act = pd.DataFrame(index=s.player_id)
    act["GP"] = [num(x) if x != "-" else 0.0 for x in s.GP]
    act = act.fillna(0.0)
    for col, (m, a) in {"FGMA": ("FGM", "FGA"), "FTMA": ("FTM", "FTA")}.items():
        sp = s[col].str.split("/", expand=True)
        act[m] = sp[0].map(num).to_numpy(); act[a] = sp[1].map(num).to_numpy()
    for c in ["3PTM", "PTS", "REB", "AST", "ST", "BLK", "TO"]:
        act[c] = s[c].map(num).to_numpy()
    act = act.fillna(0.0)

    # Players with no preseason projection: waiver-level prior.
    ranked = df.sort_values("std_value", ascending=False).index
    repl_pg = e.pg.loc[ranked[170:190]].mean()
    for r in s.itertuples():
        nba, pos = (r.team_pos.split(" - ") + [""])[:2]
        if r.player_id not in df.index:
            row = {c: np.nan for c in df.columns}
            row.update(player_id=r.player_id, name=r.name, nba_team=nba, positions=pos, pg_GP=60,
                       games_missed=0.0, z_zsum=df.loc[ranked[180], "z_zsum"])
            df.loc[r.player_id] = row
            e.pg.loc[r.player_id] = repl_pg
            sim.elig[r.player_id] = eligible(pos)
            sim.prio[r.player_id] = row["z_zsum"]
            sim.p_active[r.player_id] = 60 / 82
        df.at[r.player_id, "nba_team"] = nba
        df.at[r.player_id, "status"] = r.status
    e.il_credit = pd.DataFrame(np.outer(e._il_share(), e.repl), index=df.index, columns=COUNT)
    for pid in df.index:   # refresh activity rates for any team changes
        sim.p_active[pid] = min(1.0, df.at[pid, "pg_GP"] / max(sim.team_games.get(df.at[pid, "nba_team"], 82), 1))
    sim._cache.clear()

    prior = e.pg.copy()
    gp = act["GP"].reindex(prior.index).fillna(0.0)
    a = act[COUNT].reindex(prior.index).fillna(0.0)
    if k is not None:
        w = (gp / (gp + k)).to_numpy()[:, None]
    else:
        w = (recency * gp / (recency * gp + (82 - gp).clip(lower=0))).fillna(0).to_numpy()[:, None]
    e.pg = prior * (1 - w) + a * w
    if actual_only:
        e.pg = a.copy()
        # Availability from this season: share of the team's games so far that the player played.
        sched = pd.read_csv("data/league/nba_schedule_2026.csv")
        sched = sched[sched.date <= through]
        tg = pd.concat([sched.home, sched.away]).replace(ESPN_TO_YAHOO).value_counts()
        rostered = set(s.player_id)
        for pid in df.index:
            played = gp.get(pid, 0.0)
            sim.p_active[pid] = min(1.0, played / max(tg.get(df.at[pid, "nba_team"], 1), 1)) if pid in rostered else 0.0
        # No injury fill-in credit: an absent player just contributes nothing.
        e.il_credit[:] = 0.0
    set_priority(e)
    return e, s


def set_priority(e):
    """Lineup priority: re-rank by the updated rates (z-score sum over the 9 cats, roughly)."""
    upd = e.pg
    z = sum(((upd[c] - upd[c].mean()) / upd[c].std()) for c in ["3PTM", "PTS", "REB", "AST", "ST", "BLK"]) \
        - (upd["TO"] - upd["TO"].mean()) / upd["TO"].std()
    e.sim.prio = z.to_dict()
    e.sim._cache.clear()

"""Player projections for What the Puck (Yahoo 41313): expected fantasy points per scheduled team game.

Skaters
  history  each stat per game = 70% last season + 30% the season before (GP-weighted), shrunk
           toward the position (F/D) mean with its own K (games of league-average weight, fitted
           in backtest.py: +/- and SHA are mostly noise, shots/PIM/PPP/faceoffs carry over),
           then scored with the league weights.
  current  2026-27 per-game stats blended in at 2x recency: w = 2*GP / (2*GP + games left).
  play     chance he dresses for a team game: (GP last season + GP this season + 20*0.9) /
           (82 + team games this season + 20); IR -> 0 this week.
  yahoo    Yahoo rest-of-season projection / team games left, with the faceoff-loss fix
           (Yahoo projects ~15% as many FL as FW; we replace that with his real FO%).
  final    expected FP per team game = 50% our model + 50% Yahoo (ours alone if no Yahoo line).
Goalies
  FP per start barely carries over year to year (backtest corr ~0), so per-start FP is shrunk
  hard (K=40 starts) toward the league mean; the value is in start share:
  share = (GS this season + 10 * last-season share) / (team games this season + 10).
"""
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

from scoring import SKATER, goalie_fp, skater_fp

# Per-stat shrinkage (games of position-average weight), fitted by backtest.fit_ks().
STAT_K = {"G": 20, "A": 5, "PM": 160, "PIM": 0, "PPP": 0, "SHG": 0, "SHA": 160, "SOG": 0,
          "FW": 0, "FL": 5, "HIT": 20, "BLK": 5}

ROOT = Path(__file__).parent
NHL = ROOT / "data" / "nhl"
CUR, LY, PY = 20262027, 20252026, 20242025
SEASON_GAMES = 84
YAHOO_TEAM = {"SJ": "SJS", "NJ": "NJD", "LA": "LAK", "TB": "TBL"}
Y_WEIGHT = 0.5
OUT_STATUS = {"IR", "IR+", "IR-LT", "IR-NR", "O", "NA", "SUSP"}


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z ]", "", s.replace("-", " "))
    return re.sub(r"\s+", " ", s).strip()


def schedule(today: str) -> pd.DataFrame:
    s = pd.read_csv(NHL / "schedule.csv")
    s["played"] = s.date < today
    return s


def team_games(sched: pd.DataFrame, played: bool) -> pd.Series:
    s = sched[sched.played == played]
    return pd.concat([s.home, s.away]).value_counts()


def skaters(today: str) -> pd.DataFrame:
    sk = pd.read_csv(NHL / "skaters.csv")
    sk["FP"] = skater_fp(sk)
    sk["team"] = sk.teams.str.split(",").str[-1]
    g = {s: sk[sk.season == s].set_index("playerId") for s in (CUR, LY, PY)}
    ids = pd.Index(sorted(set(g[CUR].index) | set(g[LY].index)))
    df = pd.DataFrame(index=ids)
    for s, tag in ((CUR, "cur"), (LY, "ly"), (PY, "py")):
        df[f"{tag}_fp"] = g[s].FP.reindex(ids)
        df[f"{tag}_gp"] = g[s].GP.reindex(ids)
    last = pd.concat([g[PY], g[LY], g[CUR]])
    last = last[~last.index.duplicated(keep="last")]
    df["name"], df["pos"], df["team"] = last.name.reindex(ids), last.pos.reindex(ids), last.team.reindex(ids)
    fo = (last.FW / (last.FW + last.FL)).reindex(ids)
    df["fo_pct"] = fo.where((last.FW + last.FL).reindex(ids) > 50, 0.45)
    df["grp"] = np.where(df.pos == "D", "D", "F")

    gp = 0.7 * df.ly_gp.fillna(0) + 0.3 * df.py_gp.fillna(0)
    reg = g[LY][g[LY].GP >= 20]
    cgp = df.cur_gp.fillna(0)
    w = 2 * cgp / (2 * cgp + SEASON_GAMES - cgp)
    df["hist_fpg"] = 0.0
    df["fpg"] = 0.0
    for st, wt in SKATER.items():
        tot = 0.7 * g[LY][st].reindex(ids).fillna(0) + 0.3 * g[PY][st].reindex(ids).fillna(0)
        mean = df.grp.map({grp: reg[st][m].sum() / reg.GP[m].sum()
                           for grp, m in (("D", reg.pos == "D"), ("F", reg.pos != "D"))})
        hist = (tot + mean * STAT_K[st]) / (gp + STAT_K[st]).replace(0, np.nan)
        hist = hist.fillna(mean)
        cur = (g[CUR][st].reindex(ids) / df.cur_gp).fillna(hist)
        df[f"pg_{st}"] = hist * (1 - w) + cur * w
        df["hist_fpg"] += wt * hist
        df["fpg"] += wt * df[f"pg_{st}"]
    # this season counts too: games dressed / team games played so far
    tg = team_games(schedule(today), True)
    df["p_play"] = (df.ly_gp.fillna(0) + cgp + 20 * 0.9) / (82 + df.team.map(tg).fillna(0) * df.cur_gp.notna() + 20)
    df["key"] = df.name.map(norm)
    return df


def goalies(today: str, sched: pd.DataFrame) -> pd.DataFrame:
    go = pd.read_csv(NHL / "goalies.csv")
    go["FP"] = goalie_fp(go)
    go["team"] = go.teams.str.split(",").str[-1]
    g = {s: go[go.season == s].set_index("playerId") for s in (CUR, LY, PY)}
    ids = pd.Index(sorted(set(g[CUR].index) | set(g[LY].index)))
    df = pd.DataFrame(index=ids)
    for s, tag in ((CUR, "cur"), (LY, "ly"), (PY, "py")):
        df[f"{tag}_fp"] = g[s].FP.reindex(ids)
        df[f"{tag}_gs"] = g[s].GS.reindex(ids)
    last = pd.concat([g[PY], g[LY], g[CUR]])
    last = last[~last.index.duplicated(keep="last")]
    df["name"], df["team"] = last.name.reindex(ids), last.team.reindex(ids)
    df["pos"], df["grp"] = "G", "G"
    reg = g[LY][g[LY].GS >= 10]
    lg_mean = reg.FP.sum() / reg.GS.sum()
    fp = 0.7 * df.ly_fp.fillna(0) + 0.3 * df.py_fp.fillna(0)
    gs = 0.7 * df.ly_gs.fillna(0) + 0.3 * df.py_gs.fillna(0)
    hist = (fp + lg_mean * 40) / (gs + 40)
    cgs = df.cur_gs.fillna(0)
    w = 2 * cgs / (2 * cgs + 40)
    cur = (df.cur_fp / df.cur_gs).fillna(hist)
    df["fpg"] = hist * (1 - w) + cur * w            # FP per start
    tg = team_games(sched, True)
    ly_share = (df.ly_gs.fillna(0) / 82).clip(upper=0.85)
    df["p_play"] = (cgs + 10 * ly_share) / (df.team.map(tg).fillna(0) + 10)
    df["key"] = df.name.map(norm)
    df["fo_pct"] = np.nan
    return df


def yahoo_rosters(path: Path) -> pd.DataFrame:
    y = pd.read_csv(path, sep="|", dtype=str).fillna("")
    for c in ("team_id", "y_next7_fp", "y_ros_sog", "y_ros_fw"):
        if c not in y:
            y[c] = "0" if c == "team_id" else ""
    tp = y.team_pos.str.split(" - ", expand=True)
    y["yteam"] = tp[0].replace(YAHOO_TEAM)
    y["elig"] = tp[1]
    y["key"] = y.name.map(norm)
    y["team_id"] = y.team_id.astype(int)
    for c in ("y_ros_fp", "y_next7_fp", "y_ros_sog", "y_ros_fw"):
        y[c] = pd.to_numeric(y[c], errors="coerce")
    return y


def build(today: str, yahoo_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """All NHL players with projections; yahoo rows matched in. Returns (players, yahoo)."""
    sched = schedule(today)
    pl = pd.concat([skaters(today), goalies(today, sched)])
    pl = pl[~pl.index.duplicated(keep="first")]
    y = yahoo_rosters(yahoo_path)
    # match Yahoo rows to NHL ids by normalized name (team as tiebreak)
    ids = []
    for r in y.itertuples():
        cand = pl.index[pl.key == r.key]
        if len(cand) > 1:
            c2 = [c for c in cand if pl.at[c, "team"] == r.yteam]
            cand = c2 or cand
        ids.append(cand[0] if len(cand) else None)
    y["playerId"] = ids
    miss = y[y.playerId.isna()]
    if len(miss):
        print("unmatched Yahoo players:", ", ".join(miss.name))
    y = y.dropna(subset=["playerId"]).astype({"playerId": int})

    yy0 = y.set_index("playerId")
    pl.loc[yy0.index, "team"] = yy0.yteam          # Yahoo's NHL team is more current than ours
    left = team_games(sched, False)
    pl["games_left"] = pl.team.map(left).fillna(0)
    pl["ours"] = pl.fpg * pl.p_play                        # expected FP per team game
    yy = y.set_index("playerId")
    pl["team_id"] = yy.team_id.reindex(pl.index).fillna(0).astype(int)
    pl["slot"] = yy.slot.reindex(pl.index).fillna("")
    pl["status"] = yy.status.reindex(pl.index).fillna("")
    pl["elig"] = yy.elig.reindex(pl.index)
    pl["elig"] = pl.elig.fillna(pl.pos.map({"C": "C", "L": "LW", "R": "RW", "D": "D", "G": "G"}))
    yfp = yy.y_ros_fp.reindex(pl.index)
    # Yahoo faceoff-loss fix: their FL is ~15% of FW; real FL = FW * (1-p)/p.
    fw = yy.y_ros_fw.reindex(pl.index).fillna(0)
    p = pl.fo_pct.fillna(0.45).clip(0.3, 0.65)
    yfp = yfp - 0.1 * (fw * (1 - p) / p - 0.15 * fw)
    pl["yahoo"] = (yfp / pl.games_left.replace(0, np.nan))
    pl["y_next7"] = yy.y_next7_fp.reindex(pl.index)
    pl["exp_fp"] = np.where(pl.yahoo.notna(), (1 - Y_WEIGHT) * pl.ours + Y_WEIGHT * pl.yahoo, pl.ours)
    pl["fp_play"] = pl.exp_fp / pl.p_play.clip(lower=0.05)  # FP when he plays (a start, for goalies)
    return pl, y

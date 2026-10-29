"""What the Puck: power rankings, weekly matchup odds, and a streaming planner.

Daily lineups: each day a player whose NHL team plays (and who dresses, drawn from his play
probability; for goalies, whether he starts) is slotted greedily by expected points per game,
most specific slot first (C C LW RW D D D D G G, then W W). Only goalies who start score.
Team weekly points ~ Normal(simulated mean, SD) with SD from this season's weekly scores.

    uv run league.py rank                  # power rankings (rest-of-season weekly points, win% vs field)
    uv run league.py week --opp 9          # this week's matchup
    uv run league.py stream --opp 9        # free-agent adds for this week (5 adds max)
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import ndtr

from model import OUT_STATUS, ROOT, build, schedule, norm, team_games, yahoo_rosters

TEAMS = {1: "Team 1", 2: "Team 2", 3: "Team 3", 4: "Team 4", 6: "Team 6", 7: "Team 7", 8: "Team 8", 9: "Team 9"}
ME = 1
SLOTS = ["C", "C", "LW", "RW", "D", "D", "D", "D", "G", "G", "W", "W"]
ROSTER_SPOTS = 16   # 12 starters + 4 bench (IR extra)


def elig_mask(e: str) -> np.ndarray:
    p = set(str(e).split(","))
    return np.array([s in p or (s == "W" and bool(p & {"LW", "RW"})) for s in SLOTS])


class League:
    def __init__(self, today: str, yahoo: Path, fa: Path | None, samples: int = 2000,
                 results: pd.DataFrame | None = None, teams: dict | None = None):
        self.today, self.S = today, samples
        if teams:
            TEAMS.clear()
            TEAMS.update(teams)
        self.skip_today: set[int] = set()     # NHL ids whose game today already started (counted live)
        self.pl, self.y = build(today, yahoo)
        self.sched = schedule(today)
        self.fa_status = {}
        if fa and fa.exists():
            f = yahoo_rosters(fa)
            self.fa_status = dict(zip(f.key, f.slot))           # "FA" or "W (Oct 28)"
            f = f[~f.key.isin(self.pl.key[self.pl.team_id > 0])].set_index("key")
            pl = self.pl
            m = (pl.team_id == 0) & pl.key.isin(f.index)
            k = pl.loc[m, "key"]
            pl.loc[m, "team"] = k.map(f.yteam)
            pl.loc[m, "elig"] = k.map(f.elig)
            pl.loc[m, "status"] = k.map(f.status)
            p_fo = pl.loc[m, "fo_pct"].fillna(0.45).clip(0.3, 0.65)
            fw = k.map(f.y_ros_fw).fillna(0)
            yfp = k.map(f.y_ros_fp) - 0.1 * (fw * (1 - p_fo) / p_fo - 0.15 * fw)
            pl.loc[m, "yahoo"] = yfp / pl.loc[m, "team"].map(team_games(self.sched, False)).replace(0, np.nan)
            pl.loc[m, "exp_fp"] = 0.5 * pl.loc[m, "ours"] + 0.5 * pl.loc[m, "yahoo"].fillna(pl.loc[m, "ours"])
            pl.loc[m, "fp_play"] = pl.loc[m, "exp_fp"] / pl.loc[m, "p_play"].clip(lower=0.05)
            # NHL players Yahoo doesn't list in the top free agents: keep our projection only
        self.mask = {p: elig_mask(e) for p, e in self.pl.elig.items()}
        res = results if results is not None else pd.read_csv(ROOT / "data" / "yahoo" / "results.csv")
        long = pd.concat([res.rename(columns={"team_a": "t", "pts_a": "p"})[["week", "t", "p"]],
                          res.rename(columns={"team_b": "t", "pts_b": "p"})[["week", "t", "p"]]])
        resid = long.p - long.groupby("t").p.transform("mean")
        n = long.groupby("t").p.transform("size")
        self.sd = float(np.sqrt((resid ** 2 * n / (n - 1)).mean()))
        self.results = long
        self.games = res

    def roster(self, team: int) -> list[int]:
        return self.pl.index[(self.pl.team_id == team)].tolist()

    # ---------- lineup simulation ----------
    def plays(self, start: str, end: str):
        s = self.sched[(self.sched.date >= start) & (self.sched.date <= end)]
        days = sorted(s.date.unique())
        pm = {}
        for r in s.itertuples():
            for t in (r.home, r.away):
                pm.setdefault(t, np.zeros(len(days), bool))[days.index(r.date)] = True
        return days, pm

    def active(self, p, days, pm, S, out_ok=False):
        st = self.pl.at[p, "status"]
        if st in OUT_STATUS and not out_ok:
            return np.zeros((S, len(days)), bool)
        u = np.random.default_rng(int(p) % (2**32)).random((S, len(days)))
        team_days = pm.get(self.pl.at[p, "team"], np.zeros(len(days), bool))
        a = team_days[None, :] & (u < self.pl.at[p, "p_play"])
        if p in self.skip_today and days and days[0] == self.today:
            a[:, 0] = False                    # already playing / played today: in the live score
        return a

    def points(self, rosters_by_day, days, pm, S, out_ok=False, detail=False):
        """rosters_by_day: list of player-id lists (one per day). Returns (S,) weekly points."""
        tot = np.zeros(S)
        starts = {}
        cache = {}
        for d, ros in enumerate(rosters_by_day):
            free = np.ones((S, len(SLOTS)), bool)
            for p in sorted(ros, key=lambda p: -self.pl.at[p, "fp_play"]):
                if p not in cache:
                    cache[p] = self.active(p, days, pm, S, out_ok)
                a = cache[p][:, d]
                if not a.any():
                    continue
                placed = np.zeros(S, bool)
                for i in np.where(self.mask[p])[0]:
                    can = a & ~placed & free[:, i]
                    free[can, i] = False
                    placed |= can
                tot += placed * self.pl.at[p, "fp_play"]
                if detail:
                    starts[p] = starts.get(p, 0) + placed.mean()
        return (tot, starts) if detail else tot

    # ---------- outputs ----------
    def rank(self):
        """Rest-of-season average weekly points per team, then win% vs each other team."""
        end = self.sched.date.max()
        days, pm = self.plays(self.today, end)
        weeks = len(days) / 7
        mu = {}
        for t in TEAMS:
            ros = self.roster(t)
            mu[t] = self.points([ros] * len(days), days, pm, 60, out_ok=True).mean() / weeks
        rows = []
        for t in TEAMS:
            p = [ndtr((mu[t] - mu[o]) / (self.sd * np.sqrt(2))) for o in TEAMS if o != t]
            r = self.results[self.results.t == t]
            g = self.games[(self.games.team_a == t) | (self.games.team_b == t)]
            mine_ = np.where(g.team_a == t, g.pts_a, g.pts_b)
            theirs = np.where(g.team_a == t, g.pts_b, g.pts_a)
            w = int((mine_ > theirs).sum())
            rows.append({"team": TEAMS[t], "id": t, "record": f"{w}-{len(g) - w}", "PF": r.p.sum(),
                         "avg": r.p.mean(), "proj_week": mu[t], "win_pct": np.mean(p)})
        return pd.DataFrame(rows).sort_values("proj_week", ascending=False), self.sd

    def week(self, opp, start, end, me=ME, plan=None, banked=(0.0, 0.0)):
        """Rest of the week from `start`, on top of points already banked (live score)."""
        days, pm = self.plays(start, end)
        mine = plan or [self.roster(me)] * len(days)
        a, st = self.points(mine, days, pm, self.S, detail=True)
        b = self.points([self.roster(opp)] * len(days), days, pm, self.S)
        rng = np.random.default_rng(3)
        noise = rng.normal(size=(self.S, 2)) * self.sd * np.sqrt(max(len(days), 0.5) / 7)
        a, b = a + banked[0], b + banked[1]
        win = (a + noise[:, 0]) > (b + noise[:, 1])
        return {"me": a.mean(), "opp": b.mean(), "p_win": win.mean(), "starts": st, "days": days}

    def lineup_today(self, me=ME):
        """Best lineup for today's games by expected points (skaters who play; goalies weighted by
        their chance to start). Players whose game has started are left where they are."""
        pl = self.pl
        days, pm = self.plays(self.today, self.today)
        if not days:
            return {"starters": [], "bench": [], "no_game": []}
        plays = lambda p: bool(pm.get(pl.at[p, "team"], np.zeros(1, bool))[0])
        ros = [p for p in self.roster(me) if pl.at[p, "status"] not in OUT_STATUS]
        live = [p for p in ros if plays(p) and p not in self.skip_today]
        # value today = points if he plays x chance he plays (start chance for goalies)
        val = {p: pl.at[p, "fp_play"] * pl.at[p, "p_play"] for p in live}
        free = list(range(len(SLOTS)))
        starters, bench = [], []
        for p in sorted(live, key=lambda p: -val[p]):
            slot = next((i for i in free if self.mask[p][i]), None)
            if slot is None:
                bench.append({"id": int(p), "exp": round(val[p], 2), "why": "no open slot"})
                continue
            free.remove(slot)
            starters.append({"id": int(p), "slot": SLOTS[slot], "exp": round(val[p], 2),
                             "p_play": round(float(pl.at[p, "p_play"]), 2)})
        order = {s: i for i, s in enumerate(["C", "LW", "RW", "W", "D", "G"])}
        starters.sort(key=lambda r: order.get(r["slot"], 9))
        return {"starters": starters, "bench": bench,
                "no_game": [int(p) for p in ros if not plays(p)], "started": [int(p) for p in ros if p in self.skip_today],
                "open_slots": [SLOTS[i] for i in free]}

    # ---------- streaming ----------
    def ros_week(self, roster, S=60):
        days, pm = self.plays(self.today, self.sched.date.max())
        return self.points([roster] * len(days), days, pm, S, out_ok=True).mean() / (len(days) / 7)

    def keep_value(self, end, repl_rank=10):
        """Rest-of-season points a player is worth above replacement (the repl_rank-th best
        available free agent at his position group: skater or goalie), counted from after `end`.
        Dropping someone above replacement loses this (another team will pick him up)."""
        pl = self.pl
        avail = pl[(pl.team_id == 0) & ~pl.status.isin(OUT_STATUS)]
        # replacement by position group; D and G pools are thinner, so a shallower rank
        ranks = {"F": repl_rank, "D": max(repl_rank // 2, 1), "G": max(repl_rank // 3, 1)}
        repl = {g: avail[avail.grp == g].exp_fp.nlargest(k).iloc[-1] for g, k in ranks.items()}
        rest = self.sched[self.sched.date > end]
        left = pd.concat([rest.home, rest.away]).value_counts()
        r = pl.grp.map(repl).to_numpy()
        return pd.Series(np.maximum(pl.exp_fp - r, 0) * pl.team.map(left).fillna(0), index=pl.index), repl

    def stream(self, opp, start, end, first_add, adds=5, pool=10, protect=(), S=500, cands=45, repl_rank=10):
        days, pm = self.plays(start, end)
        D = len(days)
        f0 = days.index(first_add)
        pl = self.pl
        mine = self.roster(ME)
        active_mine = [p for p in mine if pl.at[p, "status"] not in OUT_STATUS]
        base_plan = [list(active_mine)] * D
        opp_pts = self.points([self.roster(opp)] * D, days, pm, S).mean()

        def ev(plan):
            return self.points(plan, days, pm, S).mean()

        games_after = {t: v[f0:].sum() for t, v in pm.items()}
        fa = pl[(pl.team_id == 0) & ~pl.status.isin(OUT_STATUS)].copy()
        fa = fa[~fa.key.map(lambda k: str(self.fa_status.get(k, "FA")).startswith("W"))]
        fa["wk"] = fa.exp_fp * fa.team.map(games_after).fillna(0)
        sk_c = fa[fa.grp != "G"].nlargest(cands, "wk").index.tolist()
        g_c = fa[fa.grp == "G"].nlargest(12, "wk").index.tolist()
        cand = sk_c + g_c
        drops = sorted([p for p in active_mine if pl.at[p, "name"] not in protect],
                       key=lambda p: pl.at[p, "exp_fp"])[:pool]
        V, repl = self.keep_value(end, repl_rank)
        ir = [p for p in mine if pl.at[p, "status"] in OUT_STATUS]
        rest = self.sched[self.sched.date > end].date.nunique()
        W = rest / 7                                       # weeks left after this one
        ros_cache = {}

        def ros(final):
            k = tuple(sorted(final))
            if k not in ros_cache:
                ros_cache[k] = self.ros_week(list(final) + ir, S=40)
            return ros_cache[k]

        def apply(plan, add, drop, d):
            return [r if i < d else [q for q in r if q != drop] + [add] for i, r in enumerate(plan)]

        def best(plan, droppable, taken):
            cur = ev(plan)
            cur_ros = ros(plan[-1])
            out = []
            for p in cand:
                if p in taken:
                    continue
                tg = pm.get(pl.at[p, "team"], np.zeros(D, bool))
                b = None
                for d in range(f0, D):
                    if not tg[d:].any():
                        break
                    if not tg[d]:
                        continue                       # add on a day he plays
                    for x, xf in droppable:
                        if xf > d or not all(x in plan[i] for i in range(d, D)):
                            continue
                        new = apply(plan, p, x, d)
                        wk = ev(new) - cur
                        # rest of season: the swap's effect on your weekly lineup points, over the
                        # weeks left (a good player dropped is gone -- another team takes him)
                        v = wk + (ros(new[-1]) - cur_ros) * W
                        if b is None or v > b[0]:
                            b = (v, d, x, wk)
                if b:
                    out.append((b[0], p, b[1], b[2], b[3]))
            return sorted(out, key=lambda r: -r[0])

        singles = best(base_plan, [(x, 0) for x in drops], set(mine))
        plan, taken, droppable, steps = base_plan, set(mine), [(x, 0) for x in drops], []
        for _ in range(adds):
            mv = best(plan, droppable, taken)
            if not mv or mv[0][0] < 1.0:
                break
            g, p, d, x, wk = mv[0]
            plan = apply(plan, p, x, d)
            taken.add(p)
            droppable = [(q, f) for q, f in droppable if q != x] + [(p, d + 1)]
            steps.append((p, d, x, g, wk))
        return {"days": days, "base": ev(base_plan), "opp": opp_pts, "final": ev(plan), "plan": plan,
                "steps": steps, "singles": singles, "drops": drops, "V": V, "repl": repl}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["rank", "week", "stream"])
    ap.add_argument("--today", default="2026-10-26")
    ap.add_argument("--yahoo", default="data/yahoo/rosters_2026-10-26.psv")
    ap.add_argument("--fa", default="data/yahoo/fa_2026-10-26.psv")
    ap.add_argument("--opp", type=int, default=9)
    ap.add_argument("--start", default="2026-10-26")
    ap.add_argument("--end", default="2026-11-01")
    ap.add_argument("--first-add", default="2026-10-27", help="first day an added player can play")
    ap.add_argument("--adds", type=int, default=5)
    ap.add_argument("--protect", nargs="*", default=[])
    ap.add_argument("--repl-rank", type=int, default=10, help="replacement = Nth best available free agent")
    a = ap.parse_args()
    L = League(a.today, ROOT / a.yahoo, ROOT / a.fa)
    name = lambda p: L.pl.at[p, "name"]
    if a.cmd == "rank":
        df, sd = L.rank()
        print(f"Rest-of-season projection (weekly SD {sd:.0f} pts)\n")
        print(f"{'#':>2} {'team':<29}{'rec':<6}{'PF':>8}{'avg':>7}{'proj/wk':>9}{'win%':>7}")
        for i, r in enumerate(df.itertuples(), 1):
            print(f"{i:2} {r.team:<29}{r.record:<6}{r.PF:8.1f}{r.avg:7.1f}{r.proj_week:9.1f}{r.win_pct*100:6.0f}%")
    elif a.cmd == "week":
        w = L.week(a.opp, a.start, a.end)
        print(f"{TEAMS[ME]} vs {TEAMS[a.opp]}, {a.start}..{a.end}")
        print(f"projected {w['me']:.1f} - {w['opp']:.1f}   P(win) {w['p_win']*100:.1f}%")
        print("your expected starts: " + ", ".join(f"{name(p)} {v:.1f}" for p, v in sorted(w['starts'].items(), key=lambda x: -x[1])))
    else:
        r = L.stream(a.opp, a.start, a.end, a.first_add, a.adds, protect=a.protect, repl_rank=a.repl_rank)
        days = r["days"]
        print(f"{TEAMS[ME]} vs {TEAMS[a.opp]}: current roster {r['base']:.1f} vs {r['opp']:.1f} projected")
        V = r["V"]
        print("replacement level (exp FP per team game): " + ", ".join(f"{g} {v:.2f}" for g, v in r["repl"].items()))
        print("drop cost (rest-of-season pts above replacement): " + ", ".join(f"{name(p)} {V[p]:.0f}" for p in sorted(L.roster(ME), key=lambda p: V[p])))
        print(f"\nBest single moves (total = this week's gain + change in your rest-of-season points):")
        print(f"  {'add':<24}{'tm':<5}{'pos':<10}{'exp/g':>6} {'total':>7} {'week':>6}  day / drop")
        for g, p, d, x, wk in r["singles"][:20]:
            pp = L.pl.loc[p]
            print(f"  {pp['name']:<24}{pp.team:<5}{pp.elig:<10}{pp.exp_fp:6.2f} {g:+7.1f} {wk:+6.1f}  {days[d][5:]} / {name(x)}")
        print(f"\nPlan ({len(r['steps'])} adds):")
        for p, d, x, g, wk in r["steps"]:
            print(f"  {days[d][5:]}: add {name(p)} ({L.pl.at[p,'team']}, {L.pl.at[p,'elig']}), drop {name(x)}   week {wk:+.1f}, total {g:+.1f}")
        mine = L.roster(ME)
        w0, w1 = L.week(a.opp, a.start, a.end), L.week(a.opp, a.start, a.end, plan=r["plan"])
        print(f"\nthis week {r['base']:.1f} -> {r['final']:.1f} (opp {r['opp']:.1f});  P(win) {w0['p_win']*100:.0f}% -> {w1['p_win']*100:.0f}%")
        after = r["plan"][-1] + [p for p in mine if L.pl.at[p, "status"] in OUT_STATUS]
        print(f"rest-of-season weekly pts: {L.ros_week(mine):.1f} -> {L.ros_week(after):.1f}")


if __name__ == "__main__":
    main()

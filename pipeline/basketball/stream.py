"""Weekly streaming planner: which free agents to add, on which day, dropping whom.

For the week's real NBA schedule, simulates daily 13-slot lineups for you and your opponent
(same machinery as week_h2h.py) and scores expected categories won / P(win week).
  1. Rest-of-season value of each of your players (avg weekly win% vs the field, from
     season.py) -> the least valuable ones are the drop pool.
  2. Every free agent: best single move (add day x drop) and its gain this week.
  3. Greedy plan for the week's adds (default 3): each step picks the move with the biggest
     gain in expected categories won; a streamer added earlier can be dropped again later.

Adds take effect the day after they're made (--first-add sets the earliest playing day).
Waiver players (W <date>) are only allowed from the day after their waiver clears.

    uv run scratch/stream.py --opp 3 --start 2026-10-26 --end 2026-11-01 --first-add 2026-10-27
"""
import argparse, sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from season import setup, set_priority, num
from draft_engine import COUNT
from lineups import ESPN_TO_YAHOO, SLOTS, SLOT_ORDER, eligible
from model import CATS, MY_TEAM

ap = argparse.ArgumentParser()
ap.add_argument("--opp", type=int, required=True)
ap.add_argument("--me", type=int, default=MY_TEAM)
ap.add_argument("--start", default="2026-10-26")
ap.add_argument("--end", default="2026-11-01")
ap.add_argument("--first-add", default="2026-10-27", help="first day an added player can play")
ap.add_argument("--adds", type=int, default=3)
ap.add_argument("--stats", default="data/season/stats_2026-10-26.psv")
ap.add_argument("--fa", default="data/season/fa_2026-10-26.psv")
ap.add_argument("--recency", type=float, default=2.0)
ap.add_argument("--drop-pool", type=int, default=5, help="your N lowest rest-of-season players may be dropped")
ap.add_argument("--role-k", type=float, default=5, help="games of 'no role change' in the role adjustment")
ap.add_argument("--protect", nargs="*", default=[], help="never drop these (names)")
ap.add_argument("--plan", nargs="*", help='evaluate your own moves instead: "Add Name>Drop Name@MM-DD" ...')
ap.add_argument("--banked", nargs=2, metavar=("ME", "OPP"),
                help="week-to-date totals 'FGM/FGA,FTM/FTA,3PTM,PTS,REB,AST,ST,BLK,TO' for you and the opponent; simulate only --start..--end")
ap.add_argument("--out-days", nargs="*", default=[], help='"Name=YYYY-MM-DD,..." out only on those days (overrides an O status)')
ap.add_argument("--il", nargs="*", default=[], help="move these to an IL slot (frees a roster spot each)")
ap.add_argument("--roster-size", type=int, default=17, help="active (non-IL) roster spots")
ap.add_argument("--objective", default="win", choices=["win", "cats"], help="maximise P(win week) or expected cats")
ap.add_argument("--json", help="also write the results here (for the fantasy-desk page)")
ap.add_argument("--samples", type=int, default=3000)
args = ap.parse_args()
S = args.samples

e, s = setup(args.stats, recency=args.recency)
df, sim = e.df, e.sim
OUT = {"O", "IL", "INJ", "OFS", "SUSP", "NA"}

# ---------- free agents: prior = model rates (or last season), blended with 2026-27 ----------
fa = pd.read_csv(args.fa, sep="|", dtype=str).fillna("")
fa["player_id"] = fa.player_id.astype(int)
ranked = df.sort_values("std_value", ascending=False).index
repl_pg = e.pg.loc[ranked[170:190]].mean()


def line(x):
    """'GP,FGM/FGA,FTM/FTA,3PTM,PTS,REB,AST,ST,BLK,TO' -> (GP, Series of COUNT per game)."""
    if not x:
        return 0.0, None
    f = x.split(",")
    gp = num(f[0]) or 0.0
    fgm, fga = (num(v) for v in f[1].split("/")); ftm, fta = (num(v) for v in f[2].split("/"))
    v = [fgm, fga, ftm, fta] + [num(v) for v in f[3:10]]
    return gp, pd.Series(np.nan_to_num(v), index=COUNT)


sched = pd.read_csv("data/league/nba_schedule_2026.csv")
for c in ("home", "away"):
    sched[c] = sched[c].replace(ESPN_TO_YAHOO)
played = sched[sched.date < args.start]
team_g = pd.concat([played.home, played.away]).value_counts()

def role(prior, cur, gp):
    """Scale a prior by this season's role: ratio of current to prior PTS+REB+AST per game,
    shrunk toward 1 with ROLE_K games of weight on 'no change'."""
    if cur is None or gp == 0:
        return prior
    a, b = cur[["PTS", "REB", "AST"]].sum(), prior[["PTS", "REB", "AST"]].sum()
    if b <= 0:
        return prior
    r = (gp * min(a / b, 2.0) + args.role_k) / (gp + args.role_k)
    return prior * r


# Rostered players: same role adjustment on the part of their rate that came from the prior.
sp = pd.read_csv(args.stats, sep="|", dtype=str).fillna("")
for r in sp.itertuples():
    gp, cur = line(",".join([r.GP if r.GP != "-" else "0", r.FGMA, r.FTMA, r[11], r.PTS, r.REB, r.AST, r.ST, r.BLK, r.TO]))
    pid = int(r.player_id)
    if cur is None or gp == 0 or pid not in e.pg.index:
        continue
    w = args.recency * gp / (args.recency * gp + max(82 - gp, 0))
    prior = (e.pg.loc[pid] - w * cur) / (1 - w)
    e.pg.loc[pid] = (role(prior, cur, gp) * (1 - w) + cur * w).to_numpy()

fa_ids = []
df["fa_from"] = None
for r in fa.itertuples():
    nba, pos = (r.team_pos.split(" - ") + [""])[:2]
    gp, cur = line(r.cur)
    lgp, ly = line(r.ly)
    pid = r.player_id
    if pid in df.index and df.at[pid, "pg_PTS"] == df.at[pid, "pg_PTS"]:
        prior, p_prior = e.pg.loc[pid], sim.p_active.get(pid, 0.75)
    elif ly is not None and lgp > 0:
        prior, p_prior = ly, min(1.0, lgp / 82)
    else:
        prior, p_prior = repl_pg, 0.6
    w = args.recency * gp / (args.recency * gp + max(82 - gp, 0))
    rate = role(prior, cur, gp) * (1 - w) + (cur if cur is not None else prior) * w
    if pid not in df.index:
        df.loc[pid] = {c: np.nan for c in df.columns} | {"player_id": pid, "name": r.name}
    df.at[pid, "nba_team"], df.at[pid, "positions"], df.at[pid, "status"] = nba, pos, r.status
    df.at[pid, "name"] = r.name
    e.pg.loc[pid] = rate.to_numpy()
    sim.elig[pid] = eligible(pos)
    # Availability: prior durability, nudged by this season's share of team games.
    cur_share = gp / max(team_g.get(nba, 1), 1)
    sim.p_active[pid] = min(1.0, 0.7 * p_prior + 0.3 * cur_share)
    avail = r.avail
    df.at[pid, "fa_from"] = None if avail == "FA" else pd.Timestamp(f"{avail[1:]} 2026").strftime("%Y-%m-%d")
    fa_ids.append(pid)
set_priority(e)
e.il_credit = e.il_credit.reindex(df.index, fill_value=0.0)   # free agents new to the table

# ---------- week schedule + common random numbers ----------
wk = sched[(sched.date >= args.start) & (sched.date <= args.end)]
days = sorted(wk.date.unique())
D = len(days)
plays = {}
for r in wk.itertuples():
    for t in (r.home, r.away):
        plays.setdefault(t, np.zeros(D, bool))[days.index(r.date)] = True
status = dict(zip(s.player_id, s.status)) | dict(zip(fa.player_id, fa.status))
by_name_all = {df.at[p, "name"]: p for p in set(s.player_id) | set(fa.player_id)}
out_days = {}
for spec in args.out_days:
    nm, ds = spec.split("=")
    pid = by_name_all[nm.strip()]
    out_days[pid] = [days.index(x) for x in ds.split(",") if x in days]
    status[pid] = ""                     # healthy apart from those days
_act = {}


def active(p):
    if p not in _act:
        if status.get(p, "") in OUT:
            _act[p] = np.zeros((S, D), bool)
        else:
            u = np.random.default_rng(p).random((S, D))
            _act[p] = plays.get(df.at[p, "nba_team"], np.zeros(D, bool))[None, :] & (u < sim.p_active.get(p, 0.7))
            for d in out_days.get(p, []):
                _act[p][:, d] = False
    return _act[p]


PG = {}
def pg(p):
    if p not in PG:
        PG[p] = e.pg.loc[p].to_numpy()
    return PG[p]


def week(rosters):
    """rosters: list (per day) of player ids -> (S, 11) totals, starts per player."""
    tot = np.zeros((S, len(COUNT)))
    starts = {}
    for d, ros in enumerate(rosters):
        free = np.ones((S, len(SLOTS)), bool)
        for p in sorted(ros, key=lambda p: -sim.prio.get(p, -9)):
            a = active(p)[:, d]
            if not a.any():
                continue
            placed = np.zeros(S, bool)
            el = sim.elig[p]
            for slot in SLOT_ORDER:
                if el[slot]:
                    can = a & ~placed & free[:, slot]
                    free[can, slot] = False
                    placed |= can
            tot[placed] += pg(p)
            starts[p] = starts.get(p, 0) + placed.mean()
    return tot, starts


def parse_banked(x):
    f = x.split(",")
    (fgm, fga), (ftm, fta) = (map(float, f[0].split("/"))), (map(float, f[1].split("/")))
    return np.array([fgm, fga, ftm, fta] + [float(v) for v in f[2:]])


BANK_ME, BANK_OPP = (parse_banked(args.banked[0]), parse_banked(args.banked[1])) if args.banked else (0, 0)
# Noise scales with the share of the week still to play (banked stats are known).
frac = D / 7 if args.banked else 1.0
rng = np.random.default_rng(7)
NM, NO = rng.normal(size=(S, 9)) * e.sd * np.sqrt(frac), rng.normal(size=(S, 9)) * e.sd * np.sqrt(frac)
mine = s[s.team_id == args.me].player_id.tolist()
opp_tot, _ = week([s[s.team_id == args.opp].player_id.tolist()] * D)
O = e._cats(opp_tot + BANK_OPP) + NO


def score(tot):
    m = e._cats(tot + BANK_ME) + NM
    win = m > O
    win[:, -1] = m[:, -1] < O[:, -1]
    n = win.sum(1)
    return n.mean(), (n >= 5).mean(), win.mean(0)


# ---------- rest-of-season value of your players -> drop pool ----------
others = {t: g.player_id.tolist() for t, g in s.groupby("team_id") if t != args.me}
opp_cats = np.stack([e._cats(e._totals(ids)) for ids in others.values()])


def ros(ids):
    return float(e._p_week(e._cat_probs(e._cats(e._totals(ids)), opp_cats)).mean())


healthy = [p for p in mine if status.get(p, "") not in OUT and df.at[p, "name"] not in args.protect]
base_ros = ros(mine)
ros_loss = {p: base_ros - ros([q for q in mine if q != p]) for p in healthy}
pool = sorted(ros_loss, key=ros_loss.get)[: args.drop_pool]

il_names = set(args.il)
il_slot = set(s[(s.team_id == args.me) & (s.slot == "IL")].player_id) - set(out_days)  # day-to-day guys come back
moved = {by_name_all[n] for n in il_names}
active_roster = [p for p in mine if p not in il_slot | moved]
free_spots = max(args.roster_size - len(active_roster), 0)
mine_all = mine
mine = [p for p in mine if p not in il_slot | moved] + [p for p in mine if p in il_slot | moved]
base = [list(mine)] * D
base_tot, base_st = week(base)
b_n, b_p, b_c = score(base_tot)
name = lambda p: "(open spot)" if p == -1 else df.at[p, "name"]
first = days.index(args.first_add) if args.first_add in days else 0
print(f"{e.teams[args.me]} vs {e.teams[args.opp]}, {args.start}..{args.end}; adds play from {days[first]}")
print(f"current roster: expected cats {b_n:.2f}, P(win) {b_p*100:.1f}%, starts {sum(base_st.values()):.1f}; open roster spots {free_spots}\n")
print("Rest-of-season value (drop = your avg weekly win% vs the field falls by):")
for p in sorted(ros_loss, key=ros_loss.get):
    print(f"  {name(p):<24}{ros_loss[p]*100:+6.2f} pts  week-2 starts {base_st.get(p, 0):.1f}" + ("   <- drop pool" if p in pool else ""))


EMPTY = -1   # pseudo-player: an open roster spot (no drop needed)


def apply(plan, add, drop, d):
    """New per-day rosters: from day d, `drop` out, `add` in."""
    return [r if i < d else [p for p in r if p != drop] + [add] for i, r in enumerate(plan)]


def objective(tot):
    n, pw, _ = score(tot)
    return pw + 0.02 * n if args.objective == "win" else n


def eligible_day(p):
    f = df.at[p, "fa_from"] if "fa_from" in df.columns else None
    lo = first
    if isinstance(f, str) and f:
        nxt = (pd.Timestamp(f) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        lo = max(lo, days.index(nxt) if nxt in days else D)
    return lo


def best_move(plan, droppable, taken, cands=None):
    cur_n = objective(week(plan)[0])
    out = []
    for p in cands or fa_ids:
        if p in taken or status.get(p, "") in OUT:
            continue
        g = plays.get(df.at[p, "nba_team"], np.zeros(D, bool))
        lo = eligible_day(p)
        best = None
        for d in range(lo, D):
            if not g[d:].any():
                break
            for x, xfrom in droppable:
                if xfrom > d:   # can't drop a streamer before he's added
                    continue
                if x != EMPTY and not all(x in plan[i] for i in range(d, D)):
                    continue
                n = objective(week(apply(plan, p, x, d))[0])
                if best is None or n > best[0]:
                    best = (n, d, x)
        if best:
            out.append((best[0] - cur_n, p, best[1], best[2]))
    return sorted(out, key=lambda r: -r[0])


if args.plan:
    by_name = {df.at[p, "name"]: p for p in list(mine) + fa_ids}
    plan = base
    for mv in args.plan:
        add, rest = mv.split(">"); drop, day = rest.split("@")
        plan = apply(plan, by_name[add.strip()], by_name[drop.strip()], days.index(f"{args.start[:4]}-{day.strip()}"))
    tot, st = week(plan)
    n, pw, pc = score(tot)
    print(f"\nYour plan: {'; '.join(args.plan)}")
    print(f"expected cats {b_n:.2f} -> {n:.2f}; P(win) {b_p*100:.1f}% -> {pw*100:.1f}%; starts {sum(base_st.values()):.1f} -> {sum(st.values()):.1f}")
    print("category P(win): " + "  ".join(f"{c} {a*100:.0f}->{b*100:.0f}" for c, a, b in zip(CATS, b_c, pc)))
    print(f"rest-of-season with the final roster: {base_ros*100:.1f}% -> {ros(plan[-1])*100:.1f}% avg weekly win")
    sys.exit()

# ---------- single moves: every free agent ----------
# Quick screen (earliest day, swapping for your least valuable player), then a full search on the top 40.
start_drops = [(EMPTY, 0)] * free_spots + [(x, 0) for x in pool]
screen = best_move(base, [start_drops[0]], set(mine))
short = [p for _, p, _, _ in screen[:40]]
moves = best_move(base, start_drops, set(mine), short)
unit = "P(win) pts + 0.02/cat" if args.objective == "win" else "expected cats"
print(f"\nTop free agents for this week (best single move; gain in {unit}):")
print(f"{'player':<24}{'tm':<5}{'pos':<11}{'avail':<8}{'games':>5}  {'gain':>6}  {'ROS':>6}  add day / drop")
for gain, p, d, x in moves[:25]:
    g = plays.get(df.at[p, "nba_team"], np.zeros(D, bool))
    av = df.at[p, "fa_from"] or "FA"
    # ROS: change in your avg weekly win% (rest of season) if he permanently replaces the dropped player
    r_ = ros([q for q in mine if q != x] + [p]) - base_ros
    print(f"{name(p):<24}{df.at[p,'nba_team']:<5}{df.at[p,'positions']:<11}{str(av):<8}{int(g[d:].sum()):>5}  {gain:+6.3f}  {r_*100:+6.2f}  {days[d][5:]} / {name(x)}")

# ---------- greedy plan ----------
plan, taken = base, set(mine)
droppable = list(start_drops)
steps = []
for k in range(args.adds):
    mv = best_move(plan, droppable, taken, short)
    if not mv or mv[0][0] <= 0.002:
        break
    gain, p, d, x = mv[0]
    plan = apply(plan, p, x, d)
    taken.add(p)
    if x == EMPTY:
        droppable.remove((EMPTY, 0))
    else:
        droppable = [(q, f) for q, f in droppable if q != x]
    droppable.append((p, d + 1))
    steps.append((p, d, x, gain))

tot, st = week(plan)
n, pw, pc = score(tot)
print(f"\nPlan ({len(steps)} adds):")
for p, d, x, gain in steps:
    print(f"  {days[d][5:]}: add {name(p)} ({df.at[p,'nba_team']}, {df.at[p,'positions']}), drop {name(x)}   {gain:+.3f}")
print(f"\nexpected cats {b_n:.2f} -> {n:.2f}; P(win) {b_p*100:.1f}% -> {pw*100:.1f}%; starts {sum(base_st.values()):.1f} -> {sum(st.values()):.1f}")
print("category P(win): " + "  ".join(f"{c} {a*100:.0f}->{b*100:.0f}" for c, a, b in zip(CATS, b_c, pc)))
kept = [p for p, *_ in steps if p in plan[-1]]
if kept:
    after = [q for q in plan[-1]]
    print(f"rest-of-season with the final roster: {base_ros*100:.1f}% -> {ros(after)*100:.1f}% avg weekly win")


# ---------- JSON export (fantasy-desk page) ----------
if args.json:
    import datetime, json

    def catd(vals):
        return {c: (round(float(v), 4) if "%" in c else round(float(v), 1)) for c, v in zip(CATS, vals)}

    def info(p):
        return {"id": int(p), "name": name(p), "team": str(df.at[p, "nba_team"]), "pos": str(df.at[p, "positions"]),
                "status": str(status.get(p, "") or "")}

    def outcome(pl):
        t, stx = week(pl)
        n_, pw_, pc_ = score(t)
        return {"p_win": round(float(pw_), 4), "exp_cats": round(float(n_), 3),
                "p_cat": {c: round(float(v), 4) for c, v in zip(CATS, pc_)}, "starts": round(float(sum(stx.values())), 1)}

    base_out = outcome(base)
    fa_rows = []
    for gain, p, d, x in moves[:30]:
        o = outcome(apply(base, p, x, d))
        g = plays.get(df.at[p, "nba_team"], np.zeros(D, bool))
        fa_rows.append({**info(p), "avail": str(df.at[p, "fa_from"] or "FA"), "games": int(g[d:].sum()),
                        "day": days[d], "drop": None if x == EMPTY else info(x),
                        "d_win": round(o["p_win"] - base_out["p_win"], 4),
                        "d_cats": round(o["exp_cats"] - base_out["exp_cats"], 3),
                        "d_cat": {c: round(o["p_cat"][c] - base_out["p_cat"][c], 4) for c in CATS},
                        "d_ros": round((ros([q for q in mine if q != x] + [p]) - base_ros) * 100, 2)})
    plan_rows, cur = [], base
    prev = base_out
    for p, d, x, gain in steps:
        cur = apply(cur, p, x, d)
        o = outcome(cur)
        plan_rows.append({"day": days[d], "add": info(p), "drop": None if x == EMPTY else info(x),
                          "d_win": round(o["p_win"] - prev["p_win"], 4),
                          "d_cats": round(o["exp_cats"] - prev["exp_cats"], 3),
                          "p_win_after": o["p_win"]})
        prev = o
    final = outcome(plan)
    roster_rows = [{**info(p), "slot": str(s.loc[s.player_id == p, "slot"].iloc[0]) if (s.player_id == p).any() else "",
                    "ros_value": round(ros_loss.get(p, 0.0) * 100, 2), "week_starts": round(float(base_st.get(p, 0)), 1),
                    "droppable": p in pool}
                   for p in mine]
    out = {
        "league": "basketball", "generated_at": datetime.datetime.now().isoformat(timespec="minutes"),
        "team": e.teams[args.me], "opponent": e.teams[args.opp], "week": {"start": args.start, "end": args.end},
        "cats": CATS, "punt": ["FG%", "TO"], "lower_is_better": ["TO"],
        "adds_left": args.adds, "open_spots": free_spots,
        "banked": {"me": catd(e._cats(np.asarray(BANK_ME, float))) if args.banked else None,
                   "opp": catd(e._cats(np.asarray(BANK_OPP, float))) if args.banked else None},
        "projected": {"me": catd(e._cats(base_tot.mean(0) + BANK_ME)), "opp": catd(e._cats(opp_tot.mean(0) + BANK_OPP))},
        "current": base_out, "with_plan": final,
        "ros": {"before": round(base_ros * 100, 1), "after": round(ros(plan[-1]) * 100, 1)},
        "plan": plan_rows, "free_agents": fa_rows, "roster": roster_rows,
    }
    Path(args.json).write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"\nwrote {args.json}")

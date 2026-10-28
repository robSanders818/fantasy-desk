"""Category records from daily active-lineup totals: this week vs every team, and the season so far.

Totals are [FGM, FGA, FTM, FTA, 3PTM, PTS, REB, AST, ST, BLK, TO]. FG% and FT% are made / attempted
over the period; TO is lower-is-better; equal values are ties.
"""
from datetime import date, timedelta

CATS = ["FG%", "FT%", "3PTM", "PTS", "REB", "AST", "ST", "BLK", "TO"]
SEASON_START = date(2026, 10, 20)
WEEK2_START = date(2026, 10, 26)       # week 1 is the short opening week (Tue-Sun)


def week_of(d: date) -> int:
    return 1 if d < WEEK2_START else 2 + (d - WEEK2_START).days // 7


def add(a: list[float], b: list[float]) -> list[float]:
    return [x + y for x, y in zip(a, b)]


def cats(t: list[float]) -> dict:
    return {"FG%": t[0] / t[1] if t[1] else 0.0, "FT%": t[2] / t[3] if t[3] else 0.0,
            "3PTM": t[4], "PTS": t[5], "REB": t[6], "AST": t[7], "ST": t[8], "BLK": t[9], "TO": t[10]}


def compare(a: list[float], b: list[float]) -> list[int]:
    """[wins, losses, ties] for team a vs team b over the same period."""
    ca, cb = cats(a), cats(b)
    w = l = t = 0
    for c in CATS:
        x, y = (-ca[c], -cb[c]) if c == "TO" else (ca[c], cb[c])
        if abs(x - y) < 1e-9:
            t += 1
        elif x > y:
            w += 1
        else:
            l += 1
    return [w, l, t]


def period_totals(days: dict, start: date, end: date, teams: list[int]) -> dict[int, list[float]]:
    out = {t: [0.0] * 11 for t in teams}
    d = start
    while d <= end:
        for t, v in days.get(d.isoformat(), {}).items():
            if int(t) in out:
                out[int(t)] = add(out[int(t)], v)
        d += timedelta(days=1)
    return out


def this_week(week_tot: dict[int, list[float]], me: int, opp: int, names: dict[int, str]) -> dict:
    rows, total = [], [0, 0, 0]
    for t in sorted(week_tot):
        if t == me:
            continue
        r = compare(week_tot[me], week_tot[t])
        total = [x + y for x, y in zip(total, r)]
        rows.append({"team_id": t, "team": names.get(t, str(t)), "record": r, "opponent": t == opp})
    rows.sort(key=lambda x: (-x["opponent"], -(x["record"][0] - x["record"][1])))
    return {"rows": rows, "total": total}


def season(days: dict, pairs: dict, today: date, names: dict[int, str]) -> dict:
    """Season so far (through today, live): category record vs actual opponents, all-play
    record, matchup W-L-T, and category totals."""
    teams = sorted(names)
    acc = {t: {"cat": [0, 0, 0], "allplay": [0, 0, 0], "matchups": [0, 0, 0], "tot": [0.0] * 11} for t in teams}
    weeks = []
    for w in range(1, week_of(today) + 1):
        start = SEASON_START if w == 1 else WEEK2_START + timedelta(days=7 * (w - 2))
        end = min(WEEK2_START - timedelta(days=1) if w == 1 else start + timedelta(days=6), today)
        tot = period_totals(days, start, end, teams)
        finished = end < today
        for t in teams:
            acc[t]["tot"] = add(acc[t]["tot"], tot[t])
            for o in teams:
                if o != t:
                    acc[t]["allplay"] = [x + y for x, y in zip(acc[t]["allplay"], compare(tot[t], tot[o]))]
        for a, b in pairs.get(str(w), []):
            if a not in tot or b not in tot:
                continue
            ra = compare(tot[a], tot[b])
            acc[a]["cat"] = [x + y for x, y in zip(acc[a]["cat"], ra)]
            acc[b]["cat"] = [x + y for x, y in zip(acc[b]["cat"], [ra[1], ra[0], ra[2]])]
            if finished:   # a matchup only counts in W-L-T once its week is over
                res = 0 if ra[0] > ra[1] else 1 if ra[1] > ra[0] else 2
                acc[a]["matchups"][res] += 1
                acc[b]["matchups"][[1, 0, 2][res]] += 1
        weeks.append({"week": w, "start": start.isoformat(), "end": end.isoformat(), "finished": finished})
    rows = []
    for t in teams:
        c = cats(acc[t]["tot"])
        rows.append({"team_id": t, "team": names[t], "cat_record": acc[t]["cat"], "allplay": acc[t]["allplay"],
                     "matchups": acc[t]["matchups"],
                     "totals": {k: round(v, 4) if "%" in k else round(v) for k, v in c.items()}})
    rows.sort(key=lambda r: -(r["allplay"][0] + r["allplay"][2] / 2) / max(sum(r["allplay"]), 1))
    return {"weeks": weeks, "rows": rows}

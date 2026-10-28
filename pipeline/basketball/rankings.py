"""Power rankings: each team's projected weekly win% and category win% against the rest of the league.

Rest-of-season per-game rates come from season.setup (last season as the prior, 2026-27 games at 2x
recency), with current rosters and injury statuses. A team's weekly totals come from the daily-lineup
simulation over the rest of the schedule; P(win a category) vs each opponent uses last season's
week-to-week spread, and P(win the week) = P(win 5+ of 9).

    python rankings.py STATS_PSV STANDINGS_JSON OUT_JSON
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model import CATS  # noqa: E402
from season import setup  # noqa: E402


def main(stats: str, standings: str, out: str) -> None:
    e, s = setup(stats, recency=2.0)
    st = {int(r["team_id"]): r for r in json.loads(Path(standings).read_text())}
    rosters = {int(t): g.player_id.tolist() for t, g in s.groupby("team_id")}
    cats = {t: e._cats(e._totals(ids)) for t, ids in rosters.items()}
    rows = []
    for t in sorted(cats):
        opp_ids = [o for o in cats if o != t]
        pc = e._cat_probs(cats[t], np.stack([cats[o] for o in opp_ids]))     # (opponents, 9 cats)
        pw = e._p_week(pc)                                                   # (opponents,)
        info = st.get(t, {})
        rows.append({
            "team_id": t, "team": info.get("team", e.teams.get(t, str(t))),
            "record": info.get("record", ""), "standing": info.get("rank"),
            "proj_week": round(float(pw.mean()), 4),
            "p_cat": {c: round(float(v), 4) for c, v in zip(CATS, pc.mean(0))},
            "vs": {str(o): round(float(p), 4) for o, p in zip(opp_ids, pw)},
        })
    rows.sort(key=lambda r: -r["proj_week"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    Path(out).write_text(json.dumps(rows, ensure_ascii=False))


if __name__ == "__main__":
    main(*sys.argv[1:4])

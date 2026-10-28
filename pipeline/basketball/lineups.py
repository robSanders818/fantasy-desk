"""Daily-lineup simulation: how many of each player's games actually count.

Yahoo starts 13 players a day in fixed slots (PG PG SG SG G SF SF PF PF F C C Util); the
rest sit on the bench. Each day of the 2026-27 NBA schedule, players whose team plays (and
who are healthy that day, drawn from their projected games played) are slotted greedily by
value, most specific slot first. Repeated over several random seasons.

    starts(roster)      -> expected games started per player (season)
    candidate_gain(...) -> for a player you might add: games he'd start and the starter
                           production he'd displace on your roster
"""

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
SCHED = ROOT / "data" / "league" / "nba_schedule_2026.csv"
SLOTS = ["PG", "PG", "SG", "SG", "G", "SF", "SF", "PF", "PF", "F", "C", "C", "UTIL"]
# Fill specific positions first, then G/F, then Util.
SLOT_ORDER = [i for i, s in enumerate(SLOTS) if s in ("PG", "SG", "SF", "PF", "C")] + \
             [i for i, s in enumerate(SLOTS) if s in ("G", "F")] + [SLOTS.index("UTIL")]
ESPN_TO_YAHOO = {"GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS", "UTAH": "UTA", "WSH": "WAS"}
SAMPLES = 8


def eligible(positions: str) -> np.ndarray:
    pos = set(str(positions).split(","))
    ok = []
    for s in SLOTS:
        ok.append(s == "UTIL" or s in pos or (s == "G" and pos & {"PG", "SG"}) or (s == "F" and pos & {"SF", "PF"}))
    return np.array(ok, dtype=bool)


class LineupSim:
    def __init__(self, df: pd.DataFrame, priority: pd.Series):
        sched = pd.read_csv(SCHED)
        sched = sched[(sched.home != "TBD") & (sched.away != "TBD")]
        for c in ("home", "away"):
            sched[c] = sched[c].replace(ESPN_TO_YAHOO)
        days = sorted(sched.date.unique())
        self.D = len(days)
        di = {d: i for i, d in enumerate(days)}
        plays = {}
        for r in sched.itertuples():
            for t in (r.home, r.away):
                plays.setdefault(t, np.zeros(self.D, dtype=bool))[di[r.date]] = True
        self.team_games = {t: int(v.sum()) for t, v in plays.items()}
        self.plays = plays
        self.df = df
        self.prio = priority
        self.elig = {pid: eligible(p) for pid, p in df["positions"].items()}
        # Chance a player is active on a given team game day.
        self.p_active = {pid: min(1.0, g / max(self.team_games.get(t, 82), 1))
                         for pid, g, t in zip(df.index, df["pg_GP"], df["nba_team"])}
        self._cache = {}

    def _active(self, pid, rng) -> np.ndarray:
        team_days = self.plays.get(self.df.at[pid, "nba_team"], np.zeros(self.D, dtype=bool))
        return team_days[None, :] & (rng.random((SAMPLES, self.D)) < self.p_active[pid])

    def simulate(self, roster: tuple) -> dict:
        """Greedy daily lineups for a roster. Returns starts per player and per-day slot state."""
        if roster in self._cache:
            return self._cache[roster]
        rng = np.random.default_rng(abs(hash(roster)) % (2**32))
        order = sorted(roster, key=lambda p: -self.prio.get(p, 0))
        act = {p: self._active(p, rng) for p in order}
        n = len(SLOTS)
        occ = np.full((SAMPLES, self.D, n), -1, dtype=int)          # roster index in `order`
        starts = np.zeros(len(order))
        for s in range(SAMPLES):
            for d in range(self.D):
                free = np.ones(n, dtype=bool)
                for k, p in enumerate(order):
                    if not act[p][s, d]:
                        continue
                    el = self.elig[p]
                    for slot in SLOT_ORDER:
                        if free[slot] and el[slot]:
                            free[slot] = False
                            occ[s, d, slot] = k
                            starts[k] += 1
                            break
        out = {"order": order, "starts": dict(zip(order, starts / SAMPLES)), "occ": occ}
        self._cache[roster] = out
        return out

    def candidate(self, roster: tuple, pid: int, pg: pd.DataFrame) -> tuple[float, np.ndarray]:
        """Season games `pid` would start on `roster`, and the per-game production of the
        starters he would bump (summed over the season). pg: per-game COUNT stats by player."""
        sim = self.simulate(roster)
        occ, order = sim["occ"], sim["order"]
        rng = np.random.default_rng(pid)
        active = self._active(pid, rng)                                # (S, D)
        el = self.elig[pid]
        slots_ok = np.where(el)[0]
        occ_e = occ[:, :, slots_ok]                                    # (S, D, k)
        open_ = (occ_e < 0).any(axis=2)
        prio = np.array([self.prio.get(p, 0) for p in order] + [np.inf])
        occ_prio = np.where(occ_e >= 0, prio[np.where(occ_e >= 0, occ_e, -1)], np.inf)
        weakest = occ_prio.argmin(axis=2)
        weakest_prio = np.take_along_axis(occ_prio, weakest[..., None], axis=2)[..., 0]
        bump = active & ~open_ & (weakest_prio < self.prio.get(pid, 0))
        start = active & open_
        bumped_idx = np.take_along_axis(occ_e, weakest[..., None], axis=2)[..., 0][bump]
        lost = np.zeros(pg.shape[1])
        if len(bumped_idx):
            counts = np.bincount(bumped_idx, minlength=len(order))
            lost = counts @ pg.loc[order].to_numpy()
        return float((start | bump).sum() / SAMPLES), lost / SAMPLES

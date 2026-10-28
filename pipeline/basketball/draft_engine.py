"""Live-draft engine: WAR (weekly Win% Above Replacement) for every available player.

WAR = how much adding a player raises your average P(win the week) against the other nine
teams, compared with adding a waiver-level player. Every team's unfilled roster spots are
filled with waiver-level players, so half-drafted rosters compare fairly.

Matchup model (same as draft_model.py): team weekly totals = sum of per-game rates x expected
games; per-category noise from last season's weekly results; P(win week) = P(win 5+ of 9).
"""

from math import sqrt
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import ndtr

from lineups import LineupSim
from model import (
    CATS, KEEPERS, LEAGUE, MY_TEAM, N_TEAMS, SEASON_GAMES, WEIGHTS,
    load_players, predict_keepers, snake_order, value_players,
)

PUNT = ["FG%", "TO"]
IL_COVER = 1.0     # share of an Out (IL-eligible) absence covered by a pickup
BENCH_COVER = 0.5  # share of day-to-day absences covered by the bench (only used without lineup sim)
USE_LINEUPS = True  # simulate daily positional lineups (data/league/nba_schedule_2026.csv)
ROSTER_SIZE = 17
ROUNDS = ROSTER_SIZE - KEEPERS
COUNT = ["FGM", "FGA", "FTM", "FTA", "3PTM", "PTS", "REB", "AST", "ST", "BLK", "TO"]
CI = {c: i for i, c in enumerate(COUNT)}


class Engine:
    def __init__(self) -> None:
        base = load_players()
        live = [c for c in CATS if c not in PUNT]
        mv = value_players(base, WEIGHTS, live)
        df = pd.concat([base, mv.drop(columns=["value"])], axis=1)
        df["my_value"] = mv["value"]
        df["std_value"] = value_players(base, WEIGHTS, CATS)["value"]
        df = df[df["pg_PTS"].notna() & df["pg_GP"].gt(0)].copy()
        df["player_id"] = df["player_id"].astype(int)
        self.df = df.set_index("player_id", drop=False)
        self.teams = pd.read_csv(LEAGUE / "teams.csv").set_index("team_id")["name"].to_dict()

        # Week-to-week noise from last season's real weekly totals.
        hist = pd.read_csv(LEAGUE / "matchups_2025.csv")
        reg = hist[hist.week <= 19]
        self.sd = np.array([(reg[c] - reg.groupby("team")[c].transform("mean")).std() for c in CATS])

        # Expected weekly contribution per player; games/week scaled so a typical 17-man
        # roster matches last season's average weekly FGA.
        top = self.df.nlargest(ROSTERED := ROSTER_SIZE * N_TEAMS, "std_value")
        team_fga = (top["pg_FGA"] * top["pg_GP"] / SEASON_GAMES).sum() / N_TEAMS
        self.scale = reg["FGA"].mean() / team_fga
        g = self.df["pg_GP"] / SEASON_GAMES * self.scale
        self.W = pd.DataFrame({c: self.df[f"pg_{c}"] * g for c in COUNT}, index=self.df.index)

        # Waiver level: players just outside the league's rostered pool.
        ranked = self.df.sort_values("std_value", ascending=False).index
        self.repl = self.W.loc[ranked[ROSTERED : ROSTERED + 20]].mean().to_numpy()

        # Missed games aren't all lost: an Out player sits in an IL slot (6 of them) while a
        # pickup plays, and day-to-day absences are partly covered by the bench. Credit a
        # waiver-level fill-in for that share of each player's missed games.
        self.keepers = self._load_keepers()
        self.pg = pd.DataFrame({c: self.df[f"pg_{c}"] for c in COUNT}, index=self.df.index)
        self.sim = None
        if USE_LINEUPS and (LEAGUE / "nba_schedule_2026.csv").exists():
            # Daily lineups decide which games count; the bench covers day-to-day absences, so
            # only IL-type absences (Out / known injuries) get a waiver fill-in credit.
            self.sim = LineupSim(self.df, self.df["z_zsum"].fillna(-5))
            self.il_credit = pd.DataFrame(np.outer(self._il_share(), self.repl), index=self.df.index, columns=COUNT)
            self._calibrate()
        else:
            self.W = self.W + np.outer(self._cover_share(), self.repl)

    def _il_share(self) -> np.ndarray:
        df = self.df
        il_games = df["games_missed"].fillna(0)
        other = (SEASON_GAMES - df["pg_GP"] - il_games).clip(lower=0)
        out_now = df["status"].isin(["O", "INJ", "OFS"]).to_numpy()
        return ((il_games + np.where(out_now, other, 0)) / SEASON_GAMES).to_numpy()

    def _calibrate(self) -> None:
        """Rescale so a typical full roster, after lineup limits, matches last season's weekly FGA."""
        pool = [p for p in self.df.sort_values("std_value", ascending=False).index
                if not any(p in v for v in self.keepers.values())]
        rosters = {t: list(v) for t, v in self.keepers.items()}
        for i, p in enumerate(pool[: (ROSTER_SIZE - KEEPERS) * N_TEAMS]):
            rosters[sorted(rosters)[i % N_TEAMS]].append(p)
        used = total = 0.0
        for ids in rosters.values():
            st = self.sim.simulate(tuple(sorted(ids)))["starts"]
            used += sum(self.df.at[p, "pg_FGA"] * st[p] for p in ids)
            total += sum(self.df.at[p, "pg_FGA"] * self.df.at[p, "pg_GP"] for p in ids)
        self.start_factor = used / total
        self.unit = self.scale / self.start_factor / SEASON_GAMES   # weekly units per game started
        self.repl = self.repl                                          # waiver fill-ins stream at full rate

    def starts(self, ids) -> dict:
        return self.sim.simulate(tuple(sorted(ids)))["starts"] if self.sim else {}

    def _cover_share(self) -> np.ndarray:
        """Fraction of a full season that a fill-in plays in this player's place."""
        df = self.df
        il_games = df["games_missed"].fillna(0)                      # known absences (overrides.csv)
        other = (SEASON_GAMES - df["pg_GP"] - il_games).clip(lower=0)  # projected/durability absences
        other_cover = np.where(df["status"].isin(["O", "INJ", "OFS"]), IL_COVER, BENCH_COVER)
        return ((il_games * IL_COVER + other * other_cover) / SEASON_GAMES).to_numpy()

    # ---------- keepers ----------
    def _load_keepers(self) -> dict[int, list[int]]:
        """team_id -> player_ids. Actual keepers file wins over the estimate."""
        actual = LEAGUE / "keepers.csv"
        if actual.exists():
            k = pd.read_csv(actual)
            self.keepers_source = "actual (data/league/keepers.csv)"
            return {int(t): [int(p) for p in g.player_id if int(p) in self.df.index] for t, g in k.groupby("team_id")}
        df = self.df.reset_index(drop=True)
        others = predict_keepers(df.assign(std_value=df["std_value"].where(df.team_id != MY_TEAM)), "std_value")
        others &= df.team_id != MY_TEAM
        names = [n.strip() for n in (LEAGUE / "my_keepers.txt").read_text().splitlines() if n.strip() and not n.startswith("#")]
        mine = df[(df.team_id == MY_TEAM) & df.name.isin(names)]
        out = {t: df.loc[others & (df.team_id == t), "player_id"].astype(int).tolist() for t in self.teams if t != MY_TEAM}
        out[MY_TEAM] = mine["player_id"].astype(int).tolist()
        self.keepers_source = "estimated (others: top 13 by all-category value; you: my_keepers.txt)"
        return out

    # ---------- matchup math ----------
    def _totals(self, ids: list[int]) -> np.ndarray:
        if self.sim is not None and ids:
            st = self.starts(ids)
            g = np.array([st[p] for p in ids])
            t = (self.pg.loc[ids].to_numpy() * g[:, None]).sum(axis=0) * self.unit
            t = t + self.il_credit.loc[ids].to_numpy().sum(axis=0)
        else:
            t = self.W.loc[ids].to_numpy().sum(axis=0) if ids else np.zeros(len(COUNT))
        return t + self.repl * max(ROSTER_SIZE - len(ids), 0)

    @staticmethod
    def _cats(t: np.ndarray) -> np.ndarray:
        """COUNT totals (..., 11) -> category values (..., 9) in CATS order."""
        fg = t[..., CI["FGM"]] / t[..., CI["FGA"]]
        ft = t[..., CI["FTM"]] / t[..., CI["FTA"]]
        rest = [t[..., CI[c]] for c in ["3PTM", "PTS", "REB", "AST", "ST", "BLK", "TO"]]
        return np.stack([fg, ft, *rest], axis=-1)

    def _cat_probs(self, me: np.ndarray, opp: np.ndarray) -> np.ndarray:
        """me (..., 9 cats), opp (k, 9 cats) -> P(win cat) (..., k, 9)."""
        margin = me[..., None, :] - opp
        margin[..., -1] *= -1  # TO: fewer is better
        return ndtr(margin / (self.sd * sqrt(2)))

    @staticmethod
    def _p_week(p: np.ndarray) -> np.ndarray:
        """P(win more than half of 9 independent categories); p (..., 9) -> (...)."""
        dist = np.zeros(p.shape[:-1] + (p.shape[-1] + 1,))
        dist[..., 0] = 1.0
        for j in range(p.shape[-1]):
            q = p[..., j : j + 1]
            dist[..., 1:] = dist[..., 1:] * (1 - q) + dist[..., :-1] * q
            dist[..., 0] *= 1 - q[..., 0]
        return dist[..., 5:].sum(axis=-1)

    # ---------- draft state ----------
    def rosters(self, picks: list[dict]) -> dict[int, list[int]]:
        r = {t: list(v) for t, v in self.keepers.items()}
        for p in picks:
            r.setdefault(p["team_id"], []).append(p["player_id"])
        return r

    def snapshot(self, picks: list[dict], order: list[int], seq: list[int] | None = None) -> dict:
        """order: team_id for draft slots 1..10 (snake). seq: explicit team_id for every pick (overrides)."""
        rosters = self.rosters(picks)
        taken = {pid for ids in rosters.values() for pid in ids}
        avail = [pid for pid in self.df.index if pid not in taken]

        seq = seq or [order[s - 1] for s in snake_order(N_TEAMS, ROUNDS)]
        n = len(picks)
        on_clock = seq[n] if n < len(seq) else None
        my_turns = [i for i in range(n, len(seq)) if seq[i] == MY_TEAM]
        # Picks by others before your next turn (after the current one if you're up now).
        nxt = my_turns[1] if my_turns and my_turns[0] == n and len(my_turns) > 1 else (my_turns[0] if my_turns else None)
        picks_before_next = (nxt - n - (1 if on_clock == MY_TEAM else 0)) if nxt is not None else None

        opp_ids = [t for t in self.teams if t != MY_TEAM]
        opp = self._cats(np.stack([self._totals(rosters.get(t, [])) for t in opp_ids]))
        mine = rosters.get(MY_TEAM, [])
        me_tot = self._totals(mine)
        base_cat = self._cat_probs(self._cats(me_tot), opp)          # (9 opp, 9 cats)
        base_week = self._p_week(base_cat)                            # (9 opp,)

        # Each candidate replaces one waiver-level filler on your roster.
        open_spot = len(mine) < ROSTER_SIZE
        if self.sim is not None and mine:
            # Each candidate starts only when a slot he fits is open, or by bumping a weaker starter.
            roster = tuple(sorted(mine))
            cand = np.zeros((len(avail), len(COUNT)))
            for i, pid in enumerate(avail):
                g, lost = self.sim.candidate(roster, pid, self.pg)
                cand[i] = (self.pg.loc[pid].to_numpy() * g - lost) * self.unit + self.il_credit.loc[pid].to_numpy()
            cand -= self.repl if open_spot else 0
        else:
            cand = self.W.loc[avail].to_numpy() - (self.repl if open_spot else 0)
        cand_tot = me_tot[None, :] + cand                             # (P, 11)
        cand_cat = self._cat_probs(self._cats(cand_tot), opp)         # (P, 9 opp, 9 cats)
        cand_week = self._p_week(cand_cat)                            # (P, 9 opp)
        wor = cand_week.mean(axis=1) - base_week.mean()
        dcat = cand_cat.mean(axis=1) - base_cat.mean(axis=0)          # (P, 9 cats)

        # Chance a player is still there at your next pick: others draft roughly by Yahoo rank.
        a = self.df.loc[avail]
        order_pos = a["preseason_rank"].rank(method="first").to_numpy()
        if picks_before_next is None:
            p_avail = np.full(len(avail), np.nan)
        else:
            k = picks_before_next
            p_avail = ndtr((order_pos - k - 0.5) / (3 + 0.3 * k))

        rows = []
        for i, pid in enumerate(avail):
            r = a.loc[pid]
            rows.append({
                "player_id": int(pid), "name": r["name"], "nba_team": r["nba_team"], "positions": r["positions"],
                "status": "" if pd.isna(r["status"]) else r["status"], "yahoo_rank": int(r["preseason_rank"]),
                "fantasy_team": "" if r["team_id"] == 0 else self.teams.get(int(r["team_id"]), ""),
                "value": round(float(r["my_value"]), 2), "gp": round(float(r["pg_GP"])),
                "wor": round(float(wor[i]) * 100, 2),
                "p_avail_next": None if np.isnan(p_avail[i]) else round(float(p_avail[i]), 2),
                "dcat": {c: round(float(dcat[i, j]) * 100, 1) for j, c in enumerate(CATS)},
                "per_game": {c: round(float(r[f"pg_{c}"]), 1) for c in ["PTS", "REB", "AST", "ST", "BLK", "3PTM", "TO"]}
                | {"FG%": round(float(r["pg_FGM"] / r["pg_FGA"]), 3) if r["pg_FGA"] else None,
                   "FT%": round(float(r["pg_FTM"] / r["pg_FTA"]), 3) if r["pg_FTA"] else None},
            })
        rows.sort(key=lambda x: -x["wor"])

        def roster_rows(t):
            return [{"player_id": int(pid), "name": self.df.at[pid, "name"], "positions": self.df.at[pid, "positions"],
                     "keeper": pid in self.keepers.get(t, [])} for pid in rosters.get(t, [])]

        return {
            "keepers_source": self.keepers_source,
            "punt": PUNT, "cats": CATS,
            "teams": {int(t): n for t, n in self.teams.items()}, "my_team": MY_TEAM,
            "order": order, "rounds": ROUNDS, "seq": seq,
            "pick_no": n + 1, "total_picks": len(seq), "on_clock": on_clock,
            "my_next_pick": (my_turns[0] + 1) if my_turns else None,
            "picks_before_next": picks_before_next,
            "picks": [{**p, "name": self.df.at[p["player_id"], "name"] if p["player_id"] in self.df.index else str(p["player_id"]),
                       "team": self.teams.get(p["team_id"], "")} for p in picks],
            "my_week_win": round(float(base_week.mean()) * 100, 1),
            "my_cat_win": {c: round(float(v) * 100) for c, v in zip(CATS, base_cat.mean(axis=0))},
            "vs_team": {self.teams[t]: round(float(w) * 100) for t, w in zip(opp_ids, base_week)},
            "rosters": {int(t): roster_rows(t) for t in self.teams},
            "available": rows,
        }

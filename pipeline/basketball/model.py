"""Keeper model: 9-cat z-score values, predicted league keepers, and the draft pool.

    uv run model.py                 # blend (default)
    uv run model.py --punt FT% TO   # ignore categories you plan to punt

Method
  1. Per-game rates per player, blended from Yahoo 2026-27 projections, 2025-26 and 2024-25
     averages. A season counts less when it had few games; missing sources drop out.
  2. Z-scores per category against the ~170 players who will be rostered (17 per team).
     FG%/FT% use volume-weighted impact (makes above pool average); TO counts negatively.
  3. Value = (z-sum minus replacement level) x share of games played, so missed games pull a
     player toward what a waiver pickup would give you.
  4. Each team is predicted to keep its top 13 by value; everything else plus free agents is
     the draft pool.
"""

import argparse
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
LEAGUE = ROOT / "data" / "league"
OUT = ROOT / "data" / "model"

MY_TEAM = 9
N_TEAMS = 10
KEEPERS = 13
ROSTERED = 17 * N_TEAMS  # active roster spots league-wide after the draft
SEASON_GAMES = 82

COUNTING = ["FGM", "FGA", "FTM", "FTA", "3PTM", "PTS", "REB", "AST", "ST", "BLK", "TO"]
CATS = ["FG%", "FT%", "3PTM", "PTS", "REB", "AST", "ST", "BLK", "TO"]

# Base weights for the blend; each season's weight is scaled by min(GP, 60) / 60.
WEIGHTS = {"proj": 0.50, "ly": 0.35, "py": 0.15}
METHODS = {
    "blend": WEIGHTS,
    "last_year": {"ly": 1.0},
    "projection": {"proj": 1.0},
}


def load_players() -> pd.DataFrame:
    df = pd.concat([pd.read_csv(LEAGUE / "rosters.csv"), pd.read_csv(LEAGUE / "free_agents.csv")], ignore_index=True)
    # Projections are season totals -> per game.
    gp = df["proj_GP"].replace(0, np.nan)
    for c in COUNTING:
        df[f"proj_{c}"] = df[f"proj_{c}"] / gp
    # Trades made since the roster scrape: data/league/trades.csv
    tr_path = LEAGUE / "trades.csv"
    if tr_path.exists():
        teams = pd.read_csv(LEAGUE / "teams.csv").set_index("team_id")["name"]
        for t in pd.read_csv(tr_path).itertuples():
            hit = df["name"] == t.name
            if not hit.any():
                print(f"warning: trade for unknown player: {t.name}")
            df.loc[hit, "team_id"] = t.to_team_id
            df.loc[hit, "fantasy_team"] = teams[t.to_team_id]
    # Manual adjustments (known injuries etc.): data/league/overrides.csv
    ov_path = LEAGUE / "overrides.csv"
    df["games_missed"] = 0.0
    if ov_path.exists():
        ov = pd.read_csv(ov_path)
        missing = set(ov.name) - set(df.name)
        if missing:
            print(f"warning: overrides for unknown players: {sorted(missing)}")
        df["games_missed"] = df["name"].map(ov.set_index("name")["games_missed"]).fillna(0.0)
    return df


def blend_rates(df: pd.DataFrame, weights: dict) -> pd.DataFrame:
    rates = pd.DataFrame(index=df.index)
    wsum = pd.Series(0.0, index=df.index)
    acc = {c: pd.Series(0.0, index=df.index) for c in COUNTING}
    for src, base in weights.items():
        have = df[f"{src}_PTS"].notna() & df[f"{src}_GP"].fillna(0).gt(0)
        rel = pd.Series(1.0, index=df.index) if src == "proj" else df[f"{src}_GP"].clip(upper=60) / 60
        w = (base * rel).where(have, 0.0).fillna(0.0)
        wsum += w
        for c in COUNTING:
            acc[c] += w * df[f"{src}_{c}"].fillna(0)
    for c in COUNTING:
        rates[c] = (acc[c] / wsum).where(wsum > 0)

    # Games: lean on the projection, pulled toward recent history (durability).
    hist = df[["ly_GP", "py_GP"]].mean(axis=1)
    gp = df["proj_GP"].where(df["proj_GP"].notna(), hist)
    gp = np.where(hist.notna() & df["proj_GP"].notna(), 0.6 * df["proj_GP"] + 0.4 * hist, gp)
    if list(weights) == ["ly"]:
        gp = df["ly_GP"]
    else:
        gp = gp - df["games_missed"]
    rates["GP"] = np.clip(gp, 0, SEASON_GAMES)
    return rates


def zscores(rates: pd.DataFrame, cats: list[str]) -> pd.DataFrame:
    """Z-scores against the top-ROSTERED pool, iterated so the pool is self-consistent."""
    valid = rates["PTS"].notna()
    pool = valid
    for _ in range(4):
        p = rates[pool]
        fg_avg = p["FGM"].sum() / p["FGA"].sum()
        ft_avg = p["FTM"].sum() / p["FTA"].sum()
        raw = pd.DataFrame(
            {
                "FG%": rates["FGM"] - fg_avg * rates["FGA"],
                "FT%": rates["FTM"] - ft_avg * rates["FTA"],
                **{c: rates[c] for c in ["3PTM", "PTS", "REB", "AST", "ST", "BLK"]},
                "TO": -rates["TO"],
            }
        )
        z = (raw - raw[pool].mean()) / raw[pool].std()
        zsum = z[cats].sum(axis=1).where(valid)
        pool = valid & zsum.rank(ascending=False).le(ROSTERED)
    z["zsum"] = zsum
    return z


def value_players(df: pd.DataFrame, weights: dict, cats: list[str]) -> pd.DataFrame:
    rates = blend_rates(df, weights)
    z = zscores(rates, cats)
    # Replacement level: the players just outside the rostered pool.
    ranked = z["zsum"].sort_values(ascending=False).dropna()
    repl = ranked.iloc[ROSTERED - 5 : ROSTERED + 5].mean()
    avail = rates["GP"] / SEASON_GAMES
    out = pd.concat([rates.add_prefix("pg_"), z.add_prefix("z_")], axis=1)
    out["value"] = (z["zsum"] - repl) * avail
    return out


def predict_keepers(df: pd.DataFrame, col: str) -> pd.Series:
    rostered = df[df.team_id > 0]
    rank_in_team = rostered.groupby("team_id")[col].rank(ascending=False, method="first")
    return (rank_in_team <= KEEPERS).reindex(df.index, fill_value=False)


def snake_order(slot_count: int, rounds: int) -> list[int]:
    order = []
    for r in range(rounds):
        seq = list(range(1, slot_count + 1))
        order += seq if r % 2 == 0 else seq[::-1]
    return order


def simulate_draft(df: pd.DataFrame, kept: pd.Series, my_slot: int) -> tuple[list, dict]:
    """Others draft by Yahoo preseason rank (what their draft room shows); you draft by your value.

    Returns ([(overall_pick, player_index, top_alternatives)] for your picks, {player_index: slot}
    for every pick).
    """
    pool = df.index[~kept & df["my_value"].notna()].tolist()
    by_rank = sorted(pool, key=lambda i: df.at[i, "preseason_rank"])
    available = set(pool)
    mine, all_picks = [], {}
    rounds = 17 - KEEPERS
    for n, slot in enumerate(snake_order(N_TEAMS, rounds), start=1):
        if slot == my_slot:
            ranked = sorted(available, key=lambda i: -df.at[i, "my_value"])
            pick = ranked[0]
            mine.append((n, pick, ranked[1:6]))
        else:
            pick = next(i for i in by_rank if i in available)
        all_picks[pick] = slot
        available.discard(pick)
    return mine, all_picks


def fmt(df: pd.DataFrame, cols: list[str]) -> str:
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 60)
    return df[cols].to_string(index=False, float_format=lambda x: f"{x:.2f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--punt", nargs="*", default=[], choices=CATS, help="categories to ignore")
    ap.add_argument("--slot", type=int, default=8, help="your draft slot (1-10)")
    ap.add_argument("--bubble", type=int, default=7, help="how many players to search over for the last keeper spots")
    ap.add_argument("--open-spots", type=int, default=4, help="keeper spots decided by search (rest are locks)")
    args = ap.parse_args()
    my_cats = [c for c in CATS if c not in args.punt]
    tag = f"punting {', '.join(args.punt)}" if args.punt else "all 9 cats"

    base = load_players()
    mv = value_players(base, WEIGHTS, my_cats)
    sv = value_players(base, WEIGHTS, CATS)  # how the rest of the league values players
    df = pd.concat([base, mv.drop(columns=["value"])], axis=1)
    df["my_value"] = mv["value"]
    df["std_value"] = sv["value"]
    df["rank"] = df["my_value"].rank(ascending=False, method="min")
    for m, w in METHODS.items():
        if m != "blend":
            df[f"rank_{m}"] = value_players(base, w, my_cats)["value"].rank(ascending=False, method="min")
    # Per-category rank among all valued players (1 = best in that category).
    for c in CATS:
        df[f"rk_{c}"] = df[f"z_{c}"].rank(ascending=False, method="min")

    # Others keep their top 13 by standard (all-category) value.
    others_kept = predict_keepers(df.assign(std_value=df["std_value"].where(df.team_id != MY_TEAM)), "std_value")
    others_kept &= df.team_id != MY_TEAM

    # Search over which of your bubble players to keep, simulating the draft for each choice.
    mine = df[df.team_id == MY_TEAM].sort_values("my_value", ascending=False)
    n_locks = KEEPERS - args.open_spots
    locks = mine.index[:n_locks].tolist()
    bubble = mine.index[n_locks : n_locks + args.bubble].tolist()
    results = []
    for combo in combinations(bubble, args.open_spots):
        keep = locks + list(combo)
        kept = others_kept.copy()
        kept.loc[keep] = True
        picks, all_picks = simulate_draft(df, kept, args.slot)
        team = keep + [p for _, p, _ in picks]
        results.append((df.loc[team, "my_value"].sum(), keep, picks, all_picks))
    results.sort(key=lambda r: -r[0])
    best_score, best_keep, best_picks, best_all = results[0]

    # ---------- output ----------
    OUT.mkdir(parents=True, exist_ok=True)
    suffix = ("_punt_" + "_".join(c.replace("%", "pct") for c in args.punt)) if args.punt else ""
    df.sort_values("rank").to_csv(OUT / f"player_values{suffix}.csv", index=False)

    cat_hdr = [f"{c}*" if c in args.punt else c for c in CATS]
    rk_rename = {f"rk_{c}": h for c, h in zip(CATS, cat_hdr)}
    show = ["decision", "name", "positions", "status", "GP", "value", "rank", "rk_LY", "rk_proj"] + cat_hdr

    m = mine.copy()
    m["decision"] = np.where(m.index.isin(best_keep), "KEEP", "cut")
    m = m.rename(columns=rk_rename | {"pg_GP": "GP", "my_value": "value", "rank_last_year": "rk_LY", "rank_projection": "rk_proj"})
    int_cols = ["rank", "rk_LY", "rk_proj", "GP"] + cat_hdr
    m[int_cols] = m[int_cols].round().astype("Int64")
    print(f"\n=== Your full roster ({tag}) — value and per-category ranks (1 = best of ~360 players; * = punted) ===")
    print(fmt(m, show))

    print(f"\n=== Simulated draft from slot {args.slot} (others draft by Yahoo preseason rank) ===")
    for n, p, alts in best_picks:
        r = df.loc[p]
        alt_txt = ", ".join(f"{df.at[a, 'name']} ({df.at[a, 'my_value']:.2f})" for a in alts[:3])
        print(f"  pick {n:>2}: {r['name']:<22} {r['positions']:<9} value {r['my_value']:.2f}   | also there: {alt_txt}")

    print("\n=== Best keeper sets (13 keepers + simulated draft, total value of 17) ===")
    for score, keep, picks, _ in results[:6]:
        diff = [df.at[i, "name"] for i in keep if i in bubble]
        drafted = ", ".join(df.at[p, "name"] for _, p, _ in picks)
        print(f"  {score:6.2f}  keep {', '.join(diff):<55} -> draft {drafted}")
    print(f"  (locks: {', '.join(df.loc[locks, 'name'])})")

    # Final team category strength vs the league (keepers + simulated picks for everyone).
    # Draft order for other teams is unknown, so their slots are assigned by team_id.
    kept = others_kept.copy()
    kept.loc[best_keep] = True
    other_ids = [t for t in range(1, N_TEAMS + 1) if t != MY_TEAM]
    slot_team = {args.slot: MY_TEAM} | dict(zip([s for s in range(1, N_TEAMS + 1) if s != args.slot], other_ids))
    final = df[kept | df.index.isin(list(best_all))].copy()
    for i, slot in best_all.items():
        final.at[i, "team_id"] = slot_team[slot]
    teams = pd.read_csv(LEAGUE / "teams.csv").set_index("team_id")["name"]
    final["fantasy_team"] = final["team_id"].map(teams)
    for c in CATS:
        final[f"w_{c}"] = final[f"z_{c}"] * final["pg_GP"] / SEASON_GAMES
    strength = final.groupby("fantasy_team")[[f"w_{c}" for c in CATS]].sum()
    strength.columns = cat_hdr
    ranks = strength.rank(ascending=False).astype(int)
    live = [h for c, h in zip(CATS, cat_hdr) if c not in args.punt]
    col = f"top-half cats (of {len(live)})"
    ranks[col] = (ranks[live] <= N_TEAMS // 2).sum(axis=1)
    ranks = ranks.sort_values(col, ascending=False)
    print("\n=== Category rank vs league after keepers (+ your simulated picks), 1 = best ===")
    print(ranks.to_string())

    print(f"\nwrote data/model/player_values{suffix}.csv")


if __name__ == "__main__":
    main()

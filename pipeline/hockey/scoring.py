"""League scoring (What the Puck, Yahoo 41313) and per-game fantasy points."""
import pandas as pd

SKATER = {"G": 6, "A": 4, "PM": 2, "PIM": 0.5, "PPP": 1, "SHG": 3, "SHA": 2, "SOG": 0.5,
          "FW": 0.2, "FL": -0.1, "HIT": 0.8, "BLK": 1.4}
GOALIE = {"W": 4, "GA": -3, "SV": 0.6, "SHO": 5}


def skater_fp(df: pd.DataFrame) -> pd.Series:
    return sum(df[c].fillna(0) * w for c, w in SKATER.items())


def goalie_fp(df: pd.DataFrame) -> pd.Series:
    return sum(df[c].fillna(0) * w for c, w in GOALIE.items())

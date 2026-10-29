# Fantasy Desk

Daily fantasy recommendations for all of the user's leagues, published as an encrypted phone web app.
Public repo robSanders818/fantasy-desk. Live at https://robsanders818.github.io/fantasy-desk/.

**This repo is the main home for the in-season models.** Edit models here, not in the old project folders:
- `pipeline/basketball/`: Yahoo 9-cat keeper league 13126. The old `~/Documents/Coding/Basketball` keeps draft-era work (draft app, keeper model, history) and is no longer where in-season models change.
- `pipeline/hockey/`: Yahoo H2H points league 41313. `~/Documents/Coding/Hockey` keeps the original research (backtest, notes in its CLAUDE.md).
- Soccer and football (Sleeper) come later, in `pipeline/soccer/` and `pipeline/football/`.

## Layout
```
web/                       React + Vite + Tailwind PWA; one tab per sport (Matchup, Moves, Roster, Rankings)
pipeline/
  crypt.py, cache.py, inputs.py    shared: encryption, per-sport caches, packing model inputs
  run_basketball.py, run_hockey.py one runner per sport -> pipeline/out/<sport>.json
  basketball/                      models (model.py, draft_engine.py, lineups.py, season.py, stream.py,
                                   records.py, rankings.py) + yahoo.py scraper; inputs.fdk = encrypted inputs
  hockey/                          models (model.py, league.py, scoring.py) + yahoo_hk.py + fetch_nhl.py;
                                   data/nhl/{skaters,goalies}.csv history committed (public NHL data)
  cache/<sport>.fdk                encrypted caches (daily team totals, weekly scores/pairs)
scripts/encrypt.py         bundles every sport's JSON into web/public/data/desk.fdk
.github/workflows/update.yml   ~9:00 and ~17:30 ET + on demand; one step per sport; then deploy.yml
```

## Rules
- **The repo is public.** Never commit league data unencrypted: rosters, team names and recommendations all go through `crypt.py`. Actions logs are public, so runners log only counts and timings. Runners send model subprocess output to /dev/null because tracebacks can name players.
- **Passphrase:** `$FD_PASSPHRASE` in CI, or the macOS Keychain item `fantasy-desk` locally. Never print it.
- **Secrets:** YAHOO_COOKIES (from `uv run --group local yahoo_session.py`, which reads Brave), FD_PASSPHRASE, and FD_REFRESH_TOKEN (fine-grained, Actions read/write on this repo only; it is put in the encrypted bundle for the page's Refresh button).
- **Bot commits land on main** (data and caches), so `git pull --rebase` before pushing. A local runner run also rewrites `pipeline/cache/*.fdk`. Either commit that or `git checkout` it before pulling.
- **Yahoo pacing:** about 2.5 s between requests; Yahoo returns 999 after about 180 fast ones.
  - Basketball runs use about 45 requests and hockey about 45.
  - Backfills run locally (`--backfill 99` for basketball; hockey's first run fetches every week's scoreboard once).
- **Run locally:** `uv run --group local pipeline/run_<sport>.py --local`, then `cp pipeline/out/<sport>.json web/sample/` and `cd web && npx vite`. In dev, the page loads the unencrypted samples.
- **The user decides publishing actions:** creating repos and enabling Pages were blocked for Claude, and the user ran them.

## Sport notes
- **Basketball:** Yahoo's matchup page loads its scores with JavaScript, so week-to-date totals are summed from each day's active lineup (`/{team}?date=D&stat1=S&stat2=D`).
  - IL slot or INJ status = out all week; "O" in an active slot = out today only.
  - Players whose game today has started are counted from their live stats, not simulated again.
- **Hockey:** the scoreboard `/?matchup_week=W` gives every team's live points and Yahoo's projection. Daily lineup pages give player points and the stat breakdown.
  - The Moves plan (user's choice, 2026-10-28) maximizes **this week's points** by cycling only the **rotatable** spots: players at or below waiver level, where keep value V ≤ 0.5. So more games means more points, at no season cost.
  - Each move reports the lineup games added (skater games / goalie starts, from the lineup simulation, not NHL schedule counts) and the points added.
  - The full-value planner (this week + rest-of-season change × weeks left, any drop) still ranks the free-agent board. It respects positions (no Util slot), and there are no protected players.
  - Players whose NHL game today has already started (schedule state) can't count today.
  - Weekly SD comes from finished weeks' scores. Playoff odds: 20,000 simulations, top 4, ties broken by PF.

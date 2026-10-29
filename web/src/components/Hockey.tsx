import { useMemo, useState } from "react";
import type { HockeyLeague, HkPlayer } from "../types";
import type { BballTab } from "./Basketball";
import { Badge, Card, Delta, ProbBar, SectionTitle, Sheet, StatusBadge, WinRing, pct, shortDay } from "./ui";

const pts = (v: number | null | undefined, d = 1) => (v == null ? "–" : v.toFixed(d));
const sgn = (v: number, d = 1) => `${v > 0 ? "+" : ""}${v.toFixed(d)}`;
const STAT_LABEL: Record<string, string> = {
  G: "Goals", A: "Assists", "+/-": "Plus/minus", PIM: "PIM", PPP: "PP points", SHG: "SH goals", SHA: "SH assists",
  SOG: "Shots", FW: "Faceoff wins", FL: "Faceoff losses", HIT: "Hits", BLK: "Blocks",
  W: "Goalie wins", GA: "Goals against", SV: "Saves", SHO: "Shutouts",
};

export function Hockey({ d, tab }: { d: HockeyLeague; tab: BballTab }) {
  if (tab === "moves") return <Moves d={d} />;
  if (tab === "roster") return <Roster d={d} />;
  if (tab === "league") return <Rankings d={d} />;
  return <Matchup d={d} />;
}

function Who({ p, sub }: { p: HkPlayer; sub?: string }) {
  return (
    <div className="min-w-0">
      <div className="flex items-center gap-1.5">
        <span className="truncate font-medium">{p.name}</span>
        <StatusBadge status={p.status} />
      </div>
      <div className="truncate text-xs text-muted">
        {p.team} · {p.pos}
        {sub ? ` · ${sub}` : ""}
      </div>
    </div>
  );
}

/* ---------------- Matchup ---------------- */

function Matchup({ d }: { d: HockeyLeague }) {
  const lead = d.live.me - d.live.opp;
  return (
    <>
      <Card className="p-4">
        <div className="text-xs text-muted">
          Week {d.week.number} · {shortDay(d.week.start)} – {shortDay(d.week.end)}
        </div>
        <div className="mt-0.5 text-lg font-semibold leading-tight">vs {d.opponent}</div>
        <div className="mt-4 flex items-center gap-5">
          <WinRing p={d.p_win} label="to win" />
          <div className="flex-1 space-y-2.5 text-sm">
            <Row k="Live score">
              <span className="font-semibold tabular-nums">
                {pts(d.live.me)} – {pts(d.live.opp)}
              </span>
            </Row>
            <Row k="Projected final">
              <span className="font-semibold tabular-nums">
                {pts(d.projected.me, 0)} – {pts(d.projected.opp, 0)}
              </span>
            </Row>
            {d.with_plan.p_win != null && (
              <Row k="With plan">
                <span className="font-semibold tabular-nums text-up">{pct(d.with_plan.p_win)}</span>
              </Row>
            )}
            <Row k="Adds left">
              <span className="font-semibold tabular-nums">
                {d.adds_left}
                <span className="font-normal text-muted"> of {d.adds_left + d.adds_used}</span>
              </span>
            </Row>
          </div>
        </div>
        <div className={`mt-3 text-xs ${lead >= 0 ? "text-up" : "text-down"}`}>
          {lead >= 0 ? "Up" : "Down"} {Math.abs(lead).toFixed(1)} so far
          {d.live.yahoo_proj_me != null && (
            <span className="text-muted">
              {" "}· Yahoo projects {pts(d.live.yahoo_proj_me, 0)} – {pts(d.live.yahoo_proj_opp, 0)}
            </span>
          )}
        </div>
      </Card>

      <TodayLineup d={d} />
      <StatBreakdown me={d.by_stat.me} them={d.by_stat.opp} themName={d.opponent} />
      <PlayerPoints d={d} />
      <VsEveryTeam d={d} />
    </>
  );
}

function Row({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-muted">{k}</span>
      {children}
    </div>
  );
}

function TodayLineup({ d }: { d: HockeyLeague }) {
  const l = d.lineup_today;
  const nothing = !l.starters.length && !l.bench.length;
  return (
    <>
      <SectionTitle aside={shortDay(d.week.sim_from)}>Today's lineup</SectionTitle>
      <Card className="divide-y divide-line">
        {nothing && (
          <div className="px-4 py-3 text-sm text-muted">
            {l.started.length ? "Everyone with a game today has already started." : "None of your players have a game today."}
          </div>
        )}
        {l.starters.map((s) => (
          <div key={s.id} className="flex items-center gap-3 px-4 py-2.5">
            <span className="w-8 shrink-0 text-center text-xs font-bold text-accent">{s.slot}</span>
            <div className="min-w-0 flex-1">
              <Who p={s} sub={s.slot === "G" ? `${pct(s.p_play)} to start` : undefined} />
            </div>
            <span className="text-sm font-semibold tabular-nums">{s.exp.toFixed(1)}</span>
          </div>
        ))}
        {l.bench.map((b) => (
          <div key={b.id} className="flex items-center gap-3 px-4 py-2.5 opacity-70">
            <span className="w-8 shrink-0 text-center text-xs font-bold text-muted">BN</span>
            <div className="min-w-0 flex-1">
              <Who p={b} sub="has a game, no open slot" />
            </div>
            <span className="text-sm tabular-nums text-muted">{b.exp.toFixed(1)}</span>
          </div>
        ))}
      </Card>
      {l.open_slots.length > 0 && l.starters.length > 0 && (
        <p className="px-1 pt-2 text-xs text-warn">
          Open today: {l.open_slots.join(", ")}. A free agent with a game tonight could fill {l.open_slots.length === 1 ? "it" : "them"}.
        </p>
      )}
      <p className="px-1 pt-2 text-xs text-muted">
        Expected points today. {l.no_game.length} with no game{l.started.length ? `, ${l.started.length} already playing` : ""}.
      </p>
    </>
  );
}

function StatBreakdown({ me, them, themName }: { me: Record<string, number>; them: Record<string, number>; themName: string }) {
  const keys = Object.keys(STAT_LABEL).filter((k) => Math.abs(me[k] ?? 0) + Math.abs(them[k] ?? 0) > 0);
  // One bar per stat from the center toward whoever got more fantasy points from it:
  // left and green = you, right and red = them. Length = the gap.
  const maxGap = Math.max(1, ...keys.map((k) => Math.abs((me[k] ?? 0) - (them[k] ?? 0))));
  const totalMe = keys.reduce((s, k) => s + (me[k] ?? 0), 0);
  const totalThem = keys.reduce((s, k) => s + (them[k] ?? 0), 0);
  return (
    <>
      <SectionTitle aside="fantasy points from each stat">Where the points come from</SectionTitle>
      <Card className="px-4 py-3">
        <div className="mb-1.5 grid grid-cols-[5.5rem_2.75rem_1fr_2.75rem] items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-muted">
          <div />
          <div className="text-right">You</div>
          <div className="flex justify-between px-1 normal-case tracking-normal">
            <span className="text-up">◀ you ahead</span>
            <span className="text-down">them ahead ▶</span>
          </div>
          <div className="truncate">{themName.split(" ")[0]}</div>
        </div>
        <div className="space-y-1">
          {keys.map((k) => {
            const a = me[k] ?? 0, b = them[k] ?? 0, gap = a - b;
            const w = `${(Math.abs(gap) / maxGap) * 50}%`;
            return (
              <div key={k} className="grid grid-cols-[5.5rem_2.75rem_1fr_2.75rem] items-center gap-2 text-xs tabular-nums">
                <div className="truncate text-muted">{STAT_LABEL[k]}</div>
                <div className={`text-right ${gap > 0.05 ? "font-semibold text-up" : ""}`}>{sgn(a)}</div>
                <div className="relative h-3">
                  <div className="absolute inset-y-0 left-1/2 w-px bg-line" />
                  {gap > 0.05 && <div className="absolute inset-y-0.5 right-1/2 rounded-l bg-up" style={{ width: w }} />}
                  {gap < -0.05 && <div className="absolute inset-y-0.5 left-1/2 rounded-r bg-down" style={{ width: w }} />}
                </div>
                <div className={gap < -0.05 ? "font-semibold text-down" : ""}>{sgn(b)}</div>
              </div>
            );
          })}
        </div>
        <div className="mt-2 grid grid-cols-[5.5rem_2.75rem_1fr_2.75rem] items-center gap-2 border-t border-line pt-2 text-xs font-semibold tabular-nums">
          <div>Total</div>
          <div className={`text-right ${totalMe > totalThem ? "text-up" : ""}`}>{totalMe.toFixed(1)}</div>
          <div className={`text-center text-[11px] ${totalMe >= totalThem ? "text-up" : "text-down"}`}>
            {totalMe >= totalThem ? "you +" : "them +"}
            {Math.abs(totalMe - totalThem).toFixed(1)}
          </div>
          <div className={totalThem > totalMe ? "text-down" : ""}>{totalThem.toFixed(1)}</div>
        </div>
      </Card>
    </>
  );
}

function PlayerPoints({ d }: { d: HockeyLeague }) {
  const [side, setSide] = useState<"me" | "opp">("me");
  const rows = d.player_pts[side].filter((r) => r.pts || r.bench_pts);
  return (
    <>
      <SectionTitle
        aside={
          <div className="flex rounded-lg bg-line/60 p-0.5 text-xs font-medium">
            {(["me", "opp"] as const).map((k) => (
              <button key={k} onClick={() => setSide(k)} className={`rounded-md px-2.5 py-0.5 ${side === k ? "bg-surface text-fg shadow-sm" : "text-muted"}`}>
                {k === "me" ? "You" : "Them"}
              </button>
            ))}
          </div>
        }
      >
        Player points this week
      </SectionTitle>
      <Card className="divide-y divide-line">
        {rows.length === 0 && <div className="px-4 py-3 text-sm text-muted">No points yet this week.</div>}
        {rows.map((r) => (
          <div key={r.name} className="flex items-center gap-3 px-4 py-2">
            <span className="min-w-0 flex-1 truncate text-sm">{r.name}</span>
            {r.bench_pts > 0 && <span className="text-[11px] text-warn">+{r.bench_pts.toFixed(1)} on bench</span>}
            <span className="w-12 text-right text-sm font-semibold tabular-nums">{r.pts.toFixed(1)}</span>
          </div>
        ))}
      </Card>
    </>
  );
}

function VsEveryTeam({ d }: { d: HockeyLeague }) {
  const v = d.this_week_vs;
  const [open, setOpen] = useState<number | null>(null);
  const sel = v.rows.find((r) => r.team_id === open);
  const wins = v.rows.filter((r) => r.result === "W").length;
  return (
    <>
      {sel && (
        <Sheet onClose={() => setOpen(null)}>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-xs text-muted">This week so far (live)</div>
              <h3 className="mt-0.5 truncate text-lg font-semibold">You vs {sel.team}</h3>
            </div>
            <div className={`shrink-0 text-2xl font-bold tabular-nums ${sel.result === "W" ? "text-up" : sel.result === "L" ? "text-down" : "text-warn"}`}>
              {v.me_pts.toFixed(1)}–{sel.pts.toFixed(1)}
            </div>
          </div>
          <StatBreakdown me={v.me_by_stat} them={sel.by_stat} themName={sel.team} />
        </Sheet>
      )}
      <SectionTitle aside={<span>total <b className="tabular-nums text-fg">{wins}–{v.rows.length - wins}</b></span>}>This week vs every team</SectionTitle>
      <Card className="divide-y divide-line">
        {v.rows.map((r) => (
          <button key={r.team_id} onClick={() => setOpen(r.team_id)} className="flex w-full items-center gap-3 px-4 py-2.5 text-left active:bg-line/40">
            <span className="min-w-0 flex-1 truncate text-sm">{r.team}</span>
            {r.opponent && <Badge tone="accent">opponent</Badge>}
            <span className="w-12 text-right text-sm tabular-nums text-muted">{r.pts.toFixed(1)}</span>
            <span className={`w-5 text-right text-sm font-bold ${r.result === "W" ? "text-up" : r.result === "L" ? "text-down" : "text-warn"}`}>{r.result}</span>
            <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0 text-muted" fill="none" stroke="currentColor" strokeWidth={2}>
              <path d="m9 6 6 6-6 6" />
            </svg>
          </button>
        ))}
      </Card>
      <p className="px-1 pt-2 text-xs text-muted">Your {v.me_pts.toFixed(1)} so far vs each team's this week. Tap a team for the stat-by-stat comparison.</p>
    </>
  );
}

/* ---------------- Moves (games-max plan + free agents) ---------------- */

type FaSort = "total" | "week_pts" | "games";

function Moves({ d }: { d: HockeyLeague }) {
  const [sort, setSort] = useState<FaSort>("total");
  const fas = useMemo(() => [...d.free_agents].sort((a, b) => b[sort] - a[sort]), [d.free_agents, sort]);
  const rot = d.roster.filter((r) => r.rotatable);
  const pl = d.plans?.week ?? null;
  return (
    <>
      <SectionTitle aside={`${d.adds_left} of ${d.adds_left + d.adds_used} adds left`}>Streaming plan</SectionTitle>
      <p className="px-1 pb-2 text-xs text-muted">
        Most points this week, by cycling your rotatable spots to fit more games into the lineup. Never drops a player worth
        keeping, so it doesn't cost you for the season.
      </p>

      {!pl ? (
        <Card className="p-4 text-sm text-muted">No move adds enough points to spend an add{!rot.length ? " (no rotatable spots)" : ""}.</Card>
      ) : (
        <>
          <Card className="grid grid-cols-3 divide-x divide-line p-0 text-center">
            <Stat label="Lineup games" from={pl.games.before.toFixed(1)} to={pl.games.after.toFixed(1)} up={pl.games.after > pl.games.before} />
            <Stat label="Win chance" from={pct(d.p_win)} to={pct(pl.p_win ?? d.p_win)} up={(pl.p_win ?? 0) > d.p_win} />
            <Stat label="Season pts/wk" from={d.ros.before.toFixed(0)} to={pl.ros_after.toFixed(0)} up={pl.ros_after >= d.ros.before} />
          </Card>
          <p className="px-1 pt-1.5 text-[11px] text-muted">
            Goalie starts {pl.games.goalies_before.toFixed(1)} → {pl.games.goalies_after.toFixed(1)} · projected {pl.points.before.toFixed(0)} →{" "}
            {pl.points.after.toFixed(0)} pts this week
          </p>

          <ol className="mt-3 space-y-2.5">
            {[...pl.steps].sort((a, b) => a.day.localeCompare(b.day)).map((s, i) => (
              <li key={i}>
                <Card className="p-4">
                  <div className="flex items-center justify-between gap-2">
                    <Badge tone="accent">{shortDay(s.day)}</Badge>
                    <div className="flex flex-wrap justify-end gap-1.5">
                      <Delta v={s.games_added}>{sgn(s.games_added)} games</Delta>
                      <Delta v={s.week_pts}>{sgn(s.week_pts)} pts</Delta>
                    </div>
                  </div>
                  <div className="mt-3 space-y-1.5 text-[15px]">
                    <div className="flex items-baseline gap-2">
                      <span className="w-4 font-bold text-up">+</span>
                      <span className="font-semibold">{s.add.name}</span>
                      <span className="text-xs text-muted">{s.add.team} · {s.add.pos}</span>
                    </div>
                    <div className="flex items-baseline gap-2">
                      <span className="w-4 font-bold text-down">−</span>
                      <span>{s.drop.name}</span>
                      <span className="text-xs text-muted">{s.drop.team} · {s.drop.pos}</span>
                    </div>
                  </div>
                  <div className="mt-2.5 text-xs text-muted">
                    {Math.abs(s.skater_games) >= 0.05 && <>skater games {sgn(s.skater_games)}</>}
                    {Math.abs(s.skater_games) >= 0.05 && Math.abs(s.goalie_starts) >= 0.05 && " · "}
                    {Math.abs(s.goalie_starts) >= 0.05 && <>goalie starts {sgn(s.goalie_starts)}</>}
                  </div>
                </Card>
              </li>
            ))}
          </ol>
        </>
      )}
      {rot.length > 0 && (
        <p className="px-1 pt-3 text-xs text-muted">
          <span className="font-semibold text-fg">Rotatable spots:</span> {rot.map((r) => r.name).join(", ")}. Each is at or below
          what's on waivers, so cycling them for extra games costs little for the season.
        </p>
      )}
      <p className="px-1 pt-2 text-xs text-muted">
        Games = games that actually land in your lineup (an open slot that day; goalies only when they start), not just games on
        the NHL schedule. Permanent upgrades worth more over the season show up below, sorted by Value.
      </p>

      <SectionTitle
        aside={
          <div className="flex rounded-lg bg-line/60 p-0.5 text-xs font-medium">
            {(
              [
                ["total", "Value"],
                ["week_pts", "Week"],
                ["games", "Games"],
              ] as [FaSort, string][]
            ).map(([k, label]) => (
              <button key={k} onClick={() => setSort(k)} className={`rounded-md px-2 py-0.5 ${sort === k ? "bg-surface text-fg shadow-sm" : "text-muted"}`}>
                {label}
              </button>
            ))}
          </div>
        }
      >
        All free agents
      </SectionTitle>
      <Card className="divide-y divide-line">
        {fas.map((f) => (
          <div key={f.id} className="flex items-center gap-3 px-4 py-3">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <span className="truncate font-semibold">{f.name}</span>
                <StatusBadge status={f.status} />
                {f.avail.startsWith("W") && <Badge tone="warn">waivers</Badge>}
              </div>
              <div className="mt-0.5 truncate text-xs text-muted">
                {f.team} · {f.pos} · {f.exp_fp.toFixed(1)}/g · {f.games} games · for {f.drop.name}
              </div>
            </div>
            <div className="flex shrink-0 flex-col items-end gap-1">
              <Delta v={f.total}>{sgn(f.total, 0)}</Delta>
              <span className="text-[11px] tabular-nums text-muted">week {sgn(f.week_pts)}</span>
            </div>
          </div>
        ))}
      </Card>
      <p className="px-1 pt-2 text-xs text-muted">
        Value = this week's points gained plus the change in your weekly points for the rest of the season. A good player
        dropped is assumed gone for good; positions are respected (no Util slot).
      </p>
    </>
  );
}

/* ---------------- Roster ---------------- */

function Stat({ label, from, to, up }: { label: string; from: string; to: string; up: boolean }) {
  return (
    <div className="px-2 py-3">
      <div className="text-[11px] text-muted">{label}</div>
      <div className="mt-1 text-sm font-semibold tabular-nums">
        <span className="text-muted">{from}</span> → <span className={up ? "text-up" : "text-down"}>{to}</span>
      </div>
    </div>
  );
}

function Roster({ d }: { d: HockeyLeague }) {
  const max = Math.max(...d.roster.map((r) => r.exp_fp), 1);
  return (
    <>
      <div className="px-1 pb-2 pt-1 text-xs text-muted">
        Expected fantasy points per team game (includes chance he plays; goalies: chance he starts).
      </div>
      <Card className="divide-y divide-line">
        {d.roster.map((r) => (
          <div key={r.id} className="flex items-center gap-3 px-4 py-2.5">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <span className="truncate font-medium">{r.name}</span>
                <StatusBadge status={r.slot.startsWith("IR") ? r.slot : r.status} />
                {r.rotatable && <Badge>rotatable</Badge>}
              </div>
              <div className="mt-0.5 text-[11px] text-muted">
                {r.team} · {r.pos} · {r.games_left} games left · {r.week_pts.toFixed(1)} pts this week
                {r.goalie ? ` · starts ${pct(r.p_play)}` : ""}
              </div>
              <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-line">
                <div className="h-full rounded-full bg-accent" style={{ width: `${(r.exp_fp / max) * 100}%` }} />
              </div>
            </div>
            <div className="w-12 shrink-0 text-right">
              <div className="text-sm font-semibold tabular-nums">{r.exp_fp.toFixed(1)}</div>
              <div className="text-[10px] text-muted">pts/g</div>
            </div>
          </div>
        ))}
      </Card>
      <p className="px-1 pt-2 text-xs text-muted">
        Rotatable = no better than what's on waivers ({Object.entries(d.replacement).map(([k, v]) => `${k} ${v.toFixed(1)}`).join(", ")} pts/g), so a fine spot to stream.
      </p>
    </>
  );
}

/* ---------------- Rankings ---------------- */

const rec = (r: number[]) => `${r[0]}–${r[1]}${r[2] ? `–${r[2]}` : ""}`;

function Rankings({ d }: { d: HockeyLeague }) {
  const [view, setView] = useState<"power" | "season" | "playoffs">("power");
  return (
    <>
      <div className="mb-2 flex rounded-lg bg-line/60 p-0.5 text-sm font-medium">
        {(
          [
            ["power", "Power"],
            ["season", "Season"],
            ["playoffs", "Playoff odds"],
          ] as const
        ).map(([k, label]) => (
          <button key={k} onClick={() => setView(k)} className={`flex-1 rounded-md py-1.5 ${view === k ? "bg-surface text-fg shadow-sm" : "text-muted"}`}>
            {label}
          </button>
        ))}
      </div>
      {view === "power" && <Power d={d} />}
      {view === "season" && <Season d={d} />}
      {view === "playoffs" && <Playoffs d={d} />}
    </>
  );
}

function Power({ d }: { d: HockeyLeague }) {
  return (
    <>
      <div className="px-1 pb-2 pt-1 text-xs text-muted">Projected weekly points for the rest of the season, and the chance to beat a typical opponent.</div>
      <Card className="divide-y divide-line">
        {d.rankings.map((r) => {
          const mine = r.team_id === d.my_team_id;
          return (
            <div key={r.team_id} className={`flex items-center gap-3 px-4 py-3 ${mine ? "bg-accent/5" : ""}`}>
              <div className={`w-6 text-center text-lg font-bold tabular-nums ${mine ? "text-accent" : "text-muted"}`}>{r.rank}</div>
              <div className="min-w-0 flex-1">
                <div className={`truncate font-semibold ${mine ? "text-accent" : ""}`}>{r.team}</div>
                <div className="mt-1.5">
                  <ProbBar p={r.win_pct} />
                </div>
              </div>
              <div className="w-16 shrink-0 text-right">
                <div className="text-lg font-bold tabular-nums">{pct(r.win_pct)}</div>
                <div className="text-[11px] tabular-nums text-muted">{r.proj_week.toFixed(0)} / wk</div>
              </div>
            </div>
          );
        })}
      </Card>
    </>
  );
}

type SeasonSort = "allplay_pct" | "pf" | "pa" | "luck" | "record";

function Season({ d }: { d: HockeyLeague }) {
  const [sort, setSort] = useState<SeasonSort>("allplay_pct");
  const val = (r: HockeyLeague["season"][number]) =>
    sort === "record" ? r.record[0] + r.record[2] / 2 + r.pf / 1e5 : sort === "pa" ? -r.pa : r[sort];
  const rows = [...d.season].sort((a, b) => val(b) - val(a));
  const head = (k: SeasonSort, label: string) => (
    <th onClick={() => setSort(k)} className={`cursor-pointer whitespace-nowrap px-2 py-2 text-right font-semibold ${sort === k ? "text-accent" : "text-muted"}`}>
      {label}
    </th>
  );
  return (
    <>
      <div className="px-1 pb-2 pt-1 text-xs text-muted">Finished weeks only. Tap a column to sort.</div>
      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs tabular-nums">
            <thead className="border-b border-line">
              <tr>
                <th className="sticky left-0 z-[1] bg-surface px-3 py-2 text-left font-semibold text-muted">Team</th>
                {head("record", "W-L")}
                {head("pf", "PF")}
                {head("pa", "PA")}
                {head("allplay_pct", "All-play")}
                {head("luck", "Luck")}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.map((r) => {
                const mine = r.team_id === d.my_team_id;
                return (
                  <tr key={r.team_id} className={mine ? "bg-accent/5" : ""}>
                    <td className={`sticky left-0 z-[1] max-w-[9rem] truncate px-3 py-2 font-medium ${mine ? "bg-[color-mix(in_oklab,var(--surface),var(--accent)_5%)] text-accent" : "bg-surface"}`}>{r.team}</td>
                    <td className="whitespace-nowrap px-2 py-2 text-right">{rec(r.record)}</td>
                    <td className="px-2 py-2 text-right">{r.pf.toFixed(0)}</td>
                    <td className="px-2 py-2 text-right">{r.pa.toFixed(0)}</td>
                    <td className="whitespace-nowrap px-2 py-2 text-right">
                      {rec(r.allplay)}
                      <div className="text-[10px] text-muted">{pct(r.allplay_pct)}</div>
                    </td>
                    <td className={`px-2 py-2 text-right font-semibold ${r.luck > 0.25 ? "text-up" : r.luck < -0.25 ? "text-down" : "text-muted"}`}>{sgn(r.luck)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
      <p className="px-1 pt-2 text-xs text-muted">
        All-play = record if you'd played every team every week. Luck = actual wins minus the wins your all-play rate would
        have earned: positive means your opponents happened to score less.
      </p>
    </>
  );
}

function Playoffs({ d }: { d: HockeyLeague }) {
  const rows = [...d.season].sort((a, b) => b.playoff_odds - a.playoff_odds);
  return (
    <>
      <div className="px-1 pb-2 pt-1 text-xs text-muted">
        Top 4 make the playoffs. 20,000 simulations of the rest of the season on the real schedule, starting from this week's
        live score.
      </div>
      <Card className="divide-y divide-line">
        {rows.map((r) => {
          const mine = r.team_id === d.my_team_id;
          return (
            <div key={r.team_id} className={`flex items-center gap-3 px-4 py-3 ${mine ? "bg-accent/5" : ""}`}>
              <div className="min-w-0 flex-1">
                <div className={`truncate font-semibold ${mine ? "text-accent" : ""}`}>{r.team}</div>
                <div className="mt-0.5 text-[11px] text-muted">
                  {rec(r.record)} now · projected {r.proj_wins.toFixed(1)} wins · 1st seed {pct(r.first_seed)}
                </div>
                <div className="mt-1.5">
                  <ProbBar p={r.playoff_odds} />
                </div>
              </div>
              <div className="w-14 shrink-0 text-right text-lg font-bold tabular-nums">{pct(r.playoff_odds)}</div>
            </div>
          );
        })}
      </Card>
    </>
  );
}

import { useMemo, useState } from "react";
import type { CategoryLeague, FreeAgent, RankRow, SeasonRow } from "../types";
import { Badge, Card, Delta, ProbBar, SectionTitle, Sheet, StatusBadge, WinRing, pct, shortDay, signed, signedPts } from "./ui";

const fmtCat = (c: string, v: number | undefined) =>
  v == null ? "–" : c.includes("%") ? v.toFixed(3).replace(/^0/, "") : Math.round(v).toString();

export type BballTab = "matchup" | "moves" | "roster" | "league";

export function Basketball({ d, tab }: { d: CategoryLeague; tab: BballTab }) {
  if (tab === "moves")
    return (
      <>
        <Moves d={d} />
        <SectionTitle>All free agents</SectionTitle>
        <Wire d={d} />
      </>
    );
  if (tab === "roster") return <Roster d={d} />;
  if (tab === "league") return <Rankings d={d} />;
  return <Matchup d={d} />;
}

function Alerts({ d }: { d: CategoryLeague }) {
  if (!d.alerts?.length) return null;
  return (
    <div className="mb-3 space-y-2">
      {d.alerts.map((a, i) => (
        <div key={i} className={`rounded-xl px-3.5 py-2.5 text-sm ring-1 ${a.kind === "info" ? "bg-surface ring-line text-muted" : "bg-warn/10 ring-warn/30"}`}>
          <span className="mr-1.5">{a.kind === "il" ? "🩹" : a.kind === "activate" ? "✅" : "ℹ️"}</span>
          {a.text}
        </div>
      ))}
    </div>
  );
}

function Matchup({ d }: { d: CategoryLeague }) {
  const lead = d.banked.me
    ? d.cats.reduce(
        (acc, c) => {
          const a = d.banked.me![c], b = d.banked.opp![c];
          const better = d.lower_is_better.includes(c) ? a < b : a > b;
          if (a === b) acc[2]++;
          else if (better) acc[0]++;
          else acc[1]++;
          return acc;
        },
        [0, 0, 0],
      )
    : null;
  return (
    <>
      <Alerts d={d} />
      <Card className="p-4">
        <div className="text-xs text-muted">
          {d.week.number ? `Week ${d.week.number} · ` : ""}
          {shortDay(d.week.start)} – {shortDay(d.week.end)}
        </div>
        <div className="mt-0.5 text-lg font-semibold leading-tight">vs {d.opponent}</div>
        <div className="mt-4 flex items-center gap-5">
          <WinRing p={d.current.p_win} label="to win" />
          <div className="flex-1 space-y-2.5 text-sm">
            {lead && (
              <Row k="Score so far">
                <span className="font-semibold tabular-nums">
                  {lead[0]}–{lead[1]}
                  {lead[2] ? `–${lead[2]}` : ""}
                </span>
              </Row>
            )}
            <Row k="Expected cats">
              <span className="font-semibold tabular-nums">{d.current.exp_cats.toFixed(1)}</span>
            </Row>
            <Row k="With plan">
              <span className="font-semibold tabular-nums text-up">{pct(d.with_plan.p_win)}</span>
            </Row>
            <Row k="Adds left">
              <span className="font-semibold tabular-nums">
                {d.adds_left}
                {d.adds_used != null && <span className="font-normal text-muted"> of {d.adds_left + d.adds_used}</span>}
              </span>
            </Row>
          </div>
        </div>
      </Card>

      <SectionTitle aside="so far · projected · P(win)">Categories</SectionTitle>
      <Card className="divide-y divide-line">
        {d.cats.map((c) => {
          const punt = d.punt.includes(c);
          return (
            <div key={c} className={`grid grid-cols-[3.25rem_1fr_1fr_4.5rem] items-center gap-2 px-4 py-2.5 ${punt ? "opacity-55" : ""}`}>
              <div className="text-sm font-semibold">
                {c}
                {punt && <div className="text-[10px] font-normal uppercase tracking-wide text-muted">punt</div>}
              </div>
              <div className="text-xs tabular-nums text-muted">
                {fmtCat(c, d.banked.me?.[c])} <span className="opacity-60">v</span> {fmtCat(c, d.banked.opp?.[c])}
              </div>
              <div className="text-xs tabular-nums">
                {fmtCat(c, d.projected.me[c])} <span className="text-muted">v</span> {fmtCat(c, d.projected.opp[c])}
              </div>
              <div className="space-y-1 text-right">
                <div className="text-sm font-semibold tabular-nums">{pct(d.current.p_cat[c])}</div>
                <ProbBar p={d.current.p_cat[c]} faded={punt} />
              </div>
            </div>
          );
        })}
      </Card>
      <p className="px-1 pt-2 text-xs text-muted">
        Projected = week-to-date stats plus a simulation of the remaining days with daily lineups.
      </p>
      <VsEveryTeam d={d} />
      <CategoryRanks d={d} />
    </>
  );
}

const rec = (r: number[]) => `${r[0]}–${r[1]}${r[2] ? `–${r[2]}` : ""}`;

type Pt = { team_id: number; team: string; v: number; me: boolean; opp: boolean };

/** Every team's value per category, this week (live) or season totals. */
function categoryPoints(d: CategoryLeague, view: "week" | "season"): Record<string, Pt[]> | null {
  const me = d.my_team_id;
  const oppId = d.this_week_vs?.rows.find((r) => r.opponent)?.team_id;
  const teams: { team_id: number; team: string; cats: Record<string, number> }[] = [];
  if (view === "week") {
    const v = d.this_week_vs;
    if (!v?.me || v.rows.some((r) => !r.cats)) return null;
    teams.push({ team_id: me ?? -1, team: d.team, cats: v.me });
    v.rows.forEach((r) => teams.push({ team_id: r.team_id, team: r.team, cats: r.cats! }));
  } else {
    if (!d.season?.rows.length) return null;
    d.season.rows.forEach((r) => teams.push({ team_id: r.team_id, team: r.team, cats: r.totals }));
  }
  const out: Record<string, Pt[]> = {};
  for (const c of d.cats) {
    const low = d.lower_is_better.includes(c);
    out[c] = teams
      .map((t) => ({ team_id: t.team_id, team: t.team, v: t.cats[c], me: t.team_id === me, opp: t.team_id === oppId }))
      .sort((a, b) => (low ? a.v - b.v : b.v - a.v));
  }
  return out;
}

const ordinalShort = (n: number) => {
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
};

function CategoryRanks({ d }: { d: CategoryLeague }) {
  const [view, setView] = useState<"week" | "season">("week");
  const [open, setOpen] = useState<string | null>(null);
  const data = categoryPoints(d, view) ?? categoryPoints(d, "season");
  if (!data) return null;
  const n = data[d.cats[0]].length;
  const rankOf = (c: string) => data[c].findIndex((p) => p.me) + 1;
  const avg = d.cats.filter((c) => !d.punt.includes(c)).reduce((s, c) => s + rankOf(c), 0) / Math.max(1, d.cats.filter((c) => !d.punt.includes(c)).length);
  return (
    <>
      {open && (
        <Sheet onClose={() => setOpen(null)}>
          <CategorySheet d={d} c={open} pts={data[open]} view={view} />
        </Sheet>
      )}
      <SectionTitle
        aside={
          <div className="flex rounded-lg bg-line/60 p-0.5 text-xs font-medium">
            {(
              [
                ["week", "This week"],
                ["season", "Season"],
              ] as const
            ).map(([k, label]) => (
              <button key={k} onClick={() => setView(k)} className={`rounded-md px-2.5 py-0.5 ${view === k ? "bg-surface text-fg shadow-sm" : "text-muted"}`}>
                {label}
              </button>
            ))}
          </div>
        }
      >
        Category ranks
      </SectionTitle>
      <Card className="px-4 pb-2 pt-3">
        <div className="mb-1 flex items-center justify-between text-[11px] text-muted">
          <span className="flex items-center gap-3">
            <span className="flex items-center gap-1"><i className="inline-block h-2.5 w-2.5 rounded-full bg-accent" /> you</span>
            <span className="flex items-center gap-1"><i className="inline-block h-2 w-2 rounded-full bg-down" /> opponent</span>
            <span className="flex items-center gap-1"><i className="inline-block h-1.5 w-1.5 rounded-full bg-muted/60" /> others</span>
          </span>
          <span>better →</span>
        </div>
        <div className="divide-y divide-line">
          {d.cats.map((c) => {
            const pts = data[c];
            const vals = pts.map((p) => p.v);
            const lo = Math.min(...vals), hi = Math.max(...vals);
            const low = d.lower_is_better.includes(c);
            // position: 0 = worst, 1 = best
            const pos = (v: number) => (hi === lo ? 0.5 : low ? (hi - v) / (hi - lo) : (v - lo) / (hi - lo));
            const r = rankOf(c);
            const punt = d.punt.includes(c);
            const tone = r <= 3 ? "text-up" : r > n - 3 ? "text-down" : "text-fg";
            const me = pts.find((p) => p.me)!;
            return (
              <button key={c} onClick={() => setOpen(c)} className={`grid w-full grid-cols-[3.25rem_1fr_3rem] items-center gap-3 py-2.5 text-left outline-none active:opacity-70 ${punt ? "opacity-45" : ""}`}>
                <div>
                  <div className="text-sm font-semibold">{c}</div>
                  <div className="text-[10px] tabular-nums text-muted">{fmtCat(c, me.v)}</div>
                </div>
                <div className="relative h-5">
                  <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-line" />
                  <div className="absolute top-1/2 h-1 -translate-y-1/2 rounded-full bg-gradient-to-r from-down/25 via-transparent to-up/25" style={{ left: 0, right: 0 }} />
                  {[...pts].sort((a, b) => Number(a.me || a.opp) - Number(b.me || b.opp)).map((p) => (
                    <span
                      key={p.team_id}
                      className={`absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full ${
                        p.me ? "z-[2] h-3.5 w-3.5 bg-accent ring-2 ring-surface" : p.opp ? "z-[1] h-2.5 w-2.5 bg-down ring-2 ring-surface" : "h-2 w-2 bg-muted/50"
                      }`}
                      style={{ left: `${4 + pos(p.v) * 92}%` }}
                    />
                  ))}
                </div>
                <div className={`text-right text-sm font-bold tabular-nums ${punt ? "text-muted" : tone}`}>{ordinalShort(r)}</div>
              </button>
            );
          })}
        </div>
      </Card>
      <p className="px-1 pt-2 text-xs text-muted">
        Average rank in your categories: <span className="font-semibold text-fg">{avg.toFixed(1)}</span> of {n}
        {view === "week" ? " (live this week)" : " (season totals)"}. Punted categories are dimmed. Tap a category for the full list.
      </p>
    </>
  );
}

function CategorySheet({ d, c, pts, view }: { d: CategoryLeague; c: string; pts: Pt[]; view: "week" | "season" }) {
  const low = d.lower_is_better.includes(c);
  const vals = pts.map((p) => p.v);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const frac = (v: number) => (hi === lo ? 1 : 0.15 + 0.85 * (low ? (hi - v) / (hi - lo) : (v - lo) / (hi - lo)));
  return (
    <>
      <div className="text-xs text-muted">{view === "week" ? "This week so far (live)" : "Season totals"}{low ? " · lower is better" : ""}</div>
      <h3 className="mt-0.5 text-lg font-semibold">{c} ranking</h3>
      <div className="mt-3 space-y-1.5">
        {pts.map((p, i) => (
          <div key={p.team_id} className="grid grid-cols-[1.25rem_7.5rem_1fr_3.25rem] items-center gap-2 text-sm">
            <span className={`text-right text-xs tabular-nums ${p.me ? "font-bold text-accent" : "text-muted"}`}>{i + 1}</span>
            <span className={`truncate ${p.me ? "font-semibold text-accent" : p.opp ? "font-medium text-down" : ""}`}>{p.team}</span>
            <div className="h-2.5 overflow-hidden rounded-full bg-line/60">
              <div className={`h-full rounded-full ${p.me ? "bg-accent" : p.opp ? "bg-down" : "bg-muted/50"}`} style={{ width: `${frac(p.v) * 100}%` }} />
            </div>
            <span className="text-right text-xs tabular-nums">{fmtCat(c, p.v)}</span>
          </div>
        ))}
      </div>
    </>
  );
}

function VsEveryTeam({ d }: { d: CategoryLeague }) {
  const v = d.this_week_vs;
  const [open, setOpen] = useState<number | null>(null);
  if (!v?.rows.length) return null;
  const sel = v.rows.find((r) => r.team_id === open);
  return (
    <>
      {sel && v.me && sel.cats && (
        <Sheet onClose={() => setOpen(null)}>
          <HeadToHead d={d} me={v.me} them={sel.cats} team={sel.team} record={sel.record} opponent={sel.opponent} />
        </Sheet>
      )}
      <SectionTitle aside={<span>total <b className="text-fg tabular-nums">{rec(v.total)}</b></span>}>This week vs every team</SectionTitle>
      <Card className="divide-y divide-line">
        {v.rows.map((r) => {
          const tone = r.record[0] > r.record[1] ? "text-up" : r.record[0] < r.record[1] ? "text-down" : "text-warn";
          return (
            <button key={r.team_id} onClick={() => setOpen(r.team_id)}
              className="flex w-full items-center gap-3 px-4 py-2.5 text-left active:bg-line/40">
              <span className="min-w-0 flex-1 truncate text-sm">{r.team}</span>
              {r.opponent && <Badge tone="accent">opponent</Badge>}
              <span className={`w-14 text-right text-sm font-semibold tabular-nums ${tone}`}>{rec(r.record)}</span>
              <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0 text-muted" fill="none" stroke="currentColor" strokeWidth={2}>
                <path d="m9 6 6 6-6 6" />
              </svg>
            </button>
          );
        })}
      </Card>
      <p className="px-1 pt-2 text-xs text-muted">
        Your categories so far this week (live) against each team's, as if you'd played everyone. Tap a team to compare.
      </p>
    </>
  );
}

function HeadToHead({ d, me, them, team, record, opponent }: {
  d: CategoryLeague; me: Record<string, number>; them: Record<string, number>; team: string; record: number[]; opponent: boolean;
}) {
  const tone = record[0] > record[1] ? "text-up" : record[0] < record[1] ? "text-down" : "text-warn";
  return (
    <>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-xs text-muted">This week so far (live){opponent ? " · your opponent" : ""}</div>
          <h3 className="mt-0.5 truncate text-lg font-semibold">You vs {team}</h3>
        </div>
        <div className={`shrink-0 text-2xl font-bold tabular-nums ${tone}`}>{rec(record)}</div>
      </div>
      <div className="mt-4 grid grid-cols-[1fr_auto_1fr] gap-x-3 px-1 pb-1 text-[11px] font-semibold uppercase tracking-wide text-muted">
        <div className="text-right">You</div>
        <div className="w-12 text-center">Cat</div>
        <div>{team.split(" ")[0]}</div>
      </div>
      <div className="divide-y divide-line rounded-xl ring-1 ring-line">
        {d.cats.map((c) => {
          const low = d.lower_is_better.includes(c);
          const a = me[c], b = them[c];
          const win = Math.abs(a - b) < 1e-9 ? 0 : (low ? a < b : a > b) ? 1 : -1;
          const punt = d.punt.includes(c);
          return (
            <div key={c} className={`grid grid-cols-[1fr_auto_1fr] items-center gap-x-3 px-3 py-2.5 tabular-nums ${punt ? "opacity-55" : ""}`}>
              <div className={`text-right text-[15px] ${win === 1 ? "font-bold text-up" : "text-fg"}`}>{fmtCat(c, a)}</div>
              <div className="w-12 text-center text-xs font-semibold text-muted">
                {c}
                {punt && <div className="text-[9px] font-normal uppercase">punt</div>}
              </div>
              <div className={`text-[15px] ${win === -1 ? "font-bold text-down" : "text-fg"}`}>{fmtCat(c, b)}</div>
            </div>
          );
        })}
      </div>
      <p className="mt-3 text-xs text-muted">Active-lineup stats only, Mon through today. Ties shown in neither color.</p>
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

function Moves({ d }: { d: CategoryLeague }) {
  return (
    <>
      <Alerts d={d} />
      <Card className="p-4">
        <div className="flex items-end justify-between">
          <div>
            <div className="text-xs text-muted">If you make every move</div>
            <div className="mt-1 text-3xl font-bold tabular-nums">
              {pct(d.current.p_win)} <span className="text-muted">→</span> <span className="text-up">{pct(d.with_plan.p_win)}</span>
            </div>
          </div>
          <div className="text-right text-xs text-muted">
            <div>Season avg weekly win</div>
            <div className="mt-1 text-base font-semibold tabular-nums text-fg">
              {d.ros.before.toFixed(1)}% → {d.ros.after.toFixed(1)}%
            </div>
          </div>
        </div>
      </Card>

      <SectionTitle aside={`${d.adds_left} adds left this week`}>Recommended moves, in calendar order</SectionTitle>
      {d.plan.length === 0 && <Card className="p-4 text-sm text-muted">No move helps enough to spend an add.</Card>}
      <ol className="space-y-2.5">
        {[...d.plan].sort((a, b) => a.day.localeCompare(b.day)).map((s, i) => (
          <li key={i}>
            <Card className="p-4">
              <div className="flex items-center justify-between">
                <Badge tone="accent">{shortDay(s.day)}</Badge>
                <div className="flex gap-1.5">
                  <Delta v={s.d_win}>{signedPts(s.d_win)} win</Delta>
                  <Delta v={s.d_cats}>{signed(s.d_cats)} cats</Delta>
                </div>
              </div>
              <div className="mt-3 space-y-1.5 text-[15px]">
                <div className="flex items-baseline gap-2">
                  <span className="w-4 font-bold text-up">+</span>
                  <span className="font-semibold">{s.add.name}</span>
                  <span className="text-xs text-muted">
                    {s.add.team} · {s.add.pos}
                  </span>
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="w-4 font-bold text-down">−</span>
                  <span>{s.drop ? s.drop.name : "open roster spot"}</span>
                  {s.drop && (
                    <span className="text-xs text-muted">
                      {s.drop.team} · {s.drop.pos}
                    </span>
                  )}
                </div>
              </div>
            </Card>
          </li>
        ))}
      </ol>
    </>
  );
}

type SortKey = "d_win" | "d_ros" | "games";

function Wire({ d }: { d: CategoryLeague }) {
  const [sort, setSort] = useState<SortKey>("d_win");
  const [open, setOpen] = useState<number | null>(null);
  const rows = useMemo(() => [...d.free_agents].sort((a, b) => b[sort] - a[sort]), [d.free_agents, sort]);
  return (
    <>
      <div className="flex items-center justify-between px-1 pb-2">
        <div className="text-xs text-muted">Best single move for each</div>
        <div className="flex rounded-lg bg-line/60 p-0.5 text-xs font-medium">
          {(
            [
              ["d_win", "Win %"],
              ["d_ros", "Season"],
              ["games", "Games"],
            ] as [SortKey, string][]
          ).map(([k, label]) => (
            <button
              key={k}
              onClick={() => setSort(k)}
              className={`rounded-md px-2.5 py-1 ${sort === k ? "bg-surface text-fg shadow-sm" : "text-muted"}`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <Card className="divide-y divide-line">
        {rows.map((f) => (
          <FaRow key={f.id} f={f} d={d} open={open === f.id} toggle={() => setOpen(open === f.id ? null : f.id)} />
        ))}
      </Card>
      <p className="px-1 pt-2 text-xs text-muted">
        Win % = change in this week's chance to win. Season = change in your average weekly win % if he replaces the dropped
        player for good.
      </p>
    </>
  );
}

function FaRow({ f, d, open, toggle }: { f: FreeAgent; d: CategoryLeague; open: boolean; toggle: () => void }) {
  return (
    <div>
      <button onClick={toggle} className="flex w-full items-center gap-3 px-4 py-3 text-left active:bg-line/40">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="truncate font-semibold">{f.name}</span>
            <StatusBadge status={f.status} />
            {f.avail !== "FA" && <Badge tone="warn">waivers</Badge>}
          </div>
          <div className="mt-0.5 truncate text-xs text-muted">
            {f.team} · {f.pos} · {f.games} games · for {f.drop ? f.drop.name : "open spot"}
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <Delta v={f.d_win}>{signedPts(f.d_win)}</Delta>
          <span className={`text-[11px] tabular-nums ${f.d_ros >= 0 ? "text-up" : "text-muted"}`}>
            season {signed(f.d_ros, 1)}
          </span>
        </div>
      </button>
      {open && (
        <div className="grid grid-cols-3 gap-x-4 gap-y-2 bg-bg/40 px-4 pb-3 pt-1 text-xs">
          {d.cats.map((c) => (
            <div key={c} className={`flex justify-between ${d.punt.includes(c) ? "opacity-50" : ""}`}>
              <span className="text-muted">{c}</span>
              <span className={`tabular-nums ${f.d_cat[c] > 0.002 ? "text-up" : f.d_cat[c] < -0.002 ? "text-down" : "text-muted"}`}>
                {signedPts(f.d_cat[c], 0)}
              </span>
            </div>
          ))}
          <div className="col-span-3 pt-1 text-muted">
            Add {shortDay(f.day)} · expected cats {signed(f.d_cats)}
          </div>
        </div>
      )}
    </div>
  );
}

function Roster({ d }: { d: CategoryLeague }) {
  const rows = [...d.roster].sort((a, b) => b.ros_value - a.ros_value);
  const max = Math.max(...rows.map((r) => r.ros_value), 1);
  return (
    <>
      <div className="px-1 pb-2 pt-1 text-xs text-muted">
        Value = how much your average weekly win % falls if he's replaced by a waiver-level player.
      </div>
      <Card className="divide-y divide-line">
        {rows.map((r) => (
          <div key={r.id} className="flex items-center gap-3 px-4 py-2.5">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <span className="truncate font-medium">{r.name}</span>
                <StatusBadge status={r.slot === "IL" ? "IL" : r.status} />
                {r.droppable && <Badge>drop pool</Badge>}
              </div>
              <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-line">
                <div className="h-full rounded-full bg-accent" style={{ width: `${(Math.max(r.ros_value, 0) / max) * 100}%` }} />
              </div>
            </div>
            <div className="w-14 shrink-0 text-right">
              <div className="text-sm font-semibold tabular-nums">{r.ros_value.toFixed(1)}</div>
              <div className="text-[11px] tabular-nums text-muted">{r.week_starts.toFixed(1)} starts</div>
            </div>
          </div>
        ))}
      </Card>
    </>
  );
}

function Rankings({ d }: { d: CategoryLeague }) {
  const [view, setView] = useState<"power" | "season">("power");
  return (
    <>
      <div className="mb-2 flex rounded-lg bg-line/60 p-0.5 text-sm font-medium">
        {(
          [
            ["power", "Power rankings"],
            ["season", "Season so far"],
          ] as const
        ).map(([k, label]) => (
          <button key={k} onClick={() => setView(k)}
            className={`flex-1 rounded-md py-1.5 ${view === k ? "bg-surface text-fg shadow-sm" : "text-muted"}`}>
            {label}
          </button>
        ))}
      </div>
      {view === "power" ? <Power d={d} /> : <Season d={d} />}
    </>
  );
}

function Power({ d }: { d: CategoryLeague }) {
  const [open, setOpen] = useState<number | null>(d.my_team_id ?? null);
  const rows = d.rankings ?? [];
  if (!rows.length) return <Card className="p-4 text-sm text-muted">Rankings will appear after the next update.</Card>;
  const me = d.my_team_id;
  return (
    <>
      <div className="px-1 pb-2 pt-1 text-xs text-muted">
        Projected chance to win a typical week against the rest of the league, from current rosters and injuries.
      </div>
      <Card className="divide-y divide-line">
        {rows.map((r) => (
          <RankItem key={r.team_id} r={r} d={d} mine={r.team_id === me} open={open === r.team_id}
            toggle={() => setOpen(open === r.team_id ? null : r.team_id)} />
        ))}
      </Card>
      <p className="px-1 pt-2 text-xs text-muted">Record and standing are from Yahoo. Tap a team for its category strengths.</p>
    </>
  );
}

function RankItem({ r, d, mine, open, toggle }: { r: RankRow; d: CategoryLeague; mine: boolean; open: boolean; toggle: () => void }) {
  const vsMe = d.my_team_id != null ? r.vs[String(d.my_team_id)] : undefined;
  return (
    <div className={mine ? "bg-accent/5" : ""}>
      <button onClick={toggle} className="flex w-full items-center gap-3 px-4 py-3 text-left active:bg-line/40">
        <div className={`w-6 text-center text-lg font-bold tabular-nums ${mine ? "text-accent" : "text-muted"}`}>{r.rank}</div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className={`truncate font-semibold ${mine ? "text-accent" : ""}`}>{r.team}</span>
          </div>
          <div className="mt-0.5 text-xs text-muted">
            {r.record}
            {r.standing ? ` · ${ordinal(r.standing)} in standings` : ""}
          </div>
          <div className="mt-1.5">
            <ProbBar p={r.proj_week} />
          </div>
        </div>
        <div className="w-12 shrink-0 text-right text-lg font-bold tabular-nums">{pct(r.proj_week)}</div>
      </button>
      {open && (
        <div className="px-4 pb-3">
          <div className="grid grid-cols-3 gap-x-4 gap-y-2 text-xs">
            {d.cats.map((c) => (
              <div key={c} className="flex items-center justify-between gap-2">
                <span className="text-muted">{c}</span>
                <span className={`font-semibold tabular-nums ${r.p_cat[c] >= 0.6 ? "text-up" : r.p_cat[c] <= 0.4 ? "text-down" : ""}`}>
                  {pct(r.p_cat[c])}
                </span>
              </div>
            ))}
          </div>
          {!mine && vsMe != null && (
            <div className="mt-2.5 text-xs text-muted">
              Head to head: they'd beat you <span className="font-semibold text-fg">{pct(vsMe)}</span> of the time.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ordinal(n: number) {
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

type SeasonSort = "allplay" | "cat" | string;

function Season({ d }: { d: CategoryLeague }) {
  const [sort, setSort] = useState<SeasonSort>("allplay");
  const se = d.season;
  if (!se?.rows.length) return <Card className="p-4 text-sm text-muted">Season records will appear after the next update.</Card>;
  const me = d.my_team_id;
  const frac = (r: number[]) => (r[0] + r[2] / 2) / Math.max(r[0] + r[1] + r[2], 1);
  const val = (r: SeasonRow) =>
    sort === "allplay" ? frac(r.allplay) : sort === "cat" ? frac(r.cat_record) : d.lower_is_better.includes(sort) ? -r.totals[sort] : r.totals[sort];
  const rows = [...se.rows].sort((a, b) => val(b) - val(a));
  const weeks = se.weeks.length;
  const head = (k: SeasonSort, label: string, cls = "") => (
    <th onClick={() => setSort(k)} className={`cursor-pointer whitespace-nowrap px-2 py-2 text-right font-semibold ${sort === k ? "text-accent" : "text-muted"} ${cls}`}>
      {label}
    </th>
  );
  return (
    <>
      <div className="px-1 pb-2 pt-1 text-xs text-muted">
        {weeks} week{weeks === 1 ? "" : "s"}, live through today. Tap a column to sort.
      </div>
      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs tabular-nums">
            <thead className="border-b border-line">
              <tr>
                <th className="sticky left-0 z-[1] bg-surface px-3 py-2 text-left font-semibold text-muted">Team</th>
                {head("allplay", "All-play")}
                {head("cat", "Cat rec")}
                {d.cats.map((c) => head(c, c))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.map((r) => {
                const mine = r.team_id === me;
                return (
                  <tr key={r.team_id} className={mine ? "bg-accent/5" : ""}>
                    <td className={`sticky left-0 z-[1] max-w-[9rem] truncate px-3 py-2 font-medium ${mine ? "bg-[color-mix(in_oklab,var(--surface),var(--accent)_5%)] text-accent" : "bg-surface"}`}>
                      {r.team}
                      <div className="text-[10px] font-normal text-muted">{rec(r.matchups)} in matchups</div>
                    </td>
                    <td className="whitespace-nowrap px-2 py-2 text-right">
                      {rec(r.allplay)}
                      <div className="text-[10px] text-muted">{pct(frac(r.allplay))}</div>
                    </td>
                    <td className="whitespace-nowrap px-2 py-2 text-right">{rec(r.cat_record)}</td>
                    {d.cats.map((c) => (
                      <td key={c} className={`px-2 py-2 text-right ${d.punt.includes(c) && mine ? "text-muted" : ""}`}>
                        {c.includes("%") ? r.totals[c].toFixed(3).replace(/^0/, "") : r.totals[c]}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
      <p className="px-1 pt-2 text-xs text-muted">
        All-play = categories won against every team, every week. Cat rec = categories won against your actual opponents.
        Totals count active-lineup stats only, like Yahoo.
      </p>
    </>
  );
}

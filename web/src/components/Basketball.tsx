import { useMemo, useState } from "react";
import type { CategoryLeague, FreeAgent } from "../types";
import { Badge, Card, Delta, ProbBar, SectionTitle, StatusBadge, WinRing, pct, shortDay, signed, signedPts } from "./ui";

const fmtCat = (c: string, v: number | undefined) =>
  v == null ? "–" : c.includes("%") ? v.toFixed(3).replace(/^0/, "") : Math.round(v).toString();

export type BballTab = "matchup" | "moves" | "wire" | "roster";

export function Basketball({ d, tab }: { d: CategoryLeague; tab: BballTab }) {
  if (tab === "moves") return <Moves d={d} />;
  if (tab === "wire") return <Wire d={d} />;
  if (tab === "roster") return <Roster d={d} />;
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
      <div className="flex items-center justify-between px-1 pb-2 pt-1">
        <div className="text-xs text-muted">Best single move for each free agent</div>
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

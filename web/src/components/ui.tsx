import type { ReactNode } from "react";

export const pct = (p: number, digits = 0) => `${(p * 100).toFixed(digits)}%`;

/** Signed percentage-point change, e.g. +2.6 pts */
export function signedPts(d: number, digits = 1) {
  const v = d * 100;
  const s = v.toFixed(digits);
  return `${v > 0 ? "+" : ""}${s === "-0.0" ? "0.0" : s}`;
}

export function signed(v: number, digits = 2) {
  const s = v.toFixed(digits);
  return `${v > 0 ? "+" : ""}${s}`;
}

export function shortDay(iso: string) {
  const d = new Date(`${iso}T12:00:00`);
  return d.toLocaleDateString(undefined, { weekday: "short", month: "numeric", day: "numeric" });
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-2xl bg-surface ring-1 ring-line shadow-sm ${className}`}>{children}</section>
  );
}

export function SectionTitle({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between px-1 pb-2 pt-5">
      <h2 className="text-[13px] font-semibold uppercase tracking-wider text-muted">{children}</h2>
      {aside && <div className="text-xs text-muted">{aside}</div>}
    </div>
  );
}

/** Coloured change chip: green up, red down, grey ~0. `value` is already formatted. */
export function Delta({ v, children, eps = 0.0005 }: { v: number; children: ReactNode; eps?: number }) {
  const tone =
    v > eps ? "bg-up/15 text-up" : v < -eps ? "bg-down/15 text-down" : "bg-line/60 text-muted";
  return (
    <span className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-xs font-semibold tabular-nums ${tone}`}>
      {children}
    </span>
  );
}

export function Badge({ children, tone = "muted" }: { children: ReactNode; tone?: "muted" | "warn" | "down" | "accent" }) {
  const cls = {
    muted: "bg-line/70 text-muted",
    warn: "bg-warn/15 text-warn",
    down: "bg-down/15 text-down",
    accent: "bg-accent/15 text-accent",
  }[tone];
  return <span className={`rounded px-1.5 py-px text-[10px] font-bold uppercase tracking-wide ${cls}`}>{children}</span>;
}

export function StatusBadge({ status }: { status: string }) {
  if (!status) return null;
  const tone = ["O", "IL", "INJ", "OFS", "SUSP", "NA"].includes(status) ? "down" : "warn";
  return <Badge tone={tone}>{status}</Badge>;
}

/** Win-probability ring. */
export function WinRing({ p, size = 112, label }: { p: number; size?: number; label?: string }) {
  const r = (size - 12) / 2;
  const c = 2 * Math.PI * r;
  const tone = p >= 0.6 ? "stroke-up" : p >= 0.4 ? "stroke-warn" : "stroke-down";
  return (
    <div className="relative grid place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={10} className="stroke-line" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          strokeWidth={10}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - p)}
          className={`${tone} transition-[stroke-dashoffset] duration-700`}
        />
      </svg>
      <div className="absolute text-center">
        <div className="text-3xl font-bold tabular-nums leading-none">{pct(p)}</div>
        {label && <div className="mt-1 text-[11px] text-muted">{label}</div>}
      </div>
    </div>
  );
}

/** Horizontal probability bar (0..1), coloured by how safe the category is. */
export function ProbBar({ p, faded = false }: { p: number; faded?: boolean }) {
  const tone = p >= 0.65 ? "bg-up" : p >= 0.35 ? "bg-warn" : "bg-down";
  return (
    <div className={`h-1.5 w-full overflow-hidden rounded-full bg-line ${faded ? "opacity-40" : ""}`}>
      <div className={`h-full rounded-full ${tone} transition-[width] duration-700`} style={{ width: pct(p) }} />
    </div>
  );
}

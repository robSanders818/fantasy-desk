import { useCallback, useEffect, useState } from "react";
import { decryptBundle, rememberPassphrase, savedPassphrase } from "./crypto";
import type { Bundle } from "./types";
import { Basketball, type BballTab } from "./components/Basketball";
import { useRefresh, type RefreshState } from "./refresh";
import { Sheet } from "./components/ui";

type League = "basketball" | "hockey" | "soccer" | "football";
const LEAGUES: { id: League; label: string; icon: string }[] = [
  { id: "basketball", label: "Basketball", icon: "🏀" },
  { id: "hockey", label: "Hockey", icon: "🏒" },
  { id: "soccer", label: "Soccer", icon: "⚽" },
  { id: "football", label: "Football", icon: "🏈" },
];
const TABS: { id: BballTab; label: string; icon: string }[] = [
  { id: "matchup", label: "Matchup", icon: "M3 13h4v8H3zM10 8h4v13h-4zM17 3h4v18h-4z" },
  { id: "moves", label: "Moves", icon: "M12 5v14M5 12h14" },
  { id: "roster", label: "Roster", icon: "M16 11a4 4 0 1 0-8 0M4 21a8 8 0 0 1 16 0" },
  { id: "league", label: "Rankings", icon: "M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0zM17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3" },
];

const DATA_URL = `${import.meta.env.BASE_URL}data/desk.fdk`;

async function loadBundle(passphrase: string | null): Promise<Bundle> {
  if (import.meta.env.DEV) {
    const r = await fetch(`${import.meta.env.BASE_URL}sample-bundle.json`);
    if (r.ok) return r.json();
  }
  if (!passphrase) throw new Error("locked");
  const r = await fetch(DATA_URL, { cache: "no-store" });
  if (!r.ok) throw new Error("No data published yet");
  return decryptBundle(await r.arrayBuffer(), passphrase);
}

function useLocal<T extends string>(key: string, initial: T) {
  const [v, setV] = useState<T>(() => {
    try {
      return (localStorage.getItem(key) as T) || initial;
    } catch {
      return initial;
    }
  });
  const set = (x: T) => {
    setV(x);
    try {
      localStorage.setItem(key, x);
    } catch {
      /* ignore */
    }
  };
  return [v, set] as const;
}

export default function App() {
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [state, setState] = useState<"loading" | "locked" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [league, setLeague] = useLocal<League>("fd:league", "basketball");
  const [tabRaw, setTab] = useLocal<BballTab>("fd:tab", "matchup");
  const tab: BballTab = (["matchup", "moves", "roster", "league"] as string[]).includes(tabRaw) ? tabRaw : "moves";

  const unlock = useCallback(async (p: string | null, remember = true, silent = false) => {
    if (!silent) setState("loading");
    try {
      const b = await loadBundle(p);
      if (p && remember) rememberPassphrase(p);
      setBundle(b);
      setState("ready");
    } catch (e) {
      const msg = (e as Error).message;
      if (msg === "Wrong passphrase") rememberPassphrase(null);
      setError(msg === "locked" ? "" : msg);
      setState(msg === "locked" || msg === "Wrong passphrase" ? "locked" : "error");
    }
  }, []);

  useEffect(() => {
    unlock(savedPassphrase());
  }, [unlock]);

  const reload = useCallback(() => unlock(savedPassphrase(), false, true), [unlock]);
  const refresh = useRefresh(bundle?.refresh, reload);
  const [confirming, setConfirming] = useState(false);

  if (state === "locked") return <Lock error={error} onUnlock={(p) => unlock(p)} />;
  if (state === "loading") return <Splash text="Unlocking…" />;
  if (state === "error" || !bundle) return <Splash text={error || "Something went wrong"} />;

  const bb = bundle.leagues.basketball;
  const updated = new Date(bundle.generated_at);
  const stale = Date.now() - updated.getTime() > 14 * 3600_000;

  return (
    <div className="mx-auto min-h-dvh max-w-xl pb-[calc(env(safe-area-inset-bottom)+5.5rem)]">
      <header className="sticky top-0 z-10 border-b border-line bg-bg/85 px-4 pb-2 pt-[calc(env(safe-area-inset-top)+0.75rem)] backdrop-blur-xl">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold tracking-tight">Fantasy Desk</h1>
          <div className="flex items-center gap-2">
            <span className={`text-xs ${stale ? "font-semibold text-warn" : "text-muted"}`}>
              {updated.toLocaleString(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" })}
            </span>
            <RefreshButton state={refresh.state} onClick={() => setConfirming(true)} />
          </div>
        </div>
        <RefreshBanner state={refresh.state} />
        <nav className="no-scrollbar -mx-4 mt-3 flex gap-2 overflow-x-auto px-4">
          {LEAGUES.map((l) => {
            const live = !!bundle.leagues[l.id as "basketball"];
            const on = league === l.id;
            return (
              <button
                key={l.id}
                onClick={() => setLeague(l.id)}
                className={`flex shrink-0 items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
                  on ? "bg-fg text-bg" : "bg-surface text-fg ring-1 ring-line"
                } ${live ? "" : "opacity-50"}`}
              >
                <span>{l.icon}</span>
                {l.label}
              </button>
            );
          })}
        </nav>
      </header>

      <main className="px-4 pt-3">
        {league === "basketball" && bb ? (
          <Basketball d={bb} tab={tab} />
        ) : (
          <div className="mt-16 text-center text-muted">
            <div className="text-4xl">{LEAGUES.find((l) => l.id === league)?.icon}</div>
            <p className="mt-3 text-sm">Coming soon. Basketball is wired up first.</p>
          </div>
        )}
      </main>

      {confirming && (
        <ConfirmSheet
          hasToken={!!bundle.refresh}
          onCancel={() => setConfirming(false)}
          onConfirm={() => {
            setConfirming(false);
            refresh.start();
          }}
        />
      )}

      {league === "basketball" && bb && (
        <nav className="fixed inset-x-0 bottom-0 z-10 border-t border-line bg-bg/85 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl">
          <div className="mx-auto grid max-w-xl grid-cols-4">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => {
                  setTab(t.id);
                  window.scrollTo({ top: 0 });
                }}
                className={`flex flex-col items-center gap-1 py-2.5 text-[11px] font-medium ${tab === t.id ? "text-accent" : "text-muted"}`}
              >
                <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                  <path d={t.icon} />
                </svg>
                {t.label}
              </button>
            ))}
          </div>
        </nav>
      )}
    </div>
  );
}

function RefreshButton({ state, onClick }: { state: RefreshState; onClick: () => void }) {
  const busy = state.phase === "starting" || state.phase === "running" || state.phase === "publishing";
  return (
    <button
      onClick={onClick}
      disabled={busy}
      aria-label="Refresh now"
      className="grid h-9 w-9 place-items-center rounded-full bg-surface ring-1 ring-line active:opacity-70 disabled:opacity-60"
    >
      <svg viewBox="0 0 24 24" className={`h-[18px] w-[18px] ${busy ? "animate-spin" : ""}`} fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 12a9 9 0 1 1-2.64-6.36M21 4v5h-5" />
      </svg>
    </button>
  );
}

function ConfirmSheet({ hasToken, onCancel, onConfirm }: { hasToken: boolean; onCancel: () => void; onConfirm: () => void }) {
  return (
    <Sheet onClose={onCancel}>
      <h3 className="text-lg font-semibold">Refresh now?</h3>
      <p className="mt-1.5 text-sm text-muted">
        {hasToken
          ? "Pulls the latest rosters, live scores and free agents from Yahoo and reruns the projections. Takes about 3 minutes; the page updates itself when it's done."
          : "Opens the update job on GitHub, where you can tap “Run workflow”."}
      </p>
      <div className="mt-5 grid grid-cols-2 gap-3">
        <button onClick={onCancel} className="rounded-xl bg-line/70 py-3 font-semibold active:opacity-70">
          Cancel
        </button>
        <button onClick={onConfirm} className="rounded-xl bg-accent py-3 font-semibold text-bg active:opacity-80">
          Refresh
        </button>
      </div>
    </Sheet>
  );
}

function RefreshBanner({ state }: { state: RefreshState }) {
  const [, tick] = useState(0);
  useEffect(() => {
    if (state.phase !== "running") return;
    const id = window.setInterval(() => tick((x) => x + 1), 1000);
    return () => window.clearInterval(id);
  }, [state.phase]);
  if (state.phase === "idle") return null;
  let text = "";
  let tone = "text-muted";
  if (state.phase === "starting") text = "Starting the update…";
  if (state.phase === "running") {
    const s = Math.floor((Date.now() - state.since) / 1000);
    text = `Updating from Yahoo… ${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")} · usually about 3 min`;
  }
  if (state.phase === "publishing") text = "Publishing the new numbers…";
  if (state.phase === "failed") {
    text = state.message;
    tone = "text-down";
  }
  const busy = state.phase !== "failed";
  return (
    <div className="mt-2">
      {busy && (
        <div className="h-0.5 overflow-hidden rounded-full bg-line">
          <div className="h-full w-1/3 animate-[slide_1.4s_ease-in-out_infinite] rounded-full bg-accent" />
        </div>
      )}
      <div className={`mt-1.5 text-xs ${tone}`}>
        {text}
        {state.phase === "failed" && state.url && (
          <a href={state.url} target="_blank" rel="noreferrer" className="ml-1 underline">
            Details
          </a>
        )}
      </div>
    </div>
  );
}

function Splash({ text }: { text: string }) {
  return <div className="grid min-h-dvh place-items-center px-6 text-center text-sm text-muted">{text}</div>;
}

function Lock({ error, onUnlock }: { error: string; onUnlock: (p: string) => void }) {
  const [p, setP] = useState("");
  return (
    <div className="grid min-h-dvh place-items-center px-6">
      <form
        className="w-full max-w-xs"
        onSubmit={(e) => {
          e.preventDefault();
          if (p) onUnlock(p);
        }}
      >
        <div className="mx-auto mb-5 flex h-16 w-16 items-end justify-center gap-1 rounded-2xl bg-surface p-3 ring-1 ring-line">
          {[0.45, 0.7, 1].map((h) => (
            <div key={h} className="w-3 rounded-sm bg-accent" style={{ height: `${h * 100}%` }} />
          ))}
        </div>
        <h1 className="text-center text-xl font-bold">Fantasy Desk</h1>
        <p className="mt-1 text-center text-sm text-muted">Enter your passphrase to unlock this device.</p>
        <input
          type="password"
          autoComplete="current-password"
          value={p}
          onChange={(e) => setP(e.target.value)}
          className="mt-5 w-full rounded-xl bg-surface px-4 py-3 text-base ring-1 ring-line outline-none focus:ring-2 focus:ring-accent"
          placeholder="Passphrase"
          autoFocus
        />
        {error && <p className="mt-2 text-center text-sm text-down">{error}</p>}
        <button className="mt-3 w-full rounded-xl bg-accent py-3 font-semibold text-bg active:opacity-80">Unlock</button>
      </form>
    </div>
  );
}

import { useCallback, useEffect, useState } from "react";
import { decryptBundle, rememberPassphrase, savedPassphrase } from "./crypto";
import type { Bundle } from "./types";
import { Basketball, type BballTab } from "./components/Basketball";

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
  { id: "wire", label: "Free agents", icon: "M4 6h16M4 12h16M4 18h10" },
  { id: "roster", label: "Roster", icon: "M16 11a4 4 0 1 0-8 0M4 21a8 8 0 0 1 16 0" },
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
  const [tab, setTab] = useLocal<BballTab>("fd:tab", "matchup");

  const unlock = useCallback(async (p: string | null, remember = true) => {
    setState("loading");
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

  if (state === "locked") return <Lock error={error} onUnlock={(p) => unlock(p)} />;
  if (state === "loading") return <Splash text="Unlocking…" />;
  if (state === "error" || !bundle) return <Splash text={error || "Something went wrong"} />;

  const bb = bundle.leagues.basketball;
  const updated = new Date(bundle.generated_at);

  return (
    <div className="mx-auto min-h-dvh max-w-xl pb-[calc(env(safe-area-inset-bottom)+5.5rem)]">
      <header className="sticky top-0 z-10 border-b border-line bg-bg/85 px-4 pb-2 pt-[calc(env(safe-area-inset-top)+0.75rem)] backdrop-blur-xl">
        <div className="flex items-baseline justify-between">
          <h1 className="text-xl font-bold tracking-tight">Fantasy Desk</h1>
          <span className="text-xs text-muted">
            Updated {updated.toLocaleString(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" })}
          </span>
        </div>
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

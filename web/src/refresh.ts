// "Refresh now": start the update workflow on GitHub, follow the run, then reload the data.
import { useCallback, useEffect, useRef, useState } from "react";
import type { Bundle } from "./types";

export type RefreshState =
  | { phase: "idle" }
  | { phase: "starting" }
  | { phase: "running"; since: number; url?: string }
  | { phase: "publishing" }
  | { phase: "failed"; message: string; url?: string };

const API = "https://api.github.com";
export const ACTIONS_URL = "https://github.com/robSanders818/fantasy-desk/actions/workflows/update.yml";

interface Run {
  id: number;
  status: string;
  conclusion: string | null;
  created_at: string;
  html_url: string;
}

export function useRefresh(cfg: Bundle["refresh"], reload: () => Promise<void>) {
  const [state, setState] = useState<RefreshState>({ phase: "idle" });
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const gh = useCallback(
    (path: string, init?: RequestInit) =>
      fetch(`${API}/repos/${cfg!.repo}${path}`, {
        ...init,
        headers: {
          Authorization: `Bearer ${cfg!.token}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          ...(init?.headers || {}),
        },
      }),
    [cfg],
  );

  const start = useCallback(async () => {
    if (!cfg) {
      window.open(ACTIONS_URL, "_blank");
      return;
    }
    setState({ phase: "starting" });
    const t0 = Date.now();
    const r = await gh(`/actions/workflows/${cfg.workflow}/dispatches`, {
      method: "POST",
      body: JSON.stringify({ ref: "main" }),
    }).catch(() => null);
    if (!r || r.status !== 204) {
      setState({ phase: "failed", message: r?.status === 401 || r?.status === 403 ? "Refresh token rejected" : "Couldn't start the update", url: ACTIONS_URL });
      return;
    }
    setState({ phase: "running", since: t0 });

    const poll = async () => {
      const res = await gh(`/actions/workflows/${cfg.workflow}/runs?event=workflow_dispatch&per_page=5`).catch(() => null);
      const runs: Run[] = res && res.ok ? (await res.json()).workflow_runs : [];
      const run = runs.find((x) => Date.parse(x.created_at) >= t0 - 60_000);
      if (run?.status === "completed") {
        if (run.conclusion !== "success") {
          setState({ phase: "failed", message: "The update failed (Yahoo session may need refreshing)", url: run.html_url });
          return;
        }
        setState({ phase: "publishing" });
        // The run includes the Pages deploy; give the CDN a moment before re-reading the data.
        timer.current = window.setTimeout(async () => {
          await reload();
          setState({ phase: "idle" });
        }, 15_000);
        return;
      }
      setState({ phase: "running", since: t0, url: run?.html_url });
      timer.current = window.setTimeout(poll, 8_000);
    };
    timer.current = window.setTimeout(poll, 6_000);
  }, [cfg, gh, reload]);

  return { state, start };
}

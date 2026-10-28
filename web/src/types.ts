// Shape of the decrypted data bundle (written by the pipeline; see scripts/encrypt.py).

export interface Player {
  id: number;
  name: string;
  team: string;
  pos: string;
  status: string;
}

export type CatMap = Record<string, number>;

export interface Outcome {
  p_win: number;
  exp_cats: number;
  p_cat: CatMap;
  starts: number;
}

export interface PlanStep {
  day: string;
  add: Player;
  drop: Player | null;
  d_win: number;
  d_cats: number;
  p_win_after: number;
}

export interface FreeAgent extends Player {
  avail: string; // "FA" or a waiver-clear date
  games: number;
  day: string;
  drop: Player | null;
  d_win: number;
  d_cats: number;
  d_cat: CatMap;
  d_ros: number; // change in avg weekly win%, rest of season (points)
}

export interface RosterPlayer extends Player {
  slot: string;
  ros_value: number; // avg weekly win% lost if dropped (points)
  week_starts: number;
  droppable: boolean;
}

export interface CategoryLeague {
  league: "basketball";
  generated_at: string;
  team: string;
  opponent: string;
  week: { number?: number; start: string; end: string; sim_from?: string };
  adds_used?: number;
  alerts?: { kind: "il" | "activate" | "info"; text: string }[];
  status?: { yahoo: string; scraped_at: string; days_banked: number };
  cats: string[];
  punt: string[];
  lower_is_better: string[];
  adds_left: number;
  open_spots: number;
  banked: { me: CatMap | null; opp: CatMap | null };
  projected: { me: CatMap; opp: CatMap };
  current: Outcome;
  with_plan: Outcome;
  ros: { before: number; after: number };
  plan: PlanStep[];
  free_agents: FreeAgent[];
  roster: RosterPlayer[];
}

export interface Bundle {
  generated_at: string;
  leagues: { basketball?: CategoryLeague };
  /** Fine-grained GitHub token (Actions read/write on the repo only), so the page can start an update. */
  refresh?: { repo: string; workflow: string; token: string };
}

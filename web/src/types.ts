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

export interface RankRow {
  rank: number;
  team_id: number;
  team: string;
  record: string;
  standing: number | null;
  proj_week: number;
  p_cat: CatMap;
  vs: Record<string, number>; // P(win a week) vs each other team, by team_id
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
  rankings?: RankRow[];
  my_team_id?: number;
  this_week_vs?: {
    rows: { team_id: number; team: string; record: number[]; opponent: boolean; cats?: CatMap }[];
    total: number[];
    me?: CatMap;
  };
  season?: {
    weeks: { week: number; start: string; end: string; finished: boolean }[];
    rows: SeasonRow[];
  };
}

export interface SeasonRow {
  team_id: number;
  team: string;
  cat_record: number[]; // [W, L, T] categories vs actual opponents
  allplay: number[]; // [W, L, T] categories vs every team, every week
  matchups: number[]; // [W, L, T] finished weeks
  totals: CatMap;
}

export interface HkPlayer {
  id: number;
  name: string;
  team: string;
  pos: string;
  status: string;
}

export interface HkPlan {
  steps: {
    day: string; add: HkPlayer; drop: HkPlayer; week_pts: number; games_added: number;
    skater_games: number; goalie_starts: number; total: number;
  }[];
  ros_after: number;
  games: { before: number; after: number; goalies_before: number; goalies_after: number };
  points: { before: number; after: number };
  p_win: number | null;
}

export interface HockeyLeague {
  league: "hockey";
  team: string;
  opponent: string;
  my_team_id: number;
  opp_id: number;
  week: { number: number; start: string; end: string; sim_from: string };
  adds_used: number;
  adds_left: number;
  live: { me: number; opp: number; yahoo_proj_me?: number; yahoo_proj_opp?: number };
  projected: { me: number; opp: number };
  p_win: number;
  with_plan: { p_win: number | null; me: number | null };
  ros: { before: number; after: number | null };
  by_stat: { me: Record<string, number>; opp: Record<string, number> };
  player_pts: { me: { name: string; pts: number; bench_pts: number; games: number }[]; opp: { name: string; pts: number; bench_pts: number; games: number }[] };
  lineup_today: {
    starters: (HkPlayer & { slot: string; exp: number; p_play: number })[];
    bench: (HkPlayer & { exp: number; why: string })[];
    no_game: HkPlayer[];
    started: HkPlayer[];
    open_slots: string[];
  };
  plan: { day: string; add: HkPlayer; drop: HkPlayer; week_pts: number; total: number; games_added: number }[];
  plans?: { week: HkPlan | null };
  free_agents: (HkPlayer & { exp_fp: number; day: string; drop: HkPlayer; week_pts: number; total: number; games: number; games_added: number; avail: string })[];
  roster: (HkPlayer & { slot: string; exp_fp: number; p_play: number; keep_value: number; rotatable: boolean; games_left: number; goalie: boolean; week_pts: number })[];
  replacement: Record<string, number>;
  this_week_vs: { rows: { team_id: number; team: string; pts: number; opponent: boolean; result: string; by_stat: Record<string, number> }[]; me_by_stat: Record<string, number>; me_pts: number };
  rankings: { rank: number; team_id: number; team: string; proj_week: number; win_pct: number }[];
  season: {
    team_id: number; team: string; record: number[]; pf: number; pa: number; allplay: number[]; allplay_pct: number;
    luck: number; playoff_odds: number; first_seed: number; proj_wins: number;
    weeks: { week: number; pts: number; opp_pts: number; opp: number; final: boolean }[];
  }[];
  weekly_sd: number;
  status?: { yahoo: string; scraped_at: string; live_today: number };
}

export interface Bundle {
  generated_at: string;
  leagues: { basketball?: CategoryLeague; hockey?: HockeyLeague };
  /** Fine-grained GitHub token (Actions read/write on the repo only), so the page can start an update. */
  refresh?: { repo: string; workflow: string; token: string };
}

export type RiskMode = "auto" | "on" | "off";

export interface ScanSettings {
  universe: string;
  capital: number;
  max_loss: number;
  max_position_pct: number;
  min_score: number;
  risk_mode: RiskMode;
  top: number;
}

export interface Plan {
  entry: number;
  stop: number;
  stop_rule: string;
  target: number;
  risk_per_share: number;
  risk_pct: number;
  reward_risk: number;
  shares: number;
  bound_by: string;
  position_value: number;
  loss_at_stop: number;
}

export interface Pick {
  symbol: string;
  tv_symbol: string;
  company: string | null;
  sector: string | null;
  score: number;
  fundamental: number;
  technical: number;
  breakout: boolean;
  change_pct: number | null;
  strengths: string[];
  red_flags: string[];
  plan: Plan;
}

export interface IndexQuote {
  close?: number;
  change?: number;
  sma50?: number;
  sma200?: number;
  rsi?: number;
  description?: string;
}

export interface Regime {
  status: "risk-on" | "risk-off" | "mixed" | "unknown";
  risk_off: boolean;
  note: string;
  indices: Record<string, IndexQuote>;
}

export interface ScanResult {
  universe: string;
  universe_label: string;
  fetched: number;
  in_universe: number;
  passed_filters: number;
  dropped: Record<string, number>;
  cutoff: number;
  risk_off: boolean;
  total_picks: number;
  picks: Pick[];
  near_misses: Pick[];
  sectors: { sector: string; count: number }[];
  regime: Regime;
  fetched_at: string;
  mode: "live" | "offline";
}

export interface NewsItem {
  title: string;
  published: number | null;
  source: string | null;
  url: string | null;
}

export interface Universe {
  id: string;
  label: string;
}

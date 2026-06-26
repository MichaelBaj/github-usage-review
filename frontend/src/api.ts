/** Backend API client. */

export interface WindowParams {
  days?: number;
  start?: string;
  end?: string;
  team?: string;
}

function qs(params: WindowParams = {}): string {
  const usp = new URLSearchParams();
  if (params.days !== undefined) usp.set("days", String(params.days));
  if (params.start) usp.set("start", params.start);
  if (params.end) usp.set("end", params.end);
  if (params.team) usp.set("team", params.team);
  const s = usp.toString();
  return s ? `?${s}` : "";
}

export interface Kpis {
  window_start: string;
  window_end: string;
  window_days: number;
  total_seats: number;
  active_users_7d: number;
  active_users_30d: number;
  never_used_seats: number;
  stale_seats: number;
  adoption_rate_30d: number;
  avg_dau_7d: number;
  acceptance_rate_30d: number;
  acceptances_30d: number;
  suggestions_30d: number;
  lines_accepted_window: number;
  hours_saved_30d: number;
  monthly_cost_usd: number;
  window_cost_usd: number;
  last_snapshot_at: string | null;
  last_data_load_at: string | null;
  last_data_load_source: "api" | "json_import" | string | null;
}

export interface ImportResult {
  source_type: string;
  rows_read: number;
  rows_imported: number;
  skipped_rows: number;
  warnings: string[];
  date_range: { start: string; end: string } | null;
  overwritten: { date: string; scope: string }[];
  imported_at: string;
}

export type DbImportMode = "replace" | "merge";

export interface DbImportResult {
  source_type: "db_export";
  mode: DbImportMode;
  tables_imported: number;
  rows_total: number;
  tables: Record<string, number>;
}

export interface TrendPoint {
  date: string;
  active_users: number;
  engaged_users: number;
  suggestions: number;
  acceptances: number;
  lines_suggested: number;
  lines_accepted: number;
  acceptance_rate: number;
}

export interface TeamRow {
  team: string;
  // User-derived (primary source for enterprise-managed orgs).
  members_total: number;
  members_with_seats: number;
  active_members: number;
  stale_members: number;
  never_used_members: number;
  adoption_rate: number;
  ai_credits: number;
  window_cost_usd: number;
  prs: number;
  merged_prs: number;
  net_lines: number;
  // Team-scoped metrics (kept for backward compatibility; 0 when unavailable).
  suggestions: number;
  acceptances: number;
  lines_accepted: number;
  lines_suggested: number;
  active_users_sum: number;
  peak_active_users: number;
  avg_active_users: number;
  acceptance_rate: number;
}

export interface TeamActivitySummary {
  members_total: number;
  members_with_seats: number;
  active_members: number;
  stale_members: number;
  never_used_members: number;
  adoption_rate: number;
  ai_credits: number;
  window_cost_usd: number;
  prs: number;
  merged_prs: number;
  net_lines: number;
}

export interface TeamMemberActivity {
  login: string;
  has_seat: boolean;
  status: "active" | "stale" | "never_used" | "no_seat";
  last_activity_at: string | null;
  last_activity_editor: string | null;
  prs: number;
  merged_prs: number;
  net_lines: number;
  ai_credits: number;
  cost_usd: number;
}

export interface TeamActivityDay {
  date: string;
  prs: number;
  merged_prs: number;
  net_lines: number;
}

export interface StaleSeat {
  login: string;
  team: string | null;
  last_activity_at: string | null;
  editor: string | null;
  days_inactive: number | null;
}

export interface Breakdowns {
  languages: { language: string; acc: number; sug: number; la: number }[];
  editors: { editor: string; acc: number; sug: number; chats: number }[];
  models: { model: string; acc: number; sug: number; chats: number }[];
}

export interface FeatureRow {
  feature: string;
  interactions: number;
  code_generations: number;
  code_acceptances: number;
  loc_suggested: number;
  loc_accepted: number;
  loc_deleted: number;
}

export interface FeatureBreakdown {
  window_start: string;
  window_end: string;
  features: FeatureRow[];
}

export interface Projections {
  available: boolean;
  reason?: string;
  history_days?: number;
  current_active?: number;
  projected_active_90d?: number;
  trend_slope_per_day?: number;
  current_seats?: number;
  recommended_seats_for_80pct_adoption?: number;
  potential_seat_reduction?: number;
}

export interface ModelRow {
  editor: string;
  model: string;
  suggestions: number;
  acceptances: number;
  lines_suggested: number;
  lines_accepted: number;
  chats: number;
  chat_insertions: number;
  engaged_users: number;
  acceptance_rate: number;
  ai_credits: number;
}

export interface ModelBreakdown {
  window_start: string;
  window_end: string;
  scope: string;
  team: string | null;
  code: ModelRow[];
  chat: ModelRow[];
  code_editors: CodeEditorRow[];
}

export interface CodeEditorRow {
  editor: string;
  suggestions: number;
  acceptances: number;
  acceptance_rate: number;
  lines_suggested: number;
  lines_accepted: number;
}

export interface ChatVsInline {
  window_start: string;
  window_end: string;
  scope: string;
  team: string | null;
  code_suggestions: number;
  code_acceptances: number;
  code_lines_accepted: number;
  code_acceptance_rate: number;
  chat_total: number;
  chat_insertions: number;
  chat_interaction_share: number;
}

export interface CostWindow {
  window_start: string;
  window_end: string;
  window_days: number;
  monthly_cost_usd: number;
  window_cost_usd: number;
}

export interface CohortRamp {
  buckets: Record<string, number>;
  median_days_to_first_use: number | null;
  sample_size: number;
  never_used: number;
}

export interface PrBucket {
  pr_count: number;
  merged_count: number;
  merge_rate: number;
  additions: number;
  deletions: number;
  net_lines: number;
  changed_files: number;
  commits: number;
  review_comments: number;
  avg_cycle_time_hours: number | null;
  avg_pr_size_lines: number | null;
  avg_review_comments_per_pr: number | null;
}

export interface PrCorrelation {
  window_start: string;
  window_end: string;
  window_days: number;
  team: string | null;
  total_prs: number;
  ai_authored_share: number;
  ai_authored: PrBucket;
  non_ai_authored: PrBucket;
  ai_minus_non_ai_cycle_hours: number | null;
}

export interface Distribution {
  window_start: string;
  window_end: string;
  team: string | null;
  active_authors: number;
  total_prs: number;
  top_10pct_share: number;
  median_prs_per_user: number;
  top_users: {
    login: string;
    prs: number;
    additions: number;
    deletions: number;
    has_seat: boolean;
  }[];
}

export interface UserRow {
  login: string;
  team: string | null;
  created_at: string | null;
  last_activity_at: string | null;
  last_activity_editor: string | null;
  status: "active" | "stale" | "never_used";
  days_inactive: number | null;
  prs: number;
  merged_prs: number;
  additions: number;
  deletions: number;
  net_lines: number;
  ai_credits: number;
}

export interface UserDetail {
  login: string;
  window_start: string;
  window_end: string;
  window_days: number;
  has_seat: boolean;
  seat: Record<string, unknown> | null;
  teams: string[];
  totals: {
    prs: number;
    merged: number;
    additions: number;
    deletions: number;
    net_lines: number;
    avg_cycle_time_hours: number | null;
    window_cost_usd: number;
    ai_credits: number;
    ai_credit_cost_usd: number;
  };
  daily: { date: string; prs: number; merged: number; additions: number; deletions: number }[];
  recent_prs: {
    repo: string;
    number: number;
    state: string;
    created_at: string;
    merged_at: string | null;
    additions: number;
    deletions: number;
    changed_files: number;
    review_comments: number;
    title: string;
  }[];
  pr_ingest_enabled: boolean;
  ai_credits: AiCreditsUser;
  per_user_copilot_metrics_available: boolean;
  per_user_copilot_note: string;
  tokens_available: boolean;
  tokens_note: string;
}

export interface TeamLanguageRow {
  language: string;
  acc: number;
  sug: number;
  la: number;
  ls: number;
}

export interface TeamDetail {
  team: string;
  window_start: string;
  window_end: string;
  window_days: number;
  data_source: string;
  members_total: number;
  members_with_seats: number;
  monthly_cost_usd: number;
  window_cost_usd: number;
  activity: TeamActivitySummary;
  member_activity: TeamMemberActivity[];
  activity_daily: TeamActivityDay[];
  totals: {
    suggestions: number;
    acceptances: number;
    lines_suggested: number;
    lines_accepted: number;
    acceptance_rate: number;
    hours_saved: number;
  };
  daily: {
    date: string;
    active_users: number;
    engaged_users: number;
    suggestions: number;
    acceptances: number;
    lines_accepted: number;
    acceptance_rate: number;
  }[];
  languages: TeamLanguageRow[];
  models: ModelBreakdown;
  chat_vs_inline: ChatVsInline;
  pr_correlation: PrCorrelation;
  ai_credits: AiCreditsTeam;
  members: string[];
}

export interface QualitySummary {
  chat_vs_inline: ChatVsInline;
  model_breakdown: ModelBreakdown;
  power_users: Distribution;
  cohort_ramp: CohortRamp;
  pr_correlation: PrCorrelation;
  ai_credits: AiCreditsSummary;
}

export interface AiCreditSku {
  sku: string;
  product: string;
  quantity: number;
  gross_amount_usd: number;
  net_amount_usd: number;
}

export interface AiCreditUser {
  login: string;
  ai_credits: number;
  gross_amount_usd: number;
  net_amount_usd: number;
}

export interface AiCreditModelUser {
  login: string;
  ai_credits: number;
  percentage: number;
}

export interface AiCreditTopUsersPerModel {
  model: string;
  total_ai_credits: number;
  top_users: AiCreditModelUser[];
}

export interface AiCreditBalancedModelRow {
  model: string;
  quantity: number;
  pct: number;
  tier: "high" | "low";
}

export interface AiCreditBalancedUser {
  login: string;
  total_ai_credits: number;
  high_pct: number;
  low_pct: number;
  models: AiCreditBalancedModelRow[];
}

export interface AiCreditsSummary {
  window_start: string;
  window_end: string;
  available: boolean;
  total_ai_credits: number;
  total_ai_credit_cost_usd: number;
  headline_ai_credits: number | null;
  headline_ai_credit_cost_usd: number | null;
  headline_ai_credit_gross_usd: number | null;
  headline_fetched_at: string | null;
  skus: AiCreditSku[];
  top_users: AiCreditUser[];
  top_users_per_model?: AiCreditTopUsersPerModel[];
  balanced_user_threshold_pct?: number;
  balanced_user_high_tiers?: string[];
  balanced_user_low_tiers?: string[];
  balanced_users?: AiCreditBalancedUser[];
  tokens_available: boolean;
  tokens_note: string;
}

export interface AiCreditsUser {
  login: string;
  window_start: string;
  window_end: string;
  ai_credits: number;
  ai_credit_cost_usd: number;
  by_sku: { sku: string; quantity: number; net_amount_usd: number }[];
  by_model: {
    model: string;
    ai_credits: number;
    net_amount_usd: number;
    share: number;
  }[];
  daily_ai_credits: { date: string; ai_credits: number }[];
  tokens_available: boolean;
  tokens_note: string;
}

export interface AiCreditsTeam {
  team: string;
  window_start: string;
  window_end: string;
  members: number;
  ai_credits: number;
  ai_credit_cost_usd: number;
  top_users: AiCreditUser[];
  tokens_available: boolean;
  tokens_note: string;
}

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path}: ${r.status} ${r.statusText}`);
  return (await r.json()) as T;
}

export const api = {
  kpis: (p: WindowParams = {}) => getJson<Kpis>(`/api/kpis${qs(p)}`),
  trends: (p: WindowParams = { days: 90 }) => getJson<TrendPoint[]>(`/api/trends${qs(p)}`),
  teams: (p: WindowParams = { days: 30 }) => getJson<TeamRow[]>(`/api/teams${qs(p)}`),
  teamList: () => getJson<{ team: string }[]>(`/api/teams/list`),
  teamDetail: (slug: string, p: WindowParams = {}) =>
    getJson<TeamDetail>(`/api/teams/${encodeURIComponent(slug)}${qs(p)}`),
  staleSeats: () => getJson<StaleSeat[]>("/api/seats/stale"),
  users: (p: WindowParams = { days: 30 }) => getJson<UserRow[]>(`/api/users${qs(p)}`),
  userDetail: (login: string, p: WindowParams = {}) =>
    getJson<UserDetail>(`/api/users/${encodeURIComponent(login)}${qs(p)}`),
  breakdowns: (p: WindowParams = { days: 30 }) => getJson<Breakdowns>(`/api/breakdowns${qs(p)}`),
  features: (p: WindowParams = { days: 30 }) => getJson<FeatureBreakdown>(`/api/features${qs(p)}`),
  models: (p: WindowParams = { days: 30 }) => getJson<ModelBreakdown>(`/api/models${qs(p)}`),
  chatVsInline: (p: WindowParams = { days: 30 }) =>
    getJson<ChatVsInline>(`/api/chat-vs-inline${qs(p)}`),
  cost: (p: WindowParams = {}) => getJson<CostWindow>(`/api/cost${qs(p)}`),
  cohorts: () => getJson<CohortRamp>("/api/cohorts"),
  distribution: (p: WindowParams = { days: 30 }) =>
    getJson<Distribution>(`/api/distribution${qs(p)}`),
  prCorrelation: (p: WindowParams = { days: 30 }) =>
    getJson<PrCorrelation>(`/api/pr-correlation${qs(p)}`),
  quality: (p: WindowParams = { days: 30 }) => getJson<QualitySummary>(`/api/quality${qs(p)}`),
  aiCredits: (p: WindowParams = { days: 30 }) =>
    getJson<AiCreditsSummary>(`/api/ai-credits${qs(p)}`),
  aiCreditsUser: (login: string, p: WindowParams = { days: 30 }) =>
    getJson<AiCreditsUser>(`/api/ai-credits/users/${encodeURIComponent(login)}${qs(p)}`),
  aiCreditsTeam: (slug: string, p: WindowParams = { days: 30 }) =>
    getJson<AiCreditsTeam>(`/api/ai-credits/teams/${encodeURIComponent(slug)}${qs(p)}`),
  projections: () => getJson<Projections>("/api/projections"),
  runSnapshot: async (): Promise<unknown> => {
    const r = await fetch("/api/snapshot/run", { method: "POST" });
    if (!r.ok) {
      let detail = `${r.status} ${r.statusText}`;
      try {
        const payload = (await r.json()) as { detail?: string };
        detail = payload.detail ?? detail;
      } catch {
        // Keep the HTTP status fallback.
      }
      throw new Error(`snapshot failed: ${detail}`);
    }
    return r.json();
  },
  importFile: async (file: File): Promise<ImportResult> => {
    const body = new FormData();
    body.set("file", file);
    const r = await fetch("/api/data/import-file", { method: "POST", body });
    if (!r.ok) {
      let detail = `${r.status} ${r.statusText}`;
      try {
        const payload = (await r.json()) as { detail?: string };
        detail = payload.detail ?? detail;
      } catch {
        // Keep the HTTP status fallback.
      }
      throw new Error(`import failed: ${detail}`);
    }
    return (await r.json()) as ImportResult;
  },
  exportData: async (): Promise<void> => {
    const r = await fetch("/api/data/export");
    if (!r.ok) throw new Error(`export failed: ${r.status} ${r.statusText}`);
    const blob = await r.blob();
    const disposition = r.headers.get("Content-Disposition") ?? "";
    const match = /filename="?([^"]+)"?/.exec(disposition);
    const filename = match?.[1] ?? "copilot-usage-export.db.gz";
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  },
  importDatabase: async (file: File, mode: DbImportMode): Promise<DbImportResult> => {
    const body = new FormData();
    body.set("file", file);
    const r = await fetch(`/api/data/import-db?mode=${mode}`, { method: "POST", body });
    if (!r.ok) {
      let detail = `${r.status} ${r.statusText}`;
      try {
        const payload = (await r.json()) as { detail?: string };
        detail = payload.detail ?? detail;
      } catch {
        // Keep the HTTP status fallback.
      }
      throw new Error(`database import failed: ${detail}`);
    }
    return (await r.json()) as DbImportResult;
  },
};

const DB_EXPORT_PATTERN = /\.(db|sqlite|sqlite3)(\.gz)?$|\.db\.gz$/i;

/** Return true if the chosen file looks like a full-database export. */
export function isDbExportFile(file: File): boolean {
  return DB_EXPORT_PATTERN.test(file.name);
}

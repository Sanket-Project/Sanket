export type IndustryCode = "fashion" | "electronics" | "pharma" | "agrocenter" | "hardware";
export type UserRole = "owner" | "admin" | "analyst" | "viewer" | "api_service";
export type TenantStatus = "trial" | "active" | "suspended" | "cancelled";
export type ProductStatus =
  | "active"
  | "discontinued"
  | "seasonal"
  | "clearance"
  | "pre_launch";
export type SignalType =
  | "weather"
  | "trend_search"
  | "social_sentiment"
  | "competitor_price"
  | "macro_economic"
  | "regulatory"
  | "supplier_lead"
  | "logistics_disruption";
export type SignalStatus = "pending" | "validated" | "rejected" | "expired";
export type GxPBatchStatus =
  | "quarantine"
  | "released"
  | "rejected"
  | "recalled"
  | "expired";

export interface LoginRequest {
  email: string;
  password: string;
  tenant_slug: string;
}

export interface SignUpRequest extends LoginRequest {
  name: string;
}

export type OnboardingStatus = "in_progress" | "complete" | "skipped";
export type OnboardingStepKey =
  | "industry"
  | "data"
  | "calendar"
  | "team"
  | "baseline"
  | "done";

export interface OnboardingStepState {
  done: boolean;
  at: string | null;
  meta: Record<string, unknown>;
}

/** Setup readiness for a workspace — drives the onboarding route guard. */
export interface OnboardingState {
  status: OnboardingStatus;
  current_step: OnboardingStepKey;
  steps: Partial<Record<OnboardingStepKey, OnboardingStepState>>;
  completed_at: string | null;
}

/** Identity + tenant context returned by POST /auth/session and /auth/dev-login. */
export interface SessionInfo {
  user_id: string;
  tenant_id: string;
  role: UserRole;
  active_industry: IndustryCode;
  email: string;
  full_name: string;
  /** Absent for legacy/demo tenants (treated as complete). */
  onboarding?: OnboardingState | null;
}

/** Partial update sent to PUT /onboarding/state. */
export interface OnboardingStateUpdate {
  status?: OnboardingStatus;
  current_step?: OnboardingStepKey;
  mark_step?: OnboardingStepKey;
  step_meta?: Record<string, unknown>;
}

// ── Planning calendar & rules (GET/PUT /planning/config) ─────────────────────
export interface PlanningCalendar {
  fiscal_year_start_month: number;
  period: "weekly" | "monthly";
  week_start: "monday" | "sunday";
  horizon_weeks: number;
}
export interface PlanningRules {
  min_history_weeks: number;
  default_service_level: number;
  review_cadence: "weekly" | "biweekly" | "monthly";
}
export interface PlanningConfig {
  calendar: PlanningCalendar;
  rules: PlanningRules;
}

// ── Team invites (/invites) ──────────────────────────────────────────────────
export type InviteRole = "admin" | "analyst" | "viewer";
export interface Invite {
  id: string;
  email: string;
  role: string;
  status: string;
  invited_by: string | null;
  expires_at: string;
  created_at: string;
}
export interface InviteCreated extends Invite {
  invite_url: string;
}
export interface InviteList {
  invites: Invite[];
  seats_used: number;
  seats_total: number;
}

/** Dev-login also returns the bearer token (Firebase manages it otherwise). */
export interface DevLoginResponse extends SessionInfo {
  access_token: string;
  token_type: string;
  expires_in: number;
}

/**
 * Response from POST /auth/sandbox-session — starts the shared public demo
 * session server-side so no credentials ship in the browser bundle.
 * `mode: "dev"` carries an `access_token` bearer; `mode: "firebase"` carries a
 * `custom_token` to exchange via signInWithCustomToken.
 */
export interface SandboxSessionResponse extends SessionInfo {
  mode: "dev" | "firebase";
  access_token?: string | null;
  custom_token?: string | null;
  token_type: string;
  expires_in?: number | null;
}

/** Public auth-mode config from GET /auth/config. */
export interface AuthConfig {
  enabled: boolean;
  project_id?: string | null;
  api_key?: string | null;
}

export interface IndustryContext {
  code: IndustryCode;
  display_name: string;
  default_horizon_weeks: number;
  granularity_dimensions: string[];
  required_signal_types: SignalType[];
  forecast_models: string[];
  optimization_models: string[];
  audit_level: "standard" | "gxp";
  is_gxp: boolean;
}

/** A tenant's focus watchlist — narrows the archetype to the specific business. */
export interface FocusProfile {
  keywords: string[];
  categories: string[];
}

/** GET /industry/profile — archetype defaults merged with tenant overrides. */
export interface EffectiveIndustryConfig {
  code: IndustryCode;
  display_name: string;
  effective_horizon: number;
  active_signal_types: string[];
  focus: FocusProfile;
  feature_flags: Record<string, unknown>;
}

/** PUT /industry/profile — partial; omitted fields are left unchanged. */
export interface IndustryProfileUpdate {
  custom_horizon_weeks?: number | null;
  custom_signal_types?: SignalType[];
  focus?: FocusProfile;
}

export interface Product {
  id: string;
  tenant_id: string;
  industry: IndustryCode;
  external_id: string | null;
  name: string;
  brand: string | null;
  category: string;
  subcategory: string | null;
  status: ProductStatus;
  attributes: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Sku {
  id: string;
  tenant_id: string;
  product_id: string;
  industry: IndustryCode;
  sku_code: string;
  external_id: string | null;
  gtin: string | null;
  description: string | null;
  unit_cost: number | null;
  unit_price: number | null;
  currency: string;
  lead_time_days: number | null;
  moq: number;
  safety_stock: number | null;
  reorder_point: number | null;
  attributes: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ExternalSignal {
  id: string;
  tenant_id: string;
  industry: IndustryCode;
  signal_type: SignalType;
  status: SignalStatus;
  source_name: string;
  source_url: string | null;
  effective_at: string;
  expires_at: string | null;
  region: string | null;
  category_tags: string[];
  sku_tags: string[];
  processed_value: number | null;
  sentiment_score: number | null;
  impact_weight: number | null;
  validated_by: string | null;
  validated_at: string | null;
  created_at: string;
}

export interface OverviewKPIs {
  industry: IndustryCode;
  gxp_mode?: boolean;
  kpis: Record<string, number>;
  top_categories?: { category: string; count: number }[];
  forecast_horizon_weeks: number;
  active_models: string[];
}

export interface ForecastRow {
  sku_id: string;
  forecast_date: string;
  p10: number;
  p50: number;
  p90: number;
}

export interface ForecastResponse {
  run_id: string;
  n_predictions: number;
  rows: ForecastRow[];
  source?: string;
  context_source?: string;
}

export interface PharmaBatchExpiring {
  id: string;
  sku_id: string;
  lot_number: string;
  ndc_code: string | null;
  expiry_date: string;
  quantity_remaining: number;
  cold_chain_required: boolean;
}

// ── Phase 6: trends + hybrid forecast + shortage alerts ────────────────────
export type TrendSignalSource =
  | "fred"
  | "google_trends"
  | "reddit"
  | "twitter"
  | "news_api"
  | "synthetic";

export type TrendSignalKind =
  | "economic_indicator"
  | "social_buzz"
  | "search_interest"
  | "news_sentiment"
  | "commodity_price";

export type AlertSeverity = "info" | "warning" | "critical";
export type AlertStatus = "open" | "acknowledged" | "resolved" | "suppressed";

export interface TrendSignal {
  id: string;
  tenant_id: string | null;
  industry: IndustryCode;
  source: TrendSignalSource;
  kind: TrendSignalKind;
  series_key: string;
  category_tags: string[];
  sku_tags: string[];
  region: string | null;
  raw_value: number | null;
  normalized_score: number;
  confidence: number;
  captured_at: string;
  payload: Record<string, unknown>;
}

export interface TrendDriver {
  source: string;
  kind?: string;
  series_key: string;
  score: number;
  weight?: number;
  captured_at?: string;
}

export interface TrendScore {
  industry: IndustryCode;
  score: number;
  volatility: number;
  sample_count: number;
  by_kind: Record<string, number>;
  drivers: TrendDriver[];
  demand_factors?: TrendDriver[];
  horizon_days: number;
  as_of: string;
}

export interface Scenario {
  name: "pessimistic" | "base" | "optimistic" | string;
  label: string;
  horizon_total: number;
  weekly_path: number[];
  narrative: string;
  drivers: TrendDriver[];
}

export interface HybridForecastSeries {
  sku_id: string;
  sku_code: string | null;
  ds: string[];
  p10: number[];
  p50: number[];
  p90: number[];
  baseline_p50: number[];
}

export interface HybridForecast {
  industry: IndustryCode;
  horizon_weeks: number;
  generated_at: string;
  trend: TrendScore;
  explanation: {
    median_shift_pct: number;
    band_change_pct: number;
    baseline_band_mean: number;
    adjusted_band_mean: number;
  };
  scenarios: Record<string, Scenario>;
  series: HybridForecastSeries[];
  alerts_generated: number;
  /** Source of the baseline: 'trained' | 'zero_shot' | 'synthetic' */
  data_source: string;
}

export interface HybridForecastRequest {
  sku_ids?: string[];
  horizon_weeks?: number;
  include_alerts?: boolean;
  inventory_overrides?: Record<string, { on_hand_units?: number; inbound_units?: number }>;
}

export type HybridRunStatusValue = "pending" | "running" | "completed" | "failed";

export interface HybridRunAccepted {
  run_id: string;
  status: HybridRunStatusValue;
}

export interface HybridRunStatus {
  run_id: string;
  status: HybridRunStatusValue;
  horizon_weeks: number;
  industry: IndustryCode;
  created_at: string;
  completed_at: string | null;
  error: string | null;
  result: HybridForecast | null;
}

export interface ShortageAlert {
  id: string;
  tenant_id: string;
  industry: IndustryCode;
  sku_id: string | null;
  rule_id: string | null;
  severity: AlertSeverity;
  status: AlertStatus;
  risk_score: number;
  coverage_days: number | null;
  p10_demand: number | null;
  p50_demand: number | null;
  p90_demand: number | null;
  trend_score: number | null;
  drivers: Array<Record<string, unknown>>;
  title: string;
  message: string;
  fired_at: string;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  resolved_at: string | null;
  resolution_note: string | null;
}

export interface AlertRule {
  id: string;
  tenant_id: string;
  industry: IndustryCode;
  rule_name: string;
  enabled: boolean;
  warn_coverage_days: number;
  critical_coverage_days: number;
  trend_weight: number;
  p90_weight: number;
  inventory_weight: number;
  cooldown_minutes: number;
  notify_webhook: boolean;
  notify_websocket: boolean;
}

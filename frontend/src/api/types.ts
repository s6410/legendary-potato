// Typer som speglar backend-API:ts svar.

export interface Account {
  id: number
  name: string
  kind: string
  currency: string
  is_active: boolean
  transaction_count: number
}

export interface Category {
  id: number
  name: string
  kind: string
  color: string | null
  icon: string | null
  sort_order: number
  transaction_count: number
  rule_count: number
  children: Category[]
}

export interface TxnLinkInfo {
  link_id: number
  kind: 'refund' | 'transfer'
  status: 'suggested' | 'confirmed'
}

export interface Txn {
  id: number
  booked_date: string
  amount_ore: number
  description: string
  description_norm: string
  account_id: number
  account_name: string | null
  category_id: number | null
  category_path: string | null
  category_source: 'rule' | 'manual' | null
  is_excluded: boolean
  note: string | null
  member: string | null
  link: TxnLinkInfo | null
}

export interface TxnPage {
  total: number
  total_amount_ore: number
  page: number
  page_size: number
  rows: Txn[]
}

export interface Inspection {
  file_type: string
  encoding: string | null
  delimiter: string | null
  header_row_index: number
  header: string[]
  sample_rows: string[][]
  fingerprint: string
  suggested_mapping: Record<string, number | null>
  suggested_date_format: string
  suggested_decimal_separator: string
  suggested_thousands_separator: string | null
  suggested_invert_sign: boolean
}

export interface ImportProfile {
  id: number
  fingerprint: string
  name: string
  default_account_id: number | null
  file_type: string
  delimiter: string | null
  encoding: string | null
  decimal_separator: string
  thousands_separator: string | null
  date_format: string
  header_row_index: number
  invert_sign: boolean
  skip_value: string | null
  column_mapping: Record<string, number | null>
}

export interface InspectResult {
  known: boolean
  profile: ImportProfile | null
  inspection: Inspection
}

export interface PreviewRow {
  booked_date: string
  amount_ore: number
  description: string
  duplicate: boolean
  category_id: number | null
  category_name: string | null
}

export interface ImportPreview {
  account_id: number
  profile_name: string
  total: number
  new_count: number
  duplicate_count: number
  auto_categorized: number
  skipped: { row_index: number; reason: string; cells: string[] }[]
  identical_file_already_imported: boolean
  rows: PreviewRow[]
}

export interface ImportBatch {
  id: number
  account_id: number
  account_name: string | null
  profile_name: string | null
  filename: string | null
  imported_at: string
  row_count: number
  inserted_count: number
  duplicate_count: number
  status: 'committed' | 'reverted'
}

export interface Rule {
  id: number
  match_type: 'exact' | 'prefix' | 'contains'
  pattern: string
  category_id: number
  category_path: string | null
  account_id: number | null
  account_name: string | null
  priority: number
  hit_count: number
  updated_at: string
}

export interface LinkTxn {
  id: number
  booked_date: string
  amount_ore: number
  description: string
  account_name: string | null
}

export interface LinkSuggestion {
  id: number
  kind: 'refund' | 'transfer'
  score: number | null
  txn_a: LinkTxn
  txn_b: LinkTxn
}

export interface SummaryNumbers {
  income_ore: number
  expenses_ore: number
  net_ore: number
  savings_rate: number | null
  transaction_count: number
}

export interface Summary {
  from: string
  to: string
  current: SummaryNumbers
  previous: SummaryNumbers | null
}

export interface CategoryBucket {
  category_id: number | null
  name: string
  color: string | null
  kind: string
  amount_ore: number
  transaction_count: number
}

export interface TrendPoint extends SummaryNumbers {
  month: string
  cumulative_ore?: number
}

export interface Merchant {
  merchant: string
  description_norm: string
  amount_ore: number
  transaction_count: number
}

export interface RecurringSeries {
  description_norm: string
  display_name: string
  account_id: number
  cadence: string
  cadence_label: string
  occurrences: number
  median_amount_ore: number
  variable_amount: boolean
  annual_cost_ore: number
  last_date: string
  next_expected_date: string
  possibly_ended: boolean
  category_id: number | null
  category_path: string | null
  confirmed: boolean
}

export interface BudgetItem {
  budget_id: number
  category_id: number
  category_path: string
  color: string | null
  budget_ore: number
  spent_ore: number
  remaining_ore: number
  progress: number | null
  valid_from: string
}

export interface SavingsAccount {
  id: number
  name: string
  asset_class: string
  asset_class_label: string
  is_active: boolean
  sort_order: number
  parent_id: number | null
  target_pct: number | null
  drift_band_pct: number | null
  has_holdings: boolean
  latest_date: string | null
  latest_value_ore: number | null
}

export interface SavingsHistory {
  dates: string[]
  invested: (number | null)[]
  series: {
    savings_account_id: number
    name: string
    asset_class: string
    values: (number | null)[]
    snapshots: { id: number; date: string; value_ore: number }[]
  }[]
}

export interface DriftClass {
  asset_class: string
  label: string
  value_ore: number
  current_pct: number
  target_pct: number | null
  drift_pct: number | null
  drift_ore: number | null
}

export interface DriftHolding {
  id: number
  name: string
  value_ore: number
  current_pct: number
  target_pct: number | null
  drift_pct: number | null
  drift_ore: number | null
}

export interface DriftAccountSection {
  id: number
  name: string
  total_ore: number
  band_pct: number | null
  holdings: DriftHolding[]
}

export interface Drift {
  total_ore: number
  classes: DriftClass[]
  by_account: { id: number; name: string; value_ore: number; share_pct: number }[]
  accounts: DriftAccountSection[]
}

export interface Target {
  asset_class: string
  label: string
  target_pct: number
}

export interface SavingsPlanAccount {
  id: number
  name: string
  monthly_amount_ore: number
  start_date: string
  invested_ore: number
  current_value_ore: number
  return_ore: number
  return_pct: number
}

export interface SavingsPlanTotal {
  invested_ore: number
  current_value_ore: number
  return_ore: number
  return_pct: number
  monthly_amount_ore: number
}

export interface SavingsPlanSummary {
  accounts: SavingsPlanAccount[]
  total: SavingsPlanTotal | null
  forecast: { rate_pct: number; points: { year: number; value_ore: number }[] }[]
  milestones: {
    amount_ore: number
    is_goal: boolean
    reached: { rate_pct: number; date: string | null }[]
  }[]
}

export interface Forecast {
  based_on_months: string[]
  months: string[]
  categories: { category_id: number | null; name: string; projected_monthly_ore: number }[]
  projected_total_monthly_ore: number
}

export interface Observation {
  type: string
  severity: number
  title: string
  body: string
  link: string
}

export interface CashflowEvent {
  date: string
  description: string
  amount_ore: number
  kind: 'income' | 'expense'
}

export interface CashflowForecast {
  from: string
  days: number
  events: CashflowEvent[]
  daily: { date: string; cumulative_ore: number }[]
  projected_net_ore: number
  variable_daily_ore: number
  savings_total_ore: number
  monthly_expenses_ore: number
  buffer_months: number | null
}

export interface MemberBucket {
  member: string | null
  expenses_ore: number
  income_ore: number
  transaction_count: number
}

export interface ByMember {
  from: string
  to: string
  members: MemberBucket[]
  unassigned: MemberBucket | null
  settlement: { member: string; paid_ore: number; fair_share_ore: number; diff_ore: number }[]
}

export interface RebalancePlan {
  contribution_ore: number
  allocations: { asset_class?: string; id?: number; label: string; amount_ore: number }[]
  requires_selling?: boolean
}

export interface YearlyReport {
  year: number
  summary: SummaryNumbers
  previous_summary: SummaryNumbers
  months: TrendPoint[]
  category_changes: {
    category_id: number | null
    name: string
    color: string | null
    current_ore: number
    previous_ore: number
    diff_ore: number
  }[]
  biggest_month: TrendPoint | null
  biggest_month_top_category: CategoryBucket | null
  top_merchants: Merchant[]
  subscriptions_active: RecurringSeries[]
  subscriptions_cancelled: RecurringSeries[]
  subscriptions_cancelled_savings_ore: number
  subscriptions_annual_cost_ore: number
  savings_start_ore: number | null
  savings_end_ore: number | null
  avg_savings_rate: number | null
}

export interface MonthlyReport {
  month: string
  summary: SummaryNumbers
  previous_summary: SummaryNumbers
  by_category: CategoryBucket[]
  top_merchants: Merchant[]
  largest_expenses: {
    id: number
    booked_date: string
    amount_ore: number
    description: string
    account_name: string | null
    category_path: string | null
  }[]
  budget: BudgetItem[]
  upcoming_recurring: RecurringSeries[]
  trend: TrendPoint[]
}

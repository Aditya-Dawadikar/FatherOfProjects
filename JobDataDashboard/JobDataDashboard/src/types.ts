export type JobRecord = {
  id: number
  source: string
  source_job_id: string
  company_name: string
  company_batch: string | null
  company_url: string | null
  company_one_liner: string | null
  company_logo_url: string | null
  company_last_active_at: string | null
  job_role: string
  job_url: string | null
  application_link: string | null
  location: string | null
  job_type: string | null
  role_type: string | null
  salary_range: string | null
  updated_at: string
}

export type JobDraft = {
  id: number | null
  source: string
  source_job_id: string
  company_name: string
  company_batch: string
  company_url: string
  company_one_liner: string
  company_logo_url: string
  company_last_active_at: string
  job_role: string
  job_url: string
  application_link: string
  location: string
  job_type: string
  role_type: string
  salary_range: string
}

export type HealthResponse = {
  status: string
  table: string
  match_table: string
}

export type JobsCountResponse = {
  total: number
}

export type JobsQuery = {
  searchText: string
  source: string | null
  limit: number
  offset: number
}

// Every source WebScraper's pipeline knows how to scrape today -- see WebScraper/ats_scraper.py
// and scraper.py. Kept as a fixed list (matching MatchFilter's approach) rather than derived from
// data, same tradeoff: a fifth source added later needs this list updated too.
export const JOB_SOURCES = ['ycombinator', 'greenhouse', 'ashby', 'lever'] as const

export type MatchFilter = 'all' | 'matched' | 'unmatched'

export type ScoreCriterion = {
  score: number
  reasoning: string
}

// Keyed by criterion name (skills_match, experience_fit, location_visa_fit, compensation_fit,
// role_scope_fit -- see JobManagerAgent/llm_providers/base.py:CRITERIA_KEYS). Only present on
// rows scored by a rubric-based prompt (v4+); legacy (v1-v3) rows have score_breakdown: null.
export type ScoreBreakdown = Record<string, ScoreCriterion>

export type MatchedJobRecord = JobRecord & {
  match_score: number
  is_match: boolean
  reasoning: string | null
  prompt_name: string
  prompt_version: string
  model_name: string
  evaluated_at: string
  score_breakdown: ScoreBreakdown | null
}

export type MatchesQuery = {
  searchText: string
  matchFilter: MatchFilter
  minScore: number | null
  promptVersion: string | null
  limit: number
  offset: number
}

export type PromptVersionSummary = {
  prompt_version: string
  prompt_name: string
  model_name: string
  row_count: number
  latest_evaluated_at: string
}

export type SourceFunnelSlice = {
  source: string
  total_scraped: number
  total_processed: number
}

export type PipelineFunnel = {
  total_scraped: number
  total_processed: number
  good_matches: number
  moderate_matches: number
  bad_matches: number
  failed_matches: number
  by_source: SourceFunnelSlice[]
}

export type AgentTopologyNodeKind = 'agent' | 'tool' | 'middleware' | 'guardrail' | 'prompt'

export type AgentTopologyNode = {
  id: string
  label: string
  kind: AgentTopologyNodeKind
  detail: string
  source: string
  rule_labels: string[] | null
}

export type AgentTopologyEdge = {
  source: string
  target: string
  label: string | null
}

export type AgentTopology = {
  generated_at: string
  agent_name: string
  threshold: number
  max_jobs_per_cycle: number
  tool_call_limit: number
  nodes: AgentTopologyNode[]
  edges: AgentTopologyEdge[]
}

export type MlflowEvalTypeCount = {
  label: string
  experiment_name: string
  run_count: number
  mlflow_url: string | null
}

export type MlflowSummary = {
  generated_at: string
  mlflow_base_url: string | null
  traces_collected: number
  traces_mlflow_url: string | null
  offline_evals_triggered: number
  offline_evals_by_type: MlflowEvalTypeCount[]
  registered_prompt_versions: number
  production_prompt_version: string | null
  total_tokens_tracked: number
  total_cost_usd_tracked: number
}

export type EvalRunStatus = 'running' | 'completed' | 'failed'

export type EvalRunResult = {
  total_cases?: number
  evaluated_cases?: number
  errored_cases?: number
  true_positive?: number
  false_positive?: number
  false_negative?: number
  true_negative?: number
  accuracy?: number
  precision?: number
  recall?: number
  f1?: number
  score_in_range_rate?: number
  criteria_in_range_rate?: number
  mean_predicted_score?: number
  total_prompt_tokens?: number
  total_completion_tokens?: number
  total_tokens?: number
  mean_tokens_per_case?: number
}

export type EvalRun = {
  eval_id: string
  run_id: string
  status: EvalRunStatus
  started_at: string | null
  finished_at: string | null
  experiment_id: string | null
  experiment_name: string | null
  mlflow_url: string | null
  mlflow_trace_url: string | null
  sweep_id: string | null
  run_name: string | null
  dataset_path: string | null
  prompt_source: string | null
  prompt_version: string | null
  llm_provider: string | null
  llm_model: string | null
  match_threshold: number | null
  dataset_case_count: number | null
  limit: number | null
  result: EvalRunResult | null
  error: string | null
}

export type EvalSweepTrigger = {
  eval_id: string
  status: 'running'
  prompt_version: number | null
  sweep_id: string | null
}

// POST /evals request body -- only the fields the Prompt Version Comparison trigger form
// actually exposes; every other EvalTriggerRequest field (dataset/provider/model/threshold/...)
// is left to its server-side default. prompt_version is only honored by the backend when
// prompt_source is 'production' (the default here) -- see api/eval_runs.py's EvalTriggerRequest.
export type EvalTriggerRequest = {
  prompt_source?: 'production' | 'local'
  prompt_version?: number | null
}

// Same response shape as EvalSweepTrigger's per-item type, but for a single plain POST /evals
// trigger rather than one-per-registered-version -- sweep_id is always null here.
export type EvalTrigger = {
  eval_id: string
  status: 'running'
  prompt_version: number | null
  sweep_id: string | null
}

export type ToolEvalRunResult = {
  total_cases?: number
  evaluated_cases?: number
  errored_cases?: number
  repeats?: number
  total_trials?: number
  incomplete_trials?: number
  tool_selection_accuracy?: number
  tool_error_rate?: number
  call_volume_efficiency?: number
  plan_adherence?: number
  consistency_score?: number
  success_rate?: number
  total_expected_calls?: number
  total_actual_calls?: number
  total_guardrail_errors?: number
  total_scripted_errors?: number
  total_input_tokens?: number
  total_output_tokens?: number
  total_cost_usd?: number
  total_successful_trials?: number
  mean_calls_per_trial?: number
  mean_cost_per_run?: number
  cost_per_successful_run?: number
}

export type ToolEvalRun = {
  eval_id: string
  run_id: string
  status: EvalRunStatus
  started_at: string | null
  finished_at: string | null
  experiment_id: string | null
  experiment_name: string | null
  mlflow_url: string | null
  mlflow_trace_url: string | null
  run_name: string | null
  dataset_path: string | null
  llm_model: string | null
  match_threshold: number | null
  dataset_case_count: number | null
  limit: number | null
  repeats: number | null
  result: ToolEvalRunResult | null
  error: string | null
}

export type ToolEvalTrigger = {
  eval_id: string
  status: 'running'
}

export type GuardrailsEvalRunResult = {
  total_cases: number
  evaluated_cases: number
  true_positive: number
  false_positive: number
  false_negative: number
  true_negative: number
  accuracy?: number
  precision?: number
  recall?: number
  f1?: number
  guardrail_id_accuracy?: number
}

export type GuardrailsEvalRun = {
  eval_id: string
  run_id: string
  status: EvalRunStatus
  started_at: string | null
  finished_at: string | null
  experiment_id: string | null
  experiment_name: string | null
  mlflow_url: string | null
  mlflow_trace_url: string | null
  run_name: string | null
  dataset_path: string | null
  dataset_case_count: number | null
  limit: number | null
  result: GuardrailsEvalRunResult | null
  error: string | null
}

export type GuardrailsEvalTrigger = {
  eval_id: string
  status: 'running'
}

export type EvalDatasetKind = 'prompt_matching' | 'guardrails' | 'tool_selection' | 'unknown'

export type EvalDatasetSummary = {
  name: string
  path: string
  kind: EvalDatasetKind
  case_count: number
  size_bytes: number
  modified_at: string
}

export type EvalDatasetCase = {
  line_number: number
  id: string | null
  data: Record<string, unknown>
}

export type EvalDatasetDetail = {
  name: string
  path: string
  kind: EvalDatasetKind
  cases: EvalDatasetCase[]
  parse_errors: string[]
}

// --- Migration control (feature flag / prompt cutover / backfill / RPM breakdown) -------------
// JobManagerAgent's api/admin.py + api/backfill.py -- see JobManagerAgent/docs/backfill-design.md.

export type RegisteredPrompt = {
  version: string
  schema_mode: 'legacy' | 'single' | 'batch'
  rubric_version: number
  status: 'live' | 'decommissioned'
  template: string
  is_active: boolean
  creation_timestamp: number | null
}

export type PromptActiveHistoryEntry = {
  changed_at: string
  from_version: string | null
  to_version: string
  schema_mode: string
  rubric_version: number
  reason: string
}

export type SetActivePromptResult = {
  prompt_name: string
  alias: string
  version: string
  schema_mode: string
  rubric_version: number
}

export type UnscoredBackfillStatus = {
  paused: boolean
  reason: string | null
}

export type RpmBucketUsage = {
  bucket: string
  model: string
  count: number
  cap: number
  remaining: number
}

export type RpmBreakdown = {
  model: string
  window_seconds: number
  buckets: RpmBucketUsage[]
  total_allocated: number
  provider_quota: number | null
  headroom: number | null
}

export type BillingStatus = {
  is_billing_exhausted: boolean
  billing_exhausted_at: string | null
  billing_exhausted_message: string | null
}

export type RpmDistributionUpdate = {
  live_cap: number
  backfill_cap: number
  eval_cap: number
  provider_quota: number | null
}

export type BackfillProcessSummary = {
  name: string
  description: string
}

export type BackfillRunStatusValue = 'running' | 'completed' | 'failed' | 'cancelled'

export type BackfillRun = {
  run_id: string
  process: string
  params: Record<string, unknown>
  status: BackfillRunStatusValue
  candidate_count: number | null
  processed: number
  rescored: number
  not_found_404: number
  crawl_error: number
  errored: number
  error: string | null
  cancel_reason: string | null
  started_at: string
  finished_at: string | null
}

export type BackfillRunTrigger = {
  run_id: string
  status: 'running'
}
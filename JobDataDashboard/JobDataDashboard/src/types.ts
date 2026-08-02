export type JobRecord = {
  job_id: number
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
  job_id: string
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
  limit: number
  offset: number
}

export type MatchFilter = 'all' | 'matched' | 'unmatched'

export type MatchedJobRecord = JobRecord & {
  match_score: number
  is_match: boolean
  reasoning: string | null
  prompt_name: string
  prompt_version: string
  model_name: string
  evaluated_at: string
}

export type MatchesQuery = {
  searchText: string
  matchFilter: MatchFilter
  minScore: number | null
  limit: number
  offset: number
}

export type PipelineFunnel = {
  total_scraped: number
  total_processed: number
  good_matches: number
  moderate_matches: number
  bad_matches: number
  failed_matches: number
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
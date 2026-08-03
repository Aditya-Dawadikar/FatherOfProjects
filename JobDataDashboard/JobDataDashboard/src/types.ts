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

export type AgentTopologyNodeKind = 'agent' | 'tool' | 'middleware' | 'guardrail' | 'prompt'

export type AgentTopologyNode = {
  id: string
  label: string
  kind: AgentTopologyNodeKind
  detail: string
  source: string
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
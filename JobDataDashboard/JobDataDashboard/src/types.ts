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
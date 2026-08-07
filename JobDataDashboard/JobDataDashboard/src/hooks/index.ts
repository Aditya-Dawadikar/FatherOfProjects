import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type {
  AgentTopology,
  BackfillProcessSummary,
  BackfillRun,
  BackfillRunTrigger,
  EvalRun,
  EvalSweepTrigger,
  GuardrailsEvalRun,
  GuardrailsEvalTrigger,
  HealthResponse,
  JobDraft,
  JobRecord,
  JobsCountResponse,
  JobsQuery,
  MatchedJobRecord,
  MatchesQuery,
  MlflowSummary,
  PipelineFunnel,
  PromptActiveHistoryEntry,
  RpmDistributionUpdate,
  PromptVersionSummary,
  RegisteredPrompt,
  RpmBreakdown,
  SetActivePromptResult,
  TokenBudgetStatus,
  ToolEvalRun,
  ToolEvalTrigger,
  UnscoredBackfillStatus,
} from '../types'

const API_BASE = (import.meta.env.DEV ? import.meta.env.VITE_JOB_DATA_API_BASE_URL ?? '' : '').replace(/\/$/, '')

function buildApiUrl(path: string) {
  return `${API_BASE}${path}`
}

function logRuntimeUrls() {
  if (typeof window === 'undefined') {
    return
  }

  console.info('[job-data-dashboard-runtime]', {
    mode: import.meta.env.MODE,
    dev: import.meta.env.DEV,
    origin: window.location.origin,
    pathname: window.location.pathname,
    apiBase: API_BASE || '(same-origin)',
    healthUrl: buildApiUrl('/api/health'),
    jobsUrl: buildApiUrl('/api/jobs'),
  })
}

logRuntimeUrls()

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const requestUrl = buildApiUrl(path)
  const requestMethod = init?.method ?? 'GET'

  console.info('[job-data-dashboard-request:start]', {
    method: requestMethod,
    path,
    requestUrl,
  })

  let response: Response
  try {
    response = await fetch(requestUrl, {
      headers: {
        'Content-Type': 'application/json',
        ...(init?.headers ?? {}),
      },
      ...init,
    })
  } catch (error) {
    console.error('[job-data-dashboard-request:network-error]', {
      method: requestMethod,
      path,
      requestUrl,
      error,
    })
    throw error
  }

  console.info('[job-data-dashboard-request:response]', {
    method: requestMethod,
    path,
    requestUrl,
    responseUrl: response.url,
    status: response.status,
    redirected: response.redirected,
    proxy: response.headers.get('x-dashboard-proxy'),
    route: response.headers.get('x-caddy-route'),
    upstream: response.headers.get('x-job-data-upstream'),
    contentType: response.headers.get('content-type'),
  })

  if (!response.ok) {
    let detail = `${response.status}`
    try {
      const payload = await response.json() as { detail?: string }
      detail = payload.detail ?? detail
    } catch {
      detail = await response.text() || detail
    }
    throw new Error(detail)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

async function fetchJobs({ searchText, limit, offset }: JobsQuery): Promise<JobRecord[]> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  })
  const trimmedQuery = searchText.trim()
  const path = trimmedQuery ? '/api/jobs/search' : '/api/jobs'

  if (trimmedQuery) {
    params.set('query', trimmedQuery)
  }

  return requestJson<JobRecord[]>(`${path}?${params.toString()}`)
}

async function fetchJobsCount({ searchText }: Pick<JobsQuery, 'searchText'>): Promise<JobsCountResponse> {
  const params = new URLSearchParams()
  const trimmedQuery = searchText.trim()

  if (trimmedQuery) {
    params.set('query', trimmedQuery)
  }

  const querySuffix = params.size ? `?${params.toString()}` : ''
  return requestJson<JobsCountResponse>(`/api/jobs/count${querySuffix}`)
}

async function fetchHealth(): Promise<HealthResponse> {
  return requestJson<HealthResponse>('/api/health')
}

function buildMatchesParams({ searchText, matchFilter, minScore, promptVersion }: Omit<MatchesQuery, 'limit' | 'offset'>) {
  const params = new URLSearchParams()
  const trimmedQuery = searchText.trim()

  if (trimmedQuery) {
    params.set('query', trimmedQuery)
  }
  if (matchFilter !== 'all') {
    params.set('is_match', matchFilter === 'matched' ? 'true' : 'false')
  }
  if (minScore !== null) {
    params.set('min_score', String(minScore))
  }
  if (promptVersion !== null) {
    params.set('prompt_version', promptVersion)
  }

  return params
}

async function fetchMatchedJobs({ searchText, matchFilter, minScore, promptVersion, limit, offset }: MatchesQuery): Promise<MatchedJobRecord[]> {
  const params = buildMatchesParams({ searchText, matchFilter, minScore, promptVersion })
  params.set('limit', String(limit))
  params.set('offset', String(offset))
  return requestJson<MatchedJobRecord[]>(`/api/jobs/matched?${params.toString()}`)
}

async function fetchMatchedJobsCount(filters: Omit<MatchesQuery, 'limit' | 'offset'>): Promise<JobsCountResponse> {
  const params = buildMatchesParams(filters)
  const querySuffix = params.size ? `?${params.toString()}` : ''
  return requestJson<JobsCountResponse>(`/api/jobs/matched/count${querySuffix}`)
}

async function fetchPipelineFunnel(): Promise<PipelineFunnel> {
  return requestJson<PipelineFunnel>('/api/matches/funnel')
}

async function fetchPromptVersions(): Promise<PromptVersionSummary[]> {
  return requestJson<PromptVersionSummary[]>('/api/matches/prompt-versions')
}

function toNullable(value: string) {
  const trimmedValue = value.trim()
  return trimmedValue ? trimmedValue : null
}

function toCreatePayload(draft: JobDraft) {
  return {
    job_id: Number(draft.job_id),
    company_name: draft.company_name.trim(),
    company_batch: toNullable(draft.company_batch),
    company_url: toNullable(draft.company_url),
    company_one_liner: toNullable(draft.company_one_liner),
    company_logo_url: toNullable(draft.company_logo_url),
    company_last_active_at: toNullable(draft.company_last_active_at),
    job_role: draft.job_role.trim(),
    job_url: toNullable(draft.job_url),
    application_link: toNullable(draft.application_link),
    location: toNullable(draft.location),
    job_type: toNullable(draft.job_type),
    role_type: toNullable(draft.role_type),
    salary_range: toNullable(draft.salary_range),
  }
}

function toPatchPayload(draft: JobDraft) {
  const createPayload = toCreatePayload(draft)
  const { job_id, ...patchPayload } = createPayload
  void job_id
  return patchPayload
}

export function createEmptyDraft(): JobDraft {
  return {
    job_id: '',
    company_name: '',
    company_batch: '',
    company_url: '',
    company_one_liner: '',
    company_logo_url: '',
    company_last_active_at: '',
    job_role: '',
    job_url: '',
    application_link: '',
    location: '',
    job_type: '',
    role_type: '',
    salary_range: '',
  }
}

export function toDraft(record: JobRecord): JobDraft {
  return {
    job_id: String(record.job_id),
    company_name: record.company_name,
    company_batch: record.company_batch ?? '',
    company_url: record.company_url ?? '',
    company_one_liner: record.company_one_liner ?? '',
    company_logo_url: record.company_logo_url ?? '',
    company_last_active_at: record.company_last_active_at ?? '',
    job_role: record.job_role,
    job_url: record.job_url ?? '',
    application_link: record.application_link ?? '',
    location: record.location ?? '',
    job_type: record.job_type ?? '',
    role_type: record.role_type ?? '',
    salary_range: record.salary_range ?? '',
  }
}

export async function createJob(draft: JobDraft): Promise<JobRecord> {
  return requestJson<JobRecord>('/api/jobs', {
    method: 'POST',
    body: JSON.stringify(toCreatePayload(draft)),
  })
}

export async function updateJob(draft: JobDraft): Promise<JobRecord> {
  return requestJson<JobRecord>(`/api/jobs/${draft.job_id}`, {
    method: 'PATCH',
    body: JSON.stringify(toPatchPayload(draft)),
  })
}

export async function deleteJob(jobId: number): Promise<void> {
  await requestJson<void>(`/api/jobs/${jobId}`, {
    method: 'DELETE',
  })
}

export function useJobs(filters: JobsQuery) {
  return useQuery({
    queryKey: ['jobs', filters],
    queryFn: () => fetchJobs(filters),
    staleTime: 5_000,
  })
}

export function useJobsCount(searchText: string) {
  return useQuery({
    queryKey: ['jobsCount', searchText],
    queryFn: () => fetchJobsCount({ searchText }),
    staleTime: 5_000,
  })
}

export function useJobDataHealth() {
  return useQuery({
    queryKey: ['jobDataHealth'],
    queryFn: fetchHealth,
    staleTime: 15_000,
  })
}

export function useMatchedJobs(filters: MatchesQuery) {
  return useQuery({
    queryKey: ['matchedJobs', filters],
    queryFn: () => fetchMatchedJobs(filters),
    staleTime: 5_000,
  })
}

export function useMatchedJobsCount(filters: Omit<MatchesQuery, 'limit' | 'offset'>) {
  return useQuery({
    queryKey: ['matchedJobsCount', filters],
    queryFn: () => fetchMatchedJobsCount(filters),
    staleTime: 5_000,
  })
}

export function usePipelineFunnel() {
  return useQuery({
    queryKey: ['pipelineFunnel'],
    queryFn: fetchPipelineFunnel,
    staleTime: 5_000,
  })
}

export function usePromptVersions() {
  return useQuery({
    queryKey: ['promptVersions'],
    queryFn: fetchPromptVersions,
    staleTime: 15_000,
  })
}

// JobManagerAgent's API lives on a separate service from JobDataServer, so it gets its own
// base-url resolution + request helper (same shape as requestJson above, mirrored rather than
// shared so each service's proxy target stays independently configurable).
const AGENT_API_BASE = (import.meta.env.DEV ? import.meta.env.VITE_AGENT_API_BASE_URL ?? '' : '').replace(/\/$/, '')

function buildAgentApiUrl(path: string) {
  return `${AGENT_API_BASE}${path}`
}

async function requestAgentJson<T>(path: string, init?: RequestInit): Promise<T> {
  const requestUrl = buildAgentApiUrl(path)
  const requestMethod = init?.method ?? 'GET'

  console.info('[job-manager-agent-request:start]', {
    method: requestMethod,
    path,
    requestUrl,
  })

  let response: Response
  try {
    response = await fetch(requestUrl, {
      headers: {
        'Content-Type': 'application/json',
        ...(init?.headers ?? {}),
      },
      ...init,
    })
  } catch (error) {
    console.error('[job-manager-agent-request:network-error]', {
      method: requestMethod,
      path,
      requestUrl,
      error,
    })
    throw error
  }

  console.info('[job-manager-agent-request:response]', {
    method: requestMethod,
    path,
    requestUrl,
    status: response.status,
  })

  if (!response.ok) {
    let detail = `${response.status}`
    try {
      const payload = await response.json() as { detail?: string }
      detail = payload.detail ?? detail
    } catch {
      detail = await response.text() || detail
    }
    throw new Error(detail)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

async function fetchEvals(): Promise<EvalRun[]> {
  return requestAgentJson<EvalRun[]>('/agent-api/evals')
}

async function triggerEvalSweep(): Promise<EvalSweepTrigger[]> {
  return requestAgentJson<EvalSweepTrigger[]>('/agent-api/evals/sweep', {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

export function useEvals() {
  return useQuery({
    queryKey: ['evals'],
    queryFn: fetchEvals,
    staleTime: 3_000,
    // Eval runs can take 10+ minutes; keep polling while any run in the last fetch is still
    // "running" so the list picks up completion without a manual refresh, and stop otherwise.
    refetchInterval: (query) => {
      const runs = query.state.data
      const hasRunningRun = runs?.some((run) => run.status === 'running') ?? false
      return hasRunningRun ? 5_000 : false
    },
  })
}

export function useTriggerEvalSweep() {
  return useMutation({
    mutationFn: triggerEvalSweep,
  })
}

async function fetchToolEvals(): Promise<ToolEvalRun[]> {
  return requestAgentJson<ToolEvalRun[]>('/agent-api/evals/tool-selection')
}

async function triggerToolEval(): Promise<ToolEvalTrigger> {
  return requestAgentJson<ToolEvalTrigger>('/agent-api/evals/tool-selection', {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

export function useToolEvals() {
  return useQuery({
    queryKey: ['toolEvals'],
    queryFn: fetchToolEvals,
    staleTime: 3_000,
    // Tool-selection runs are much faster than a full offline eval (one orchestrator LLM call
    // per tool-selection decision, not per case against the full scoring pipeline), but still
    // poll while one is in flight so the list picks up completion without a manual refresh.
    refetchInterval: (query) => {
      const runs = query.state.data
      const hasRunningRun = runs?.some((run) => run.status === 'running') ?? false
      return hasRunningRun ? 5_000 : false
    },
  })
}

export function useTriggerToolEval() {
  return useMutation({
    mutationFn: triggerToolEval,
  })
}

async function fetchGuardrailsEvals(): Promise<GuardrailsEvalRun[]> {
  return requestAgentJson<GuardrailsEvalRun[]>('/agent-api/evals/guardrails')
}

async function fetchAgentTopology(): Promise<AgentTopology> {
  return requestAgentJson<AgentTopology>('/agent-api/agent-topology')
}

async function fetchMlflowSummary(): Promise<MlflowSummary> {
  return requestAgentJson<MlflowSummary>('/agent-api/mlflow-summary')
}

async function triggerGuardrailsEval(): Promise<GuardrailsEvalTrigger> {
  return requestAgentJson<GuardrailsEvalTrigger>('/agent-api/evals/guardrails', {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

export function useGuardrailsEvals() {
  return useQuery({
    queryKey: ['guardrailsEvals'],
    queryFn: fetchGuardrailsEvals,
    staleTime: 3_000,
    // Guardrail runs finish in under a second (no LLM calls, just a golden dataset pass), but
    // still poll while one is in flight so the list picks up completion without a manual refresh.
    refetchInterval: (query) => {
      const runs = query.state.data
      const hasRunningRun = runs?.some((run) => run.status === 'running') ?? false
      return hasRunningRun ? 5_000 : false
    },
  })
}

export function useTriggerGuardrailsEval() {
  return useMutation({
    mutationFn: triggerGuardrailsEval,
  })
}

export function useAgentTopology() {
  return useQuery({
    queryKey: ['agentTopology'],
    queryFn: fetchAgentTopology,
    staleTime: 60_000,
  })
}

export function useMlflowSummary() {
  return useQuery({
    queryKey: ['mlflowSummary'],
    queryFn: fetchMlflowSummary,
    staleTime: 60_000,
  })
}

// --- Migration control (feature flag / prompt cutover / backfill / RPM breakdown) -------------
// All against JobManagerAgent (api/admin.py, api/backfill.py) -- see requestAgentJson above.
// See JobManagerAgent/docs/backfill-design.md for the design these hooks drive a UI for.

async function fetchPrompts(): Promise<RegisteredPrompt[]> {
  return requestAgentJson<RegisteredPrompt[]>('/agent-api/admin/prompts')
}

async function fetchPromptHistory(): Promise<PromptActiveHistoryEntry[]> {
  return requestAgentJson<PromptActiveHistoryEntry[]>('/agent-api/admin/active-prompt/history')
}

async function setActivePrompt(version: string): Promise<SetActivePromptResult> {
  return requestAgentJson<SetActivePromptResult>('/agent-api/admin/active-prompt', {
    method: 'POST',
    body: JSON.stringify({ version }),
  })
}

async function revertActivePrompt(): Promise<SetActivePromptResult> {
  return requestAgentJson<SetActivePromptResult>('/agent-api/admin/active-prompt/revert', {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

export function usePrompts() {
  return useQuery({
    queryKey: ['prompts'],
    queryFn: fetchPrompts,
    staleTime: 5_000,
  })
}

export function usePromptHistory() {
  return useQuery({
    queryKey: ['promptActiveHistory'],
    queryFn: fetchPromptHistory,
    staleTime: 5_000,
  })
}

// Both the "set active" and "revert" mutations invalidate the same three queries -- the prompt
// list (is_active moved), the history (a new entry was appended), and the Matches page's
// prompt-version dropdown (JobDataServer, a different service, but a cutover changes what
// "latest" means there too) -- so the whole dashboard reflects a cutover immediately rather than
// waiting for each panel's own staleTime to lapse.
function useInvalidateAfterPromptChange() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: ['prompts'] })
    queryClient.invalidateQueries({ queryKey: ['promptActiveHistory'] })
    queryClient.invalidateQueries({ queryKey: ['promptVersions'] })
  }
}

export function useSetActivePrompt() {
  const invalidate = useInvalidateAfterPromptChange()
  return useMutation({
    mutationFn: setActivePrompt,
    onSuccess: invalidate,
  })
}

export function useRevertActivePrompt() {
  const invalidate = useInvalidateAfterPromptChange()
  return useMutation({
    mutationFn: revertActivePrompt,
    onSuccess: invalidate,
  })
}

async function fetchUnscoredBackfillStatus(): Promise<UnscoredBackfillStatus> {
  return requestAgentJson<UnscoredBackfillStatus>('/agent-api/admin/unscored-backfill/status')
}

async function pauseUnscoredBackfill(reason: string): Promise<UnscoredBackfillStatus> {
  return requestAgentJson<UnscoredBackfillStatus>('/agent-api/admin/unscored-backfill/pause', {
    method: 'POST',
    body: JSON.stringify({ reason }),
  })
}

async function resumeUnscoredBackfill(): Promise<UnscoredBackfillStatus> {
  return requestAgentJson<UnscoredBackfillStatus>('/agent-api/admin/unscored-backfill/resume', {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

export function useUnscoredBackfillStatus() {
  return useQuery({
    queryKey: ['unscoredBackfillStatus'],
    queryFn: fetchUnscoredBackfillStatus,
    staleTime: 3_000,
    refetchInterval: 10_000,
  })
}

export function usePauseUnscoredBackfill() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: pauseUnscoredBackfill,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['unscoredBackfillStatus'] }),
  })
}

export function useResumeUnscoredBackfill() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: resumeUnscoredBackfill,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['unscoredBackfillStatus'] }),
  })
}

async function fetchRateLimits(): Promise<RpmBreakdown> {
  return requestAgentJson<RpmBreakdown>('/agent-api/admin/rate-limits')
}

async function updateRateLimitsDistribution(payload: RpmDistributionUpdate): Promise<RpmBreakdown> {
  return requestAgentJson<RpmBreakdown>('/agent-api/admin/rate-limits/config', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function useRateLimits() {
  return useQuery({
    queryKey: ['rateLimits'],
    queryFn: fetchRateLimits,
    staleTime: 2_000,
    // "Real-time" breakdown -- polls continuously (not just while something's running) since the
    // whole point is watching x/y/z shift live during a handoff, including live traffic the
    // dashboard has no other signal for.
    refetchInterval: 4_000,
  })
}

export function useUpdateRateLimitsDistribution() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: updateRateLimitsDistribution,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['rateLimits'] }),
  })
}

async function fetchTokenBudget(): Promise<TokenBudgetStatus> {
  return requestAgentJson<TokenBudgetStatus>('/agent-api/admin/token-budget')
}

async function resetTokenBudget(): Promise<TokenBudgetStatus> {
  return requestAgentJson<TokenBudgetStatus>('/agent-api/admin/token-budget/reset', { method: 'POST' })
}

export function useTokenBudget() {
  return useQuery({
    queryKey: ['tokenBudget'],
    queryFn: fetchTokenBudget,
    staleTime: 10_000,
    // Polls on every page, not just Migration (see Layout.tsx's global alert banner) -- billing
    // exhaustion needs to surface no matter which tab is open, not just to someone who happens
    // to be looking at the RPM breakdown when it happens.
    refetchInterval: 15_000,
  })
}

export function useResetTokenBudget() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: resetTokenBudget,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tokenBudget'] }),
  })
}

async function fetchBackfillProcesses(): Promise<BackfillProcessSummary[]> {
  return requestAgentJson<BackfillProcessSummary[]>('/agent-api/backfill/processes')
}

export function useBackfillProcesses() {
  return useQuery({
    queryKey: ['backfillProcesses'],
    queryFn: fetchBackfillProcesses,
    staleTime: 60_000,
  })
}

async function fetchBackfillRuns(): Promise<BackfillRun[]> {
  return requestAgentJson<BackfillRun[]>('/agent-api/backfill/runs')
}

export function useBackfillRuns() {
  return useQuery({
    queryKey: ['backfillRuns'],
    queryFn: fetchBackfillRuns,
    staleTime: 3_000,
    // Poll while a run is in flight so progress (processed/rescored/... counts) updates without
    // a manual refresh; stop once nothing is running.
    refetchInterval: (query) => {
      const runs = query.state.data
      const hasRunningRun = runs?.some((run) => run.status === 'running') ?? false
      return hasRunningRun ? 4_000 : false
    },
  })
}

async function triggerBackfill(payload: { process: string; params: Record<string, unknown>; limit: number | null }): Promise<BackfillRunTrigger> {
  return requestAgentJson<BackfillRunTrigger>('/agent-api/backfill/run', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function useTriggerBackfill() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: triggerBackfill,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['backfillRuns'] }),
  })
}

async function cancelBackfillRun(runId: string): Promise<BackfillRun> {
  return requestAgentJson<BackfillRun>(`/agent-api/backfill/runs/${runId}/cancel`, {
    method: 'POST',
  })
}

export function useCancelBackfillRun() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: cancelBackfillRun,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['backfillRuns'] }),
  })
}
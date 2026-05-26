import { useQuery } from '@tanstack/react-query'
import type { HealthResponse, JobDraft, JobRecord, JobsQuery } from '../types'

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

async function fetchJobs({ searchText, limit }: JobsQuery): Promise<JobRecord[]> {
  const params = new URLSearchParams({ limit: String(limit) })
  const trimmedQuery = searchText.trim()
  const path = trimmedQuery ? '/api/jobs/search' : '/api/jobs'

  if (trimmedQuery) {
    params.set('query', trimmedQuery)
  }

  return requestJson<JobRecord[]>(`${path}?${params.toString()}`)
}

async function fetchHealth(): Promise<HealthResponse> {
  return requestJson<HealthResponse>('/api/health')
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

export function useJobDataHealth() {
  return useQuery({
    queryKey: ['jobDataHealth'],
    queryFn: fetchHealth,
    staleTime: 15_000,
  })
}
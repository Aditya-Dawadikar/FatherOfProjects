import { startTransition, useDeferredValue, useState } from 'react'
import { QueryClient, QueryClientProvider, useMutation, useQueryClient } from '@tanstack/react-query'
import './App.css'
import Header from './components/Header'
import JobForm from './components/JobForm'
import JobsTable from './components/JobsTable'
import {
  createEmptyDraft,
  createJob,
  deleteJob,
  toDraft,
  updateJob,
  useJobs,
} from './hooks'
import type { JobDraft, JobRecord } from './types'

const queryClient = new QueryClient()
const JOBS_QUERY_KEY = ['jobs']
const PAGE_SIZE = 20

function DashboardApp() {
  const [searchText, setSearchText] = useState('')
  const [page, setPage] = useState(1)
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null)
  const [editorMode, setEditorMode] = useState<'create' | 'edit'>('create')
  const [draft, setDraft] = useState<JobDraft>(() => createEmptyDraft())
  const [feedback, setFeedback] = useState<string>('')
  const deferredSearchText = useDeferredValue(searchText)
  const jobsQuery = useJobs({
    searchText: deferredSearchText,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  })
  const jobList = jobsQuery.data ?? []
  const selectedJob = jobList.find((job) => job.job_id === selectedJobId) ?? null
  const reactQueryClient = useQueryClient()
  const pageStart = jobList.length ? (page - 1) * PAGE_SIZE + 1 : 0
  const pageEnd = jobList.length ? pageStart + jobList.length - 1 : 0
  const hasNextPage = jobList.length === PAGE_SIZE

  const createMutation = useMutation({
    mutationFn: createJob,
    onSuccess: async (createdJob) => {
      setFeedback(`Created job ${createdJob.job_id}`)
      startTransition(() => {
        setSelectedJobId(createdJob.job_id)
        setEditorMode('edit')
      })
      setDraft(toDraft(createdJob))
      await reactQueryClient.invalidateQueries({ queryKey: JOBS_QUERY_KEY })
    },
  })

  const updateMutation = useMutation({
    mutationFn: updateJob,
    onSuccess: async (updatedJob) => {
      setFeedback(`Updated job ${updatedJob.job_id}`)
      setDraft(toDraft(updatedJob))
      await reactQueryClient.invalidateQueries({ queryKey: JOBS_QUERY_KEY })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deleteJob,
    onSuccess: async (_, jobId) => {
      setFeedback(`Deleted job ${jobId}`)
      startTransition(() => {
        setSelectedJobId(null)
        setEditorMode('create')
      })
      setDraft(createEmptyDraft())
      await reactQueryClient.invalidateQueries({ queryKey: JOBS_QUERY_KEY })
    },
  })

  const mutationError = createMutation.error ?? updateMutation.error ?? deleteMutation.error
  const busy = createMutation.isPending || updateMutation.isPending || deleteMutation.isPending

  function selectJob(job: JobRecord) {
    startTransition(() => {
      setSelectedJobId(job.job_id)
      setEditorMode('edit')
    })
    setDraft(toDraft(job))
    setFeedback('')
  }

  function resetForm() {
    startTransition(() => {
      setSelectedJobId(null)
      setEditorMode('create')
    })
    setDraft(createEmptyDraft())
    setFeedback('')
  }

  function updateDraft(field: keyof JobDraft, value: string) {
    setDraft((currentDraft) => ({
      ...currentDraft,
      [field]: value,
    }))
  }

  function submitDraft() {
    setFeedback('')
    if (!draft.job_id.trim() || !draft.company_name.trim() || !draft.job_role.trim()) {
      setFeedback('Job ID, company, and role are required.')
      return
    }

    if (editorMode === 'create') {
      createMutation.mutate(draft)
      return
    }

    updateMutation.mutate(draft)
  }

  function removeDraft() {
    if (!selectedJobId) {
      return
    }

    setFeedback('')
    deleteMutation.mutate(selectedJobId)
  }

  function removeJob(job: JobRecord) {
    setFeedback('')
    deleteMutation.mutate(job.job_id)
  }

  function changeSearchText(value: string) {
    setSearchText(value)
    setPage(1)
  }

  function goToPreviousPage() {
    setPage((currentPage) => Math.max(1, currentPage - 1))
  }

  function goToNextPage() {
    if (!hasNextPage || jobsQuery.isFetching) {
      return
    }

    setPage((currentPage) => currentPage + 1)
  }

  return (
    <div className="app-shell">
      <Header />

      <main className="app-body">
        <section className="content-panel">
          <div className="toolbar">
            <div className="toolbar-copy">
              <p className="eyebrow">Records</p>
              <h2>{jobsQuery.isLoading ? 'Loading jobs...' : `${jobList.length} records loaded`}</h2>
            </div>
            <div className="toolbar-actions">
              <input
                className="search-input"
                type="search"
                value={searchText}
                onChange={(event) => changeSearchText(event.target.value)}
                placeholder="Search company, role, or location"
              />
              <button
                type="button"
                className="ghost-button"
                onClick={() => jobsQuery.refetch()}
                disabled={jobsQuery.isFetching}
              >
                {jobsQuery.isFetching ? 'Refreshing...' : 'Refresh'}
              </button>
            </div>
          </div>

          <div className="summary-grid">
            <article className="summary-card">
              <span>Rows on page</span>
              <strong>{jobList.length}</strong>
            </article>
            <article className="summary-card">
              <span>Selected</span>
              <strong>{selectedJob?.company_name ?? (editorMode === 'edit' ? draft.company_name || 'Unsynced record' : 'None')}</strong>
            </article>
            <article className="summary-card">
              <span>Page window</span>
              <strong>{pageStart && pageEnd ? `${pageStart}-${pageEnd}` : '0'}</strong>
            </article>
          </div>

          {feedback && <div className="banner banner-info">{feedback}</div>}
          {mutationError && <div className="banner banner-error">{mutationError.message}</div>}
          {jobsQuery.error && <div className="banner banner-error">{jobsQuery.error.message}</div>}

          <JobsTable
            jobs={jobList}
            selectedJobId={selectedJobId}
            busy={busy}
            onSelectJob={selectJob}
            onDeleteJob={removeJob}
          />

          <div className="pagination-bar">
            <div className="pagination-copy">
              <span className="eyebrow">Pagination</span>
              <strong>Page {page}</strong>
            </div>
            <div className="pagination-actions">
              <button
                type="button"
                className="ghost-button"
                onClick={goToPreviousPage}
                disabled={page === 1 || jobsQuery.isFetching}
              >
                Previous
              </button>
              <button
                type="button"
                className="ghost-button"
                onClick={goToNextPage}
                disabled={!hasNextPage || jobsQuery.isFetching}
              >
                Next
              </button>
            </div>
          </div>
        </section>

        <JobForm
          draft={draft}
          mode={editorMode}
          busy={busy}
          onChange={updateDraft}
          onSubmit={submitDraft}
          onReset={resetForm}
          onDelete={removeDraft}
        />
      </main>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <DashboardApp />
    </QueryClientProvider>
  )
}
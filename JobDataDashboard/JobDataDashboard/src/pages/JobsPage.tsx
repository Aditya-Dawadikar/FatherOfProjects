import { startTransition, useDeferredValue, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { FiChevronLeft, FiChevronRight, FiPlus, FiRefreshCw, FiX } from 'react-icons/fi'
import JobForm from '../components/JobForm'
import JobsTable from '../components/JobsTable'
import {
  createEmptyDraft,
  createJob,
  deleteJob,
  toDraft,
  updateJob,
  useJobsCount,
  useJobs,
} from '../hooks'
import type { JobDraft, JobRecord } from '../types'

const JOBS_QUERY_KEY = ['jobs']
const PAGE_SIZE = 20

export default function JobsPage() {
  const [isFormDrawerOpen, setIsFormDrawerOpen] = useState(false)
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
  const jobsCountQuery = useJobsCount(deferredSearchText)
  const jobList = jobsQuery.data ?? []
  const reactQueryClient = useQueryClient()
  const totalRows = jobsCountQuery.data?.total ?? 0
  const totalPages = totalRows ? Math.ceil(totalRows / PAGE_SIZE) : 1
  const hasNextPage = page < totalPages

  const createMutation = useMutation({
    mutationFn: createJob,
    onSuccess: async (createdJob) => {
      setFeedback(`Created job ${createdJob.job_id}`)
      startTransition(() => {
        setSelectedJobId(createdJob.job_id)
        setEditorMode('edit')
      })
      setDraft(toDraft(createdJob))
      await Promise.all([
        reactQueryClient.invalidateQueries({ queryKey: JOBS_QUERY_KEY }),
        reactQueryClient.invalidateQueries({ queryKey: ['jobsCount'] }),
      ])
    },
  })

  const updateMutation = useMutation({
    mutationFn: updateJob,
    onSuccess: async (updatedJob) => {
      setFeedback(`Updated job ${updatedJob.job_id}`)
      setDraft(toDraft(updatedJob))
      await Promise.all([
        reactQueryClient.invalidateQueries({ queryKey: JOBS_QUERY_KEY }),
        reactQueryClient.invalidateQueries({ queryKey: ['jobsCount'] }),
      ])
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deleteJob,
    onSuccess: async (_, jobId) => {
      setFeedback(`Deleted job ${jobId}`)
      startTransition(() => {
        setSelectedJobId(null)
        setEditorMode('create')
        setIsFormDrawerOpen(false)
      })
      setDraft(createEmptyDraft())
      await Promise.all([
        reactQueryClient.invalidateQueries({ queryKey: JOBS_QUERY_KEY }),
        reactQueryClient.invalidateQueries({ queryKey: ['jobsCount'] }),
      ])
    },
  })

  const mutationError = createMutation.error ?? updateMutation.error ?? deleteMutation.error
  const busy = createMutation.isPending || updateMutation.isPending || deleteMutation.isPending

  function selectJob(job: JobRecord) {
    startTransition(() => {
      setSelectedJobId(job.job_id)
      setEditorMode('edit')
      setIsFormDrawerOpen(true)
    })
    setDraft(toDraft(job))
    setFeedback('')
  }

  function resetForm() {
    startTransition(() => {
      setSelectedJobId(null)
      setEditorMode('create')
      setIsFormDrawerOpen(true)
    })
    setDraft(createEmptyDraft())
    setFeedback('')
  }

  function openCreateForm() {
    resetForm()
  }

  function closeFormDrawer() {
    setIsFormDrawerOpen(false)
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
    <>
      <main className="app-body app-body-jobs">
        <section className="content-panel">
          <div className="toolbar records-toolbar">
            <div className="toolbar-copy">
              <p className="eyebrow">Records</p>
              <h2>{jobsQuery.isLoading ? 'Loading jobs...' : `${totalRows} total records`}</h2>
            </div>
            <div className="toolbar-actions">
              <button
                type="button"
                className="primary-button ghost-button-with-icon"
                onClick={openCreateForm}
              >
                <FiPlus aria-hidden="true" className="button-icon" />
                New Job
              </button>
              <input
                className="search-input"
                type="search"
                value={searchText}
                onChange={(event) => changeSearchText(event.target.value)}
                placeholder="Search company, role, or location"
              />
              <button
                type="button"
                className="ghost-button ghost-button-with-icon"
                onClick={() => jobsQuery.refetch()}
                disabled={jobsQuery.isFetching}
              >
                <FiRefreshCw
                  aria-hidden="true"
                  className={jobsQuery.isFetching ? 'button-icon spin' : 'button-icon'}
                />
                {jobsQuery.isFetching ? 'Refreshing...' : 'Refresh'}
              </button>
            </div>
          </div>

          {feedback && <div className="banner banner-info">{feedback}</div>}
          {mutationError && <div className="banner banner-error">{mutationError.message}</div>}
          {jobsQuery.error && <div className="banner banner-error">{jobsQuery.error.message}</div>}
          {jobsCountQuery.error && <div className="banner banner-error">{jobsCountQuery.error.message}</div>}

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
              <strong>Page {page} of {totalPages}</strong>
            </div>
            <div className="pagination-actions">
              <button
                type="button"
                className="ghost-button ghost-button-with-icon"
                onClick={goToPreviousPage}
                disabled={page === 1 || jobsQuery.isFetching}
              >
                <FiChevronLeft aria-hidden="true" className="button-icon" />
                Previous
              </button>
              <button
                type="button"
                className="ghost-button ghost-button-with-icon"
                onClick={goToNextPage}
                disabled={!hasNextPage || jobsQuery.isFetching}
              >
                <FiChevronRight aria-hidden="true" className="button-icon" />
                Next
              </button>
            </div>
          </div>
        </section>
      </main>

      {isFormDrawerOpen && (
        <button
          type="button"
          className="drawer-backdrop"
          aria-label="Close job form"
          onClick={closeFormDrawer}
        />
      )}

      <aside className={`job-form-drawer${isFormDrawerOpen ? ' is-open' : ''}`} aria-hidden={!isFormDrawerOpen}>
        <div className="job-form-drawer-header">
          <p className="eyebrow">{editorMode === 'create' ? 'Create' : 'Edit'}</p>
          <button
            type="button"
            className="ghost-button ghost-button-with-icon"
            onClick={closeFormDrawer}
          >
            <FiX aria-hidden="true" className="button-icon" />
            Close
          </button>
        </div>
        <JobForm
          draft={draft}
          mode={editorMode}
          busy={busy}
          onChange={updateDraft}
          onSubmit={submitDraft}
          onReset={resetForm}
          onDelete={removeDraft}
        />
      </aside>
    </>
  )
}

import { startTransition, useDeferredValue, useState } from 'react'
import { FiChevronLeft, FiChevronRight, FiRefreshCw, FiX } from 'react-icons/fi'
import MatchDetailPanel from './MatchDetailPanel'
import MatchesTable from './MatchesTable'
import { useMatchedJobs, useMatchedJobsCount, usePromptVersions, usePrompts } from '../hooks'
import type { MatchedJobRecord, MatchFilter } from '../types'

const PAGE_SIZE = 20

export default function MatchesView() {
  const [searchText, setSearchText] = useState('')
  const [matchFilter, setMatchFilter] = useState<MatchFilter>('matched')
  const [minScoreText, setMinScoreText] = useState('')
  const [promptVersion, setPromptVersion] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [selectedMatch, setSelectedMatch] = useState<MatchedJobRecord | null>(null)
  const [isDetailOpen, setIsDetailOpen] = useState(false)
  const deferredSearchText = useDeferredValue(searchText)
  const minScore = minScoreText.trim() ? Number(minScoreText) : null

  const promptVersionsQuery = usePromptVersions()
  const registeredPromptsQuery = usePrompts()
  const scoredVersions = promptVersionsQuery.data ?? []
  const registeredPrompts = registeredPromptsQuery.data ?? []

  // Union of every prompt version registered in MLflow with whatever scored-job counts
  // JobDataServer has recorded for it. scoredVersions alone (a GROUP BY over job_matches) only
  // lists versions that have already scored at least one job, so a version just registered via
  // the Migrations tab wouldn't appear here until a live/backfill cycle actually used it --
  // registeredPrompts fills in those zero-jobs-yet versions.
  const scoredByVersion = new Map(scoredVersions.map((version) => [version.prompt_version, version]))
  const allVersionIds = new Set([
    ...scoredVersions.map((version) => version.prompt_version),
    ...registeredPrompts.map((prompt) => prompt.version),
  ])
  const promptVersions = Array.from(allVersionIds)
    .sort((a, b) => Number(b) - Number(a))
    .map((version) => ({
      prompt_version: version,
      row_count: scoredByVersion.get(version)?.row_count ?? 0,
    }))

  // No explicit selection yet -- default to the most recently evaluated prompt_version, mirroring
  // the backend's own default (JobDataServer/main.py:resolve_prompt_version) so the filter shows
  // as "already applied" rather than looking unset. Falls back to the newest registered version
  // only if nothing has been scored at all yet.
  const effectivePromptVersion =
    promptVersion ?? scoredVersions[0]?.prompt_version ?? promptVersions[0]?.prompt_version ?? null

  const filters = { searchText: deferredSearchText, matchFilter, minScore, promptVersion: effectivePromptVersion }
  const matchesQuery = useMatchedJobs({ ...filters, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE })
  const matchesCountQuery = useMatchedJobsCount(filters)
  const globalMatchesCountQuery = useMatchedJobsCount({
    searchText: '',
    matchFilter: 'all',
    minScore: null,
    promptVersion: effectivePromptVersion,
  })

  const matches = matchesQuery.data ?? []
  const totalRows = matchesCountQuery.data?.total ?? 0
  const totalScoredJobs = globalMatchesCountQuery.data?.total ?? 0
  const totalPages = totalRows ? Math.ceil(totalRows / PAGE_SIZE) : 1
  const hasNextPage = page < totalPages

  function changeSearchText(value: string) {
    setSearchText(value)
    setPage(1)
  }

  function changeMatchFilter(value: MatchFilter) {
    setMatchFilter(value)
    setPage(1)
  }

  function changeMinScore(value: string) {
    setMinScoreText(value)
    setPage(1)
  }

  function changePromptVersion(value: string) {
    setPromptVersion(value || null)
    setPage(1)
  }

  function goToPreviousPage() {
    setPage((currentPage) => Math.max(1, currentPage - 1))
  }

  function goToNextPage() {
    if (!hasNextPage || matchesQuery.isFetching) {
      return
    }
    setPage((currentPage) => currentPage + 1)
  }

  function selectMatch(match: MatchedJobRecord) {
    startTransition(() => {
      setSelectedMatch(match)
      setIsDetailOpen(true)
    })
  }

  function closeDetail() {
    setIsDetailOpen(false)
  }

  return (
    <>
      <div className="toolbar records-toolbar">
        <div className="toolbar-copy">
          <p className="eyebrow">Processed by JobManagerAgent</p>
          <h2>{globalMatchesCountQuery.isLoading ? 'Loading matches...' : `${totalScoredJobs} scored jobs`}</h2>
        </div>
        <div className="toolbar-actions">
          <select
            className="search-input filter-select"
            value={effectivePromptVersion ?? ''}
            onChange={(event) => changePromptVersion(event.target.value)}
            disabled={(promptVersionsQuery.isLoading && registeredPromptsQuery.isLoading) || promptVersions.length === 0}
          >
            {promptVersions.length === 0 && <option value="">No prompt versions yet</option>}
            {promptVersions.map((version) => (
              <option key={version.prompt_version} value={version.prompt_version}>
                v{version.prompt_version} ({version.row_count > 0 ? `${version.row_count} jobs` : 'no jobs yet'})
              </option>
            ))}
          </select>
          <select
            className="search-input filter-select"
            value={matchFilter}
            onChange={(event) => changeMatchFilter(event.target.value as MatchFilter)}
          >
            <option value="all">All results</option>
            <option value="matched">Matched only</option>
            <option value="unmatched">Below threshold</option>
          </select>
          <input
            className="search-input min-score-input"
            type="number"
            min={0}
            max={100}
            value={minScoreText}
            onChange={(event) => changeMinScore(event.target.value)}
            placeholder="Min score"
          />
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
            onClick={() => matchesQuery.refetch()}
            disabled={matchesQuery.isFetching}
          >
            <FiRefreshCw
              aria-hidden="true"
              className={matchesQuery.isFetching ? 'button-icon spin' : 'button-icon'}
            />
            {matchesQuery.isFetching ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {matchesQuery.error && <div className="banner banner-error">{matchesQuery.error.message}</div>}
      {matchesCountQuery.error && <div className="banner banner-error">{matchesCountQuery.error.message}</div>}
      {globalMatchesCountQuery.error && <div className="banner banner-error">{globalMatchesCountQuery.error.message}</div>}
      {registeredPromptsQuery.error && <div className="banner banner-error">{registeredPromptsQuery.error.message}</div>}

      <MatchesTable matches={matches} selectedJobId={selectedMatch?.id ?? null} onSelectMatch={selectMatch} />

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
            disabled={page === 1 || matchesQuery.isFetching}
          >
            <FiChevronLeft aria-hidden="true" className="button-icon" />
            Previous
          </button>
          <button
            type="button"
            className="ghost-button ghost-button-with-icon"
            onClick={goToNextPage}
            disabled={!hasNextPage || matchesQuery.isFetching}
          >
            <FiChevronRight aria-hidden="true" className="button-icon" />
            Next
          </button>
        </div>
      </div>

      {isDetailOpen && (
        <button type="button" className="drawer-backdrop" aria-label="Close match detail" onClick={closeDetail} />
      )}

      <aside className={`job-form-drawer${isDetailOpen ? ' is-open' : ''}`} aria-hidden={!isDetailOpen}>
        <div className="job-form-drawer-header">
          <p className="eyebrow">Match detail</p>
          <button type="button" className="ghost-button ghost-button-with-icon" onClick={closeDetail}>
            <FiX aria-hidden="true" className="button-icon" />
            Close
          </button>
        </div>
        {selectedMatch && <MatchDetailPanel match={selectedMatch} />}
      </aside>
    </>
  )
}

import { useDeferredValue, useState } from 'react'
import { FiChevronLeft, FiChevronRight, FiRefreshCw } from 'react-icons/fi'
import MatchesTable from './MatchesTable'
import { useMatchedJobs, useMatchedJobsCount } from '../hooks'
import type { MatchFilter } from '../types'

const PAGE_SIZE = 20

export default function MatchesView() {
  const [searchText, setSearchText] = useState('')
  const [matchFilter, setMatchFilter] = useState<MatchFilter>('matched')
  const [minScoreText, setMinScoreText] = useState('')
  const [page, setPage] = useState(1)
  const deferredSearchText = useDeferredValue(searchText)
  const minScore = minScoreText.trim() ? Number(minScoreText) : null

  const filters = { searchText: deferredSearchText, matchFilter, minScore }
  const matchesQuery = useMatchedJobs({ ...filters, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE })
  const matchesCountQuery = useMatchedJobsCount(filters)
  const globalMatchesCountQuery = useMatchedJobsCount({ searchText: '', matchFilter: 'all', minScore: null })

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

  function goToPreviousPage() {
    setPage((currentPage) => Math.max(1, currentPage - 1))
  }

  function goToNextPage() {
    if (!hasNextPage || matchesQuery.isFetching) {
      return
    }
    setPage((currentPage) => currentPage + 1)
  }

  return (
    <section className="content-panel matches-panel">
      <div className="toolbar records-toolbar">
        <div className="toolbar-copy">
          <p className="eyebrow">Processed by JobManagerAgent</p>
          <h2>{globalMatchesCountQuery.isLoading ? 'Loading matches...' : `${totalScoredJobs} scored jobs`}</h2>
        </div>
        <div className="toolbar-actions">
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

      {/* <div className="summary-grid">
        <article className="summary-card">
          <span>Total scored</span>
          <strong>{totalRows}</strong>
        </article>
        <article className="summary-card">
          <span>Matched (this page)</span>
          <strong>{matchedOnPage} / {matches.length}</strong>
        </article>
        <article className="summary-card">
          <span>Avg score (this page)</span>
          <strong>{avgScoreOnPage ?? '-'}</strong>
        </article>
        <article className="summary-card">
          <span>Page window</span>
          <strong>{pageStart && pageEnd ? `${pageStart}-${pageEnd}` : '0'}</strong>
        </article>
      </div> */}

      {matchesQuery.error && <div className="banner banner-error">{matchesQuery.error.message}</div>}
      {matchesCountQuery.error && <div className="banner banner-error">{matchesCountQuery.error.message}</div>}
  {globalMatchesCountQuery.error && <div className="banner banner-error">{globalMatchesCountQuery.error.message}</div>}

      <MatchesTable matches={matches} />

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
    </section>
  )
}

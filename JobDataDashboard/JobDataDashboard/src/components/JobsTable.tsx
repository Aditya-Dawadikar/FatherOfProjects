import type { MouseEvent } from 'react'
import { FiTrash2 } from 'react-icons/fi'
import type { JobRecord } from '../types'

type JobsTableProps = {
  jobs: JobRecord[]
  selectedJobId: number | null
  busy: boolean
  onSelectJob: (job: JobRecord) => void
  onDeleteJob: (job: JobRecord) => void
}

function handleDeleteClick(
  event: MouseEvent<HTMLButtonElement>,
  job: JobRecord,
  onDeleteJob: JobsTableProps['onDeleteJob'],
) {
  event.stopPropagation()
  onDeleteJob(job)
}

export default function JobsTable({ jobs, selectedJobId, busy, onSelectJob, onDeleteJob }: JobsTableProps) {
  if (!jobs.length) {
    return (
      <div className="empty-state">
        <h2>No records found</h2>
        <p>Try a different search term or create a new record.</p>
      </div>
    )
  }

  return (
    <div className="table-wrap">
      <table className="jobs-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Source</th>
            <th>Company</th>
            <th>Role</th>
            <th>Location</th>
            <th>Type</th>
            <th>Updated</th>
            <th aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => {
            const selected = job.id === selectedJobId
            return (
              <tr
                key={job.id}
                className={selected ? 'is-selected' : undefined}
                onClick={() => onSelectJob(job)}
              >
                <td>{job.id}</td>
                <td>
                  <span className="source-badge">{job.source}</span>
                </td>
                <td>
                  <div className="company-cell">
                    <strong>{job.company_name}</strong>
                    <span>{job.company_batch ?? 'Batch n/a'}</span>
                  </div>
                </td>
                <td>{job.job_role}</td>
                <td>{job.location ?? 'Remote / n/a'}</td>
                <td>{job.job_type ?? 'n/a'}</td>
                <td>{new Date(job.updated_at).toLocaleString()}</td>
                <td className="row-actions-cell">
                  <button
                    type="button"
                    className="danger-button danger-button-compact ghost-button-with-icon"
                    disabled={busy}
                    onClick={(event) => handleDeleteClick(event, job, onDeleteJob)}
                  >
                    <FiTrash2 aria-hidden="true" className="button-icon" />
                    Delete
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
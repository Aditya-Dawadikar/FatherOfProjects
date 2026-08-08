import { useState } from 'react'
import { FiRotateCcw, FiZap } from 'react-icons/fi'
import { usePromptHistory, usePrompts, useRevertActivePrompt, useSetActivePrompt } from '../../hooks'

function formatDateTime(value: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleString()
}

// --- Feature flag -- active prompt version -----------------------------------------------------

export default function PromptVersionTab() {
  const promptsQuery = usePrompts()
  const historyQuery = usePromptHistory()
  const setActiveMutation = useSetActivePrompt()
  const revertMutation = useRevertActivePrompt()
  const [selectedVersion, setSelectedVersion] = useState('')

  const prompts = promptsQuery.data ?? []
  const active = prompts.find((prompt) => prompt.is_active)
  const settableVersions = prompts.filter((prompt) => prompt.schema_mode !== 'batch')

  function applyActiveVersion() {
    if (!selectedVersion) return
    setActiveMutation.mutate(selectedVersion, {
      onSuccess: () => {
        promptsQuery.refetch()
        historyQuery.refetch()
      },
    })
  }

  return (
    <section className="migration-section">
      <div className="toolbar">
        <div className="toolbar-copy">
          <p className="eyebrow">Feature flag</p>
          <h2>Active prompt version</h2>
        </div>
        <div className="toolbar-actions">
          <select
            className="search-input filter-select"
            value={selectedVersion}
            onChange={(event) => setSelectedVersion(event.target.value)}
            disabled={promptsQuery.isLoading}
          >
            <option value="">Select a version to activate...</option>
            {settableVersions.map((prompt) => (
              <option key={prompt.version} value={prompt.version}>
                v{prompt.version} · {prompt.schema_mode}
                {prompt.is_active ? ' (currently active)' : ''}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="primary-button ghost-button-with-icon"
            onClick={applyActiveVersion}
            disabled={!selectedVersion || setActiveMutation.isPending}
          >
            <FiZap aria-hidden="true" className="button-icon" />
            {setActiveMutation.isPending ? 'Setting active...' : 'Set active'}
          </button>
          <button
            type="button"
            className="ghost-button ghost-button-with-icon"
            onClick={() => revertMutation.mutate(undefined, { onSuccess: () => { promptsQuery.refetch(); historyQuery.refetch() } })}
            disabled={revertMutation.isPending}
          >
            <FiRotateCcw aria-hidden="true" className="button-icon" />
            {revertMutation.isPending ? 'Reverting...' : 'Revert to previous'}
          </button>
        </div>
      </div>

      {active && (
        <div className="banner banner-info">
          Production is currently <strong>v{active.version}</strong> ({active.schema_mode}, rubric v{active.rubric_version}).
          Batch-mode versions (schema_mode="batch") can never be set active -- they're backfill-only.
        </div>
      )}
      {setActiveMutation.isSuccess && (
        <div className="banner banner-info">
          Set active: v{setActiveMutation.data.version}. Takes effect on the next live/backfill cycle.
        </div>
      )}
      {setActiveMutation.error && <div className="banner banner-error">{setActiveMutation.error.message}</div>}
      {revertMutation.isSuccess && (
        <div className="banner banner-info">Reverted to v{revertMutation.data.version}. No data was purged.</div>
      )}
      {revertMutation.error && <div className="banner banner-error">{revertMutation.error.message}</div>}
      {promptsQuery.error && <div className="banner banner-error">{promptsQuery.error.message}</div>}

      <div className="table-wrap">
        <table className="jobs-table">
          <thead>
            <tr>
              <th>When</th>
              <th>From</th>
              <th>To</th>
              <th>Schema</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {(historyQuery.data ?? []).map((entry, index) => (
              <tr key={`${entry.changed_at}-${index}`}>
                <td>{formatDateTime(entry.changed_at)}</td>
                <td>{entry.from_version ? `v${entry.from_version}` : 'n/a (bootstrap)'}</td>
                <td>v{entry.to_version}</td>
                <td>{entry.schema_mode}</td>
                <td>{entry.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!historyQuery.isLoading && (historyQuery.data ?? []).length === 0 && (
          <div className="empty-state">
            <p>No prompt version changes recorded yet.</p>
          </div>
        )}
      </div>
    </section>
  )
}

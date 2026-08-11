import { useState } from 'react'
import { FiRefreshCw } from 'react-icons/fi'
import { useEvalDatasets } from '../../hooks'
import type { EvalDatasetKind } from '../../types'
import DatasetDetailModal from './DatasetDetailModal'

const KIND_LABEL: Record<EvalDatasetKind, string> = {
  prompt_matching: 'Prompt matching',
  guardrails: 'Guardrails',
  tool_selection: 'Tool selection',
  unknown: 'Unknown',
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  return `${(bytes / 1024).toFixed(1)} KB`
}

export default function DatasetsTab() {
  const datasetsQuery = useEvalDatasets()
  const datasets = datasetsQuery.data ?? []
  const [selectedDataset, setSelectedDataset] = useState<string | null>(null)

  return (
    <>
      <div className="toolbar">
        <div className="toolbar-copy">
          <p className="eyebrow">Reference</p>
          <h2>Eval datasets</h2>
        </div>
        <div className="toolbar-actions">
          <button
            type="button"
            className="ghost-button ghost-button-with-icon"
            onClick={() => datasetsQuery.refetch()}
            disabled={datasetsQuery.isFetching}
          >
            <FiRefreshCw aria-hidden="true" className={datasetsQuery.isFetching ? 'button-icon spin' : 'button-icon'} />
            Refresh
          </button>
        </div>
      </div>

      {datasetsQuery.error && <div className="banner banner-error">{datasetsQuery.error.message}</div>}
      <p className="match-detail-hint">
        Every golden-dataset JSONL file under evals/ (offline match evals, guardrails evals, and
        tool-selection evals, plus their .example.jsonl reference copies). Click a dataset to see
        its individual cases.
      </p>

      {datasets.length > 0 && (
        <div className="table-wrap">
          <table className="jobs-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Kind</th>
                <th>Cases</th>
                <th>Size</th>
                <th>Modified</th>
              </tr>
            </thead>
            <tbody>
              {datasets.map((dataset) => (
                <tr key={dataset.name} onClick={() => setSelectedDataset(dataset.name)}>
                  <td>
                    <strong>{dataset.name}</strong>
                  </td>
                  <td>
                    <span className="status-pill status-pill-sweep">{KIND_LABEL[dataset.kind]}</span>
                  </td>
                  <td>{dataset.case_count}</td>
                  <td>{formatSize(dataset.size_bytes)}</td>
                  <td>{new Date(dataset.modified_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!datasetsQuery.isLoading && datasets.length === 0 && (
        <div className="empty-state">
          <p>No eval datasets found.</p>
        </div>
      )}

      {selectedDataset && (
        <DatasetDetailModal name={selectedDataset} onClose={() => setSelectedDataset(null)} />
      )}
    </>
  )
}

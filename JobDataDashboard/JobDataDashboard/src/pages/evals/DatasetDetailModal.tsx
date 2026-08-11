import { useEffect } from 'react'
import { FiX } from 'react-icons/fi'
import { useEvalDatasetDetail } from '../../hooks'
import JsonTree from './JsonTree'

const KIND_LABEL: Record<string, string> = {
  prompt_matching: 'Prompt matching',
  guardrails: 'Guardrails',
  tool_selection: 'Tool selection',
  unknown: 'Unknown',
}

export default function DatasetDetailModal({ name, onClose }: { name: string; onClose: () => void }) {
  const detailQuery = useEvalDatasetDetail(name)
  const detail = detailQuery.data

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-panel"
        role="dialog"
        aria-modal="true"
        aria-label={`Dataset ${name}`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <div className="modal-header-copy">
            <h2>{name}</h2>
            <span className="eval-run-meta">
              {detail ? `${KIND_LABEL[detail.kind] ?? detail.kind} · ${detail.cases.length} cases` : 'Loading…'}
            </span>
          </div>
          <button type="button" className="modal-close-button" onClick={onClose} aria-label="Close">
            <FiX aria-hidden="true" />
          </button>
        </div>

        <div className="modal-body">
          {detailQuery.error && <div className="banner banner-error">{detailQuery.error.message}</div>}

          {detail && detail.parse_errors.length > 0 && (
            <div className="banner banner-error">
              <strong>{detail.parse_errors.length} line(s) failed to parse:</strong>
              <ul>
                {detail.parse_errors.map((error) => (
                  <li key={error}>{error}</li>
                ))}
              </ul>
            </div>
          )}

          {!detailQuery.isLoading && detail && detail.cases.length === 0 && (
            <div className="empty-state">
              <p>This dataset has no parseable cases.</p>
            </div>
          )}

          <div className="eval-run-list">
            {detail?.cases.map((datasetCase) => (
              <details key={datasetCase.line_number} className="eval-run-item">
                <summary className="eval-run-summary">
                  <span className="eval-run-name">{datasetCase.id ?? `line ${datasetCase.line_number}`}</span>
                  <span className="eval-run-meta">line {datasetCase.line_number}</span>
                </summary>
                <div className="eval-run-body">
                  <JsonTree value={datasetCase.data} />
                </div>
              </details>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

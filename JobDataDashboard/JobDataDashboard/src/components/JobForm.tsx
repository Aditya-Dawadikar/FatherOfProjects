import type { ChangeEvent } from 'react'
import { FiPlusCircle, FiRotateCcw, FiSave, FiTrash2 } from 'react-icons/fi'
import type { JobDraft } from '../types'

// id is server-generated (see JobDraft) and never rendered as an editable form field -- every
// FIELD_CONFIG entry is one of the remaining, always-string fields.
type EditableJobDraftField = Exclude<keyof JobDraft, 'id'>

type JobFormProps = {
  draft: JobDraft
  mode: 'create' | 'edit'
  busy: boolean
  onChange: (field: EditableJobDraftField, value: string) => void
  onSubmit: () => void
  onReset: () => void
  onDelete: () => void
}

type FieldConfig = {
  key: EditableJobDraftField
  label: string
  required?: boolean
  textarea?: boolean
}

const FIELD_CONFIG: FieldConfig[] = [
  { key: 'source', label: 'Source', required: true },
  { key: 'source_job_id', label: 'Source job ID', required: true },
  { key: 'company_name', label: 'Company', required: true },
  { key: 'job_role', label: 'Job role', required: true },
  { key: 'location', label: 'Location' },
  { key: 'job_type', label: 'Job type' },
  { key: 'role_type', label: 'Role type' },
  { key: 'salary_range', label: 'Salary range' },
  { key: 'company_batch', label: 'Batch' },
  { key: 'company_url', label: 'Company URL' },
  { key: 'job_url', label: 'Job URL' },
  { key: 'application_link', label: 'Application link' },
  { key: 'company_logo_url', label: 'Logo URL' },
  { key: 'company_last_active_at', label: 'Last active label' },
  { key: 'company_one_liner', label: 'Company summary', textarea: true },
]

function handleInputChange(
  event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
  onChange: JobFormProps['onChange'],
) {
  const field = event.target.name as EditableJobDraftField
  onChange(field, event.target.value)
}

export default function JobForm({ draft, mode, busy, onChange, onSubmit, onReset, onDelete }: JobFormProps) {
  return (
    <section className="form-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">{mode === 'create' ? 'Create' : 'Edit'}</p>
          <h2>{mode === 'create' ? 'New job record' : `Job ${draft.source}/${draft.source_job_id}`}</h2>
        </div>
        <button type="button" className="ghost-button ghost-button-with-icon" onClick={onReset}>
          <FiRotateCcw aria-hidden="true" className="button-icon" />
          {mode === 'create' ? 'Clear form' : 'New record'}
        </button>
      </div>

      <div className="form-grid">
        {FIELD_CONFIG.map((field) => {
          const sharedProps = {
            id: field.key,
            name: field.key,
            value: draft[field.key],
            required: field.required,
            disabled: busy || (mode === 'edit' && (field.key === 'source' || field.key === 'source_job_id')),
            onChange: (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => handleInputChange(event, onChange),
            placeholder: field.label,
          }

          return (
            <label key={field.key} className={field.textarea ? 'field field-span' : 'field'} htmlFor={field.key}>
              <span>{field.label}</span>
              {field.textarea ? <textarea rows={4} {...sharedProps} /> : <input type="text" {...sharedProps} />}
            </label>
          )
        })}
      </div>

      <div className="form-actions">
        <button type="button" className="primary-button ghost-button-with-icon" disabled={busy} onClick={onSubmit}>
          {mode === 'create' ? (
            <FiPlusCircle aria-hidden="true" className="button-icon" />
          ) : (
            <FiSave aria-hidden="true" className="button-icon" />
          )}
          {busy ? 'Saving...' : mode === 'create' ? 'Create record' : 'Save changes'}
        </button>
        {mode === 'edit' && (
          <button type="button" className="danger-button ghost-button-with-icon" disabled={busy} onClick={onDelete}>
            <FiTrash2 aria-hidden="true" className="button-icon" />
            Delete record
          </button>
        )}
      </div>
    </section>
  )
}
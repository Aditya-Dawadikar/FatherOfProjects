import type { MatchedJobRecord, ScoreBreakdown } from '../types'

type MatchDetailPanelProps = {
  match: MatchedJobRecord
}

type RawFieldConfig = {
  label: string
  value: string | null
}

const CRITERION_LABELS: Record<string, string> = {
  skills_match: 'Skills match',
  experience_fit: 'Experience fit',
  location_visa_fit: 'Location / visa fit',
  compensation_fit: 'Compensation fit',
  role_scope_fit: 'Role scope fit',
}

function criterionLabel(key: string) {
  return CRITERION_LABELS[key] ?? key
}

function rawFields(match: MatchedJobRecord): RawFieldConfig[] {
  return [
    { label: 'Role', value: match.job_role },
    { label: 'Company', value: match.company_name },
    { label: 'Location', value: match.location },
    { label: 'Job type', value: match.job_type },
    { label: 'Role type', value: match.role_type },
    { label: 'Salary range', value: match.salary_range },
  ]
}

function scoreBand(score: number): 'high' | 'mid' | 'low' {
  if (score >= 70) return 'high'
  if (score >= 40) return 'mid'
  return 'low'
}

function CriteriaGrid({ breakdown }: { breakdown: ScoreBreakdown }) {
  return (
    <div className="criteria-grid">
      {Object.entries(breakdown).map(([key, criterion]) => (
        <div key={key} className="criteria-row">
          <div className="criteria-row-header">
            <span className="criteria-name">{criterionLabel(key)}</span>
            <span className={`score-badge score-${scoreBand(criterion.score * 10)}`}>{criterion.score}/10</span>
          </div>
          <p className="criteria-reasoning">{criterion.reasoning || 'No reasoning provided.'}</p>
        </div>
      ))}
    </div>
  )
}

export default function MatchDetailPanel({ match }: MatchDetailPanelProps) {
  return (
    <section className="form-panel match-detail-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Job {match.job_id}</p>
          <h2>{match.job_role}</h2>
        </div>
        <span className={`score-badge score-${scoreBand(match.match_score)}`}>{match.match_score}</span>
      </div>

      <div className="match-detail-section">
        <h3>Raw job data</h3>
        <p className="match-detail-hint">
          Exactly what was sent into the scoring prompt -- job posting content is crawled fresh each time, not stored.
        </p>
        <dl className="match-detail-fields">
          {rawFields(match).map((field) => (
            <div key={field.label} className="match-detail-field">
              <dt>{field.label}</dt>
              <dd>{field.value || 'n/a'}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="match-detail-section">
        <h3>LLM score breakdown</h3>
        <div className="match-detail-fields">
          <div className="match-detail-field">
            <dt>Match</dt>
            <dd>
              <span className={`match-badge ${match.is_match ? 'match-badge-yes' : 'match-badge-no'}`}>
                {match.is_match ? 'Match' : 'No match'}
              </span>
            </dd>
          </div>
          <div className="match-detail-field">
            <dt>Prompt / model</dt>
            <dd>
              v{match.prompt_version} &middot; {match.model_name}
            </dd>
          </div>
        </div>
        <p className="match-detail-reasoning">{match.reasoning || 'No reasoning recorded.'}</p>

        {match.score_breakdown ? (
          <CriteriaGrid breakdown={match.score_breakdown} />
        ) : (
          <p className="match-detail-hint">
            This row was scored by a legacy prompt version with no per-criterion breakdown -- only the overall
            reasoning above is available.
          </p>
        )}
      </div>
    </section>
  )
}

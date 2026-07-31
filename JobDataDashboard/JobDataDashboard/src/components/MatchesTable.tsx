import type { MatchedJobRecord } from '../types'

type MatchesTableProps = {
  matches: MatchedJobRecord[]
}

function scoreBand(score: number): 'high' | 'mid' | 'low' {
  if (score >= 70) {
    return 'high'
  }
  if (score >= 40) {
    return 'mid'
  }
  return 'low'
}

export default function MatchesTable({ matches }: MatchesTableProps) {
  if (!matches.length) {
    return (
      <div className="empty-state">
        <h2>No scored jobs found</h2>
        <p>Try a different search term or filter -- or wait for JobManagerAgent to score more jobs.</p>
      </div>
    )
  }

  return (
    <div className="table-wrap">
      <table className="jobs-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Company</th>
            <th>Role</th>
            <th>Score</th>
            <th>Match</th>
            <th>Reasoning</th>
            <th>Prompt</th>
            <th>Model</th>
            <th>Evaluated</th>
          </tr>
        </thead>
        <tbody>
          {matches.map((match) => (
            <tr key={match.job_id}>
              <td>{match.job_id}</td>
              <td>
                <div className="company-cell">
                  <strong>{match.company_name}</strong>
                  <span>{match.location ?? 'Remote / n/a'}</span>
                </div>
              </td>
              <td>{match.job_role}</td>
              <td>
                <span className={`score-badge score-${scoreBand(match.match_score)}`}>{match.match_score}</span>
              </td>
              <td>
                <span className={`match-badge ${match.is_match ? 'match-badge-yes' : 'match-badge-no'}`}>
                  {match.is_match ? 'Match' : 'No match'}
                </span>
              </td>
              <td className="reasoning-cell" title={match.reasoning ?? ''}>
                {match.reasoning || 'n/a'}
              </td>
              <td>v{match.prompt_version}</td>
              <td>{match.model_name}</td>
              <td>{new Date(match.evaluated_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

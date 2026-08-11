// Renders an arbitrary JSON value as collapsible nested nodes. Eval dataset cases mix flat
// scalar fields (id, notes, expected_is_match) with deeply nested ones (job, expected_criteria,
// jobs[]) that don't flatten into a table row without either truncating or exploding into an
// unreadable number of columns -- this instead shows scalars inline immediately and lets nested
// objects/arrays be expanded on demand, depth by depth.

type JsonValue = unknown

function formatPrimitive(value: JsonValue): string {
  if (value === null) return 'null'
  if (value === undefined) return 'undefined'
  if (typeof value === 'string') return `"${value}"`
  return String(value)
}

function primitiveTypeClass(value: JsonValue): string {
  if (value === null) return 'json-value-null'
  return `json-value-${typeof value}`
}

export default function JsonTree({ label, value, depth = 0 }: { label?: string; value: JsonValue; depth?: number }) {
  if (value === null || typeof value !== 'object') {
    return (
      <div className="json-row" style={{ paddingLeft: depth * 14 }}>
        {label !== undefined && <span className="json-key">{label}:</span>}
        <span className={`json-value ${primitiveTypeClass(value)}`}>{formatPrimitive(value)}</span>
      </div>
    )
  }

  const isArray = Array.isArray(value)
  const entries: [string, JsonValue][] = isArray
    ? value.map((item, index) => [String(index), item])
    : Object.entries(value as Record<string, JsonValue>)

  if (entries.length === 0) {
    return (
      <div className="json-row" style={{ paddingLeft: depth * 14 }}>
        {label !== undefined && <span className="json-key">{label}:</span>}
        <span className="json-value json-value-empty">{isArray ? '[]' : '{}'}</span>
      </div>
    )
  }

  return (
    <details className="json-node" open={depth < 1}>
      <summary style={{ paddingLeft: depth * 14 }}>
        {label !== undefined && <span className="json-key">{label}</span>}
        <span className="json-type-hint">{isArray ? `Array(${entries.length})` : `Object(${entries.length})`}</span>
      </summary>
      <div className="json-children">
        {entries.map(([key, item]) => (
          <JsonTree key={key} label={isArray ? undefined : key} value={item} depth={depth + 1} />
        ))}
      </div>
    </details>
  )
}

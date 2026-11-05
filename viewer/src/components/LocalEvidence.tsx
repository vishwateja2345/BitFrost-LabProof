import type { LocalRecord, Run } from '../contracts';
import { display } from '../contracts';

export function LocalEvidence({ record, compact = false }: { record: LocalRecord; compact?: boolean }) {
  const observation = record.observation;
  return <section className="local-evidence" aria-label="Local execution lineage">
    <div className="badge-row"><span className="badge">Variant {observation.variant}</span><span className="badge">{record.phase}</span><span className="badge">{observation.tool} {observation.tool_version}</span></div>
    <dl className="lineage"><div><dt>Operation</dt><dd>{observation.operation_id}</dd></div><div><dt>Execution ID · reported</dt><dd className="mono">{record.execution_id}</dd></div><div><dt>Reset ID · reported</dt><dd className="mono">{record.reset_id}</dd></div></dl>
    {!compact && <><p className="note">Host-recorded lineage, not a browser attestation. Distinct IDs alone do not establish fresh execution, containment, or independent verification.</p>
      <h3>Normalized case observations</h3><div className="table-scroll" role="region" aria-label="Normalized case responses" tabIndex={0}><table className="case-table"><caption className="sr-only">Recorded case responses, not inferred pass or fail results.</caption><thead><tr><th scope="col">Case</th><th scope="col">Recorded response</th></tr></thead><tbody>{observation.cases.map(entry => <tr key={entry.case_id}><td className="mono">{entry.case_id}</td><td><pre>{display(entry.response)}</pre></td></tr>)}</tbody></table></div>{!observation.cases.length && <p className="muted small">No case responses recorded.</p>}
      <details><summary>Static AST signals ({observation.ast_nodes.length} recorded)</summary><p className="muted small">Static signals alone do not confirm flaws.</p><pre>{display(observation.ast_nodes)}</pre></details>
      <p className="small muted">Declared raw SHA-256 (not verified): <span className="mono digest">{observation.raw_sha256}</span></p></>}
  </section>;
}
export function RunProvenance({ run }: { run: Run }) {
  const provenance = run.report.provenance;
  return <section className="run-provenance" aria-label="Reported run provenance">
    <div className="badge-row"><span className="badge">{run.manifest.mode}</span>{run.report.pack_id !== undefined && <span className="badge">Pack: {display(run.report.pack_id)}</span>}</div>
    <p className="small muted">{run.manifest.mode === 'local' ? 'Reported local container observations with fixed catalogue decisions. Not model autonomy. Execution and containment are not independently attested by this browser.' : run.manifest.mode === 'replay' ? 'Synthetic / scripted replay. Not a measurement from a running service or a model benchmark.' : 'Reported live mode. Provider use and source authenticity are not independently attested by this browser.'}</p>
    {provenance !== null && typeof provenance === 'object' && !Array.isArray(provenance) && <dl className="provenance-fields">{Object.entries(provenance).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{display(value)}</dd></div>)}</dl>}
  </section>;
}

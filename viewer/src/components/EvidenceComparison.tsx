import { ArrowUpRight } from 'lucide-react';
import type { Evidence, Item, Run } from '../contracts';
import { display } from '../contracts';
import { LocalEvidence } from './LocalEvidence';

function hasRepeatedValue(values: string[]) {
  return new Set(values).size < values.length;
}

export function EvidenceComparison({ run, item, onInspect }: { run: Run; item: Item; onInspect: (evidence: Evidence) => void }) {
  const evidence = run.report.evidence.filter(e => item.evidence_ids.includes(e.id));
  const records = evidence.flatMap(e => e.record ? [e.record] : []);
  const sharedExecution = hasRepeatedValue(records.map(record => record.execution_id));
  const matchingCapture = hasRepeatedValue(records.map(record => record.observation.raw_text).filter(text => text.trim()));
  return <section aria-labelledby="comparison-title"><div className="section-heading compact"><h3 id="comparison-title">Observation & control comparison</h3></div>
    <div className="expectation-grid"><div><span className="field-label">Expected invariant</span><p>{display(item.expected)}</p></div><div><span className="field-label">Reported observation</span><p>{display(item.observed)}</p></div></div>
    <p className="muted small">Variant and control labels are supplied by the report; they are not independently verified.</p>
    {sharedExecution && <p className="note small">Multiple linked records share a reported execution ID.</p>}
    {matchingCapture && <p className="note small">Multiple linked records contain identical captured text. Compare their reported execution IDs for lineage.</p>}
    <div className="comparison-grid">{evidence.map(e => <article className="evidence-card" key={e.id}>
      {e.record ? <LocalEvidence record={e.record} compact /> : <div className="badge-row"><span className="badge">{display(e.variant, 'Variant not recorded')}</span><span className="badge">{display(e.control ?? e.phase, 'Control not recorded')}</span></div>}
      <h4>{display(e.title, e.id)}</h4><p className="excerpt">{display(e.content ?? e.response)}</p>
      <button className="text-button" onClick={() => onInspect(e)}>Inspect evidence <ArrowUpRight size={14} aria-hidden="true" /><span className="sr-only"> {e.id}</span></button>
    </article>)}</div>
    {!evidence.length && <p className="warning-text">No linked evidence recorded. A finding alone is not verification.</p>}
  </section>;
}

import { AlertTriangle } from 'lucide-react';
import type { Bundle, Run } from '../contracts';
import { projectName } from '../contracts';

export function LimitationsPanel({ runs, bundle }: { runs: Run[]; bundle?: Bundle }) {
  return <section className="panel limitations" aria-labelledby="limitations-heading">
    <div className="section-heading"><h2 id="limitations-heading"><AlertTriangle size={17} aria-hidden="true" /> Interpretation boundaries</h2><span className="eyebrow">Read before citing</span></div>
    <p>Schema and references are checked locally. Payload digests are <strong>not verified</strong> in this browser. Unsigned reports do not prove authenticity, completeness, or truth. Browser validation is not the independent domain verifier. An empty event list is not a domain-verified LabProof run.</p>
    <ul><li>Replay is synthetic / scripted, not a measured model benchmark. “Completed” describes a run, not a clean assessment.</li><li>Recorded controls and replays do not authorize new tests or establish exploitability beyond the retained observations.</li></ul>
    {bundle?.limitations && <div className="run-limitations"><h3>Bundle limitations</h3><ul>{bundle.limitations.map((line, i) => <li key={i}>{line}</li>)}</ul></div>}
    {bundle?.source_report_sha256 && <p>Recorded source report digest (not browser-verified): <span className="mono">{bundle.source_report_sha256}</span></p>}
    {runs.map(run => <div className="run-limitations" key={run.manifest.run_id}>
      <h3>{projectName(run.manifest.project_id)} <span className="mono">{run.manifest.run_id}</span></h3>
      {run.manifest.status !== 'completed' && <p className="warning-text">Run {run.manifest.status}: treat missing evidence as unknown, not a passing result.</p>}
      <ul>{[...new Set([...run.manifest.limitations, ...run.report.limitations])].map((line, i) => <li key={i}>{line}</li>)}</ul>
    </div>)}
  </section>;
}

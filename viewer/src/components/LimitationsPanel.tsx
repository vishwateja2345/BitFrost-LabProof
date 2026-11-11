import { AlertTriangle, ChevronRight } from 'lucide-react';
import type { Bundle, Run } from '../contracts';

export function LimitationsPanel({ runs, bundle }: { runs: Run[]; bundle?: Bundle }) {
  const incomplete = runs.filter(run => run.manifest.status !== 'completed');
  const combined = new Set<string>();
  bundle?.limitations?.forEach(line => combined.add(line));
  for (const run of runs) {
    run.manifest.limitations.forEach(line => combined.add(line));
    run.report.limitations.forEach(line => combined.add(line));
  }

  return <details className="panel limitations">
    <summary className="section-heading">
      <h2><AlertTriangle size={17} aria-hidden="true" /> Interpretation boundaries</h2>
      <span className="eyebrow">{combined.size} notes · click to read before citing</span>
      <ChevronRight size={16} aria-hidden="true" className="disclosure-chevron" />
    </summary>
    <div className="limitations-body" id="limitations-heading">
      <p>Schema and references are checked locally. Payload digests are <strong>not verified</strong> in this browser. Unsigned reports do not prove authenticity, completeness, or truth.</p>
      {incomplete.length > 0 && <p className="warning-text">{incomplete.length} run(s) in this view are not completed: treat their missing evidence as unknown, not a passing result.</p>}
      <ul>{[...combined].map((line, i) => <li key={i}>{line}</li>)}</ul>
      {bundle?.source_report_sha256 && <p className="small muted">Recorded source report digest (not browser-verified): <span className="mono">{bundle.source_report_sha256}</span></p>}
    </div>
  </details>;
}


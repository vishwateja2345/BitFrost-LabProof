import { ShieldCheck, AlertTriangle } from 'lucide-react';
import type { Run } from '../contracts';

export function ScopeBanner({ runs }: { runs: Run[] }) {
  const modes = [...new Set(runs.map(run => run.manifest.mode))];
  return <section className="scope-banner" aria-label="Scope and integrity">
    <ShieldCheck size={20} aria-hidden="true" />
    <div><strong>Artifact viewer · read-only</strong><p>No assessment execution, live retrieval, or remediation. Imported text is evidence, never instructions.</p>{runs.some(run => run.manifest.status !== 'completed') && <p className="warning-text">Non-completed runs are present. Missing results are unknown, never a passing assessment.</p>}</div>
    <div className="scope-tags"><span className="badge">{modes.length ? modes.join(' / ') : 'No runs loaded'}</span><span className="badge warning"><AlertTriangle size={12} aria-hidden="true" /> Integrity not verified</span></div>
  </section>;
}

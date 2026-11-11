import { useState } from 'react';
import type { Run } from '../contracts';
import { display } from '../contracts';
import { JsonRecord } from './JsonRecord';
import { StatusBadge } from './ResultsTable';

export function OriginalReport({ run }: { run: Run }) {
  const [showArtifacts, setShowArtifacts] = useState(false);
  const { manifest, report } = run;
  return <section className="original-run">
    <div className="section-heading">
      <h3>{report.title}</h3>
      <StatusBadge status={manifest.status} />
    </div>
    <p>{report.summary}</p>
    <dl className="report-meta">
      <div><dt>Run</dt><dd className="mono">{manifest.run_id}</dd></div>
      <div><dt>Pack / mode</dt><dd>{display(report.pack_id, manifest.mode)}</dd></div>
      <div><dt>Report format</dt><dd className="mono">{display(report.schema_version, 'Legacy replay')}</dd></div>
    </dl>
    <JsonRecord label="Original report JSON" filename={`${manifest.run_id}-report.json`} value={report} />
    <JsonRecord label="Manifest JSON" filename={`${manifest.run_id}-manifest.json`} value={manifest} />
    <details className="json-record" onToggle={event => setShowArtifacts(event.currentTarget.open)}>
      <summary>Registered files ({manifest.artifacts.length})</summary>
      {showArtifacts && <div className="table-scroll" role="region" aria-label="Declared artifact digests" tabIndex={0}>
        <table className="artifact-index">
          <thead><tr><th scope="col">Path</th><th scope="col">Bytes</th><th scope="col">Declared SHA-256</th></tr></thead>
          <tbody>{manifest.artifacts.map(artifact => <tr key={artifact.path}>
            <td className="mono">{artifact.path}</td><td className="numeric">{artifact.bytes.toLocaleString('en-US')}</td>
            <td className="mono digest">{artifact.sha256}</td>
          </tr>)}</tbody>
        </table>
      </div>}
    </details>
  </section>;
}

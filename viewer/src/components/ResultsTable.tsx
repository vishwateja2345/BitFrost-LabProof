import type { Item, Run } from '../contracts';
import { itemStatus, itemTitle } from '../contracts';
import { ArrowUpRight } from 'lucide-react';

export interface ResultRow { run: Run; item: Item }
export const resultKey = (row: ResultRow) => `${row.run.manifest.run_id}/${row.item.id}`;
export function StatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  const tone = /stale|contradicted|confirmed|vulnerable|failed/.test(normalized) ? 'warning' : /supported|pass|refuted|not_detected/.test(normalized) ? 'positive' : '';
  return <span className={`badge status ${tone}`}>{status.replaceAll('_', ' ')}</span>;
}
export function ResultsTable({ rows, selected, onSelect }: { rows: ResultRow[]; selected: string | null; onSelect: (row: ResultRow) => void }) {
  return <div className="table-scroll" role="region" aria-label="Research results" tabIndex={0}><table className="results-table">
    <caption className="sr-only">Findings. Select a result to inspect its evidence.</caption>
    <thead><tr><th scope="col">Finding</th><th scope="col">Run</th><th scope="col">Reported result</th><th scope="col">Evidence</th></tr></thead>
    <tbody>{rows.map(row => <tr key={resultKey(row)} className={selected === resultKey(row) ? 'selected' : ''}>
      <td><span className="record-id mono">{row.item.id}</span><button className="result-button" onClick={() => onSelect(row)} aria-pressed={selected === resultKey(row)}>{itemTitle(row.item)}<ArrowUpRight size={15} aria-hidden="true" /></button></td>
      <td><span className="project-label labproof">{row.run.manifest.mode}</span><span className="record-id">{typeof row.run.report.pack_id === 'string' ? row.run.report.pack_id : row.run.manifest.run_id}</span></td>
      <td><StatusBadge status={itemStatus(row.item)} /></td><td className="numeric">{row.item.evidence_ids.length}<span className="muted"> linked</span></td>
    </tr>)}</tbody>
  </table>{rows.length === 0 && <div className="empty-state"><h3>No matching results</h3><p>Try a different run, search, or result filter.</p></div>}</div>;
}

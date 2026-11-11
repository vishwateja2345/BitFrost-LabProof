import type { Item, Run } from '../contracts';
import { display, itemStatus, itemTitle } from '../contracts';
import { ChevronRight } from 'lucide-react';

export interface ResultRow { run: Run; item: Item }
export const resultKey = (row: ResultRow) => `${row.run.manifest.run_id}/${row.item.id}`;
export function StatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  const tone = ['stale', 'contradicted', 'confirmed', 'vulnerable', 'failed', 'blocked', 'incomplete'].includes(normalized) ? 'warning'
    : ['supported', 'pass', 'refuted', 'not_detected', 'rejected', 'completed'].includes(normalized) ? 'positive' : '';
  return <span className={`badge status ${tone}`}>{status.replaceAll('_', ' ')}</span>;
}
export function ResultsTable({ rows, selected, onSelect }: { rows: ResultRow[]; selected: string | null; onSelect: (row: ResultRow) => void }) {
  return <div className="table-scroll" role="region" aria-label="Research results" tabIndex={0}><table className="results-table">
    <caption className="sr-only">Findings. Select a result to inspect its evidence.</caption>
    <thead><tr><th scope="col">Finding</th><th scope="col">Reported result</th><th scope="col">Evidence</th></tr></thead>
    <tbody>{rows.map(row => <tr key={resultKey(row)} className={selected === resultKey(row) ? 'selected' : ''}>
      <td><button className="result-button" onClick={() => onSelect(row)} aria-pressed={selected === resultKey(row)}>
        <span>{itemTitle(row.item)}</span><ChevronRight size={15} aria-hidden="true" />
      </button><span className="record-id">{display(row.run.report.pack_id, row.run.manifest.mode)}{typeof row.item.variant === 'string' && ` · ${row.item.variant}`}</span></td>
      <td><StatusBadge status={itemStatus(row.item)} /></td><td className="numeric">{row.item.evidence_ids.length}</td>
    </tr>)}</tbody>
  </table>{rows.length === 0 && <div className="empty-state"><h3>No matching results</h3><p>Try a different run, search, or result filter.</p></div>}</div>;
}

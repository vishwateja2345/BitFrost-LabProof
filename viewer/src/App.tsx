import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowDownToLine, ArrowRight, Check, ChevronDown, FileJson, FlaskConical, Search, Upload } from 'lucide-react';
import type { Bundle, Evidence, Run } from './contracts';
import { display, itemsFor, itemStatus, itemTitle, MAX_BUNDLE_BYTES, parseBundle, projectName, readBundleResponse } from './contracts';
import { ScopeBanner } from './components/ScopeBanner';
import { LimitationsPanel } from './components/LimitationsPanel';
import { EvidenceInspector } from './components/EvidenceInspector';
import { EvidenceComparison } from './components/EvidenceComparison';
import { RunProvenance } from './components/LocalEvidence';
import { ExperimentDetails } from './components/ExperimentDetails';
import { ResultsTable, resultKey, StatusBadge } from './components/ResultsTable';
import type { ResultRow } from './components/ResultsTable';
import { product } from './product';

type View = 'results' | 'evidence' | 'trace' | 'original';
const views: { id: View; label: string }[] = [
  { id: 'results', label: 'Results' }, { id: 'evidence', label: 'Evidence ledger' },
  { id: 'trace', label: 'Run trace' }, { id: 'original', label: 'Original reports' },
];

export default function App() {
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [source, setSource] = useState('No artifact bundle');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [runId, setRunId] = useState('all');
  const [view, setView] = useState<View>('results');
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('all');
  const [selected, setSelected] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const detailRef = useRef<HTMLElement>(null);
  const loadId = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    const id = ++loadId.current;
    fetch('./demo.json', { signal: controller.signal, credentials: 'omit', redirect: 'error' })
      .then(readBundleResponse).then(data => {
        if (loadId.current !== id) return;
        setBundle(data); setSource('Bundled demo'); setError('');
      }).catch((reason: unknown) => {
        if (!controller.signal.aborted && loadId.current === id) setError(reason instanceof Error ? reason.message : 'Could not read the demo bundle.');
      }).finally(() => { if (loadId.current === id) setLoading(false); });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      const target = event.target;
      if (event.key === '/' && !event.ctrlKey && !event.metaKey && !(target instanceof HTMLElement && (target.matches('input, textarea, select') || target.isContentEditable)) && !evidence) {
        event.preventDefault(); searchRef.current?.focus();
      }
    };
    window.addEventListener('keydown', listener);
    return () => window.removeEventListener('keydown', listener);
  }, [evidence]);

  async function importBundle(file: File | undefined) {
    if (!file) return;
    const id = ++loadId.current;
    setLoading(true); setError('');
    try {
      if (file.size > MAX_BUNDLE_BYTES) throw new Error('Bundle exceeds the 5 MiB upload limit.');
      const imported = parseBundle(await file.text());
      if (loadId.current !== id) return;
      setBundle(imported); setSource(file.name); setSelected(null); setEvidence(null); setSearch(''); setStatus('all'); setRunId('all');
    } catch (reason) { if (loadId.current === id) setError(reason instanceof Error ? reason.message : 'Unable to read this file.'); }
    finally { if (loadId.current === id) setLoading(false); if (fileRef.current) fileRef.current.value = ''; }
  }
  const allRuns = useMemo(() => bundle?.runs ?? [], [bundle]);
  const scopedRuns = useMemo(() => allRuns.filter(run => runId === 'all' || run.manifest.run_id === runId), [allRuns, runId]);
  const allRows = useMemo(() => scopedRuns.flatMap(run => itemsFor(run).map(item => ({ run, item }))), [scopedRuns]);
  const statuses = [...new Set(allRows.map(row => itemStatus(row.item)))].sort();
  const query = search.trim().toLowerCase();
  const rows = allRows.filter(row => (status === 'all' || itemStatus(row.item) === status) && (!query || JSON.stringify({ project: row.run.manifest.project_id, run: row.run.manifest.run_id, item: row.item, evidence: row.run.report.evidence.filter(e => row.item.evidence_ids.includes(e.id)) }).toLowerCase().includes(query)));
  const current = rows.find(row => resultKey(row) === selected) ?? rows[0] ?? null;
  const filteredRuns = scopedRuns.filter(run => rows.some(row => row.run === run) || (status === 'all' && query && JSON.stringify(run).toLowerCase().includes(query)));
  const visibleRuns = query || status !== 'all' ? filteredRuns : scopedRuns;
  const evidenceRows = visibleRuns.flatMap(run => run.report.evidence.filter(e => {
    if (status !== 'all' && !rows.some(row => row.run === run && row.item.evidence_ids.includes(e.id))) return false;
    return !query || JSON.stringify(e).toLowerCase().includes(query) || rows.some(row => row.run === run && row.item.evidence_ids.includes(e.id));
  }).map(record => ({ run, record })));

  function choose(row: ResultRow) {
    setSelected(resultKey(row));
    requestAnimationFrame(() => detailRef.current?.focus({ preventScroll: true }));
  }
  return <>
    <a href="#workspace" className="skip-link">Skip to workspace</a>
    <header className="topbar"><div className="topbar-inner">
      <a className="brand" href="#"><span className="brand-mark" aria-hidden="true">{product.mark}<span>⸬</span></span><span>{product.brand}<span className="brand-sub">{product.subtitle}</span></span></a>
      <div className="topbar-right"><span className="read-only"><span className="status-dot" /> Read-only session</span><button className="button secondary" onClick={() => fileRef.current?.click()}><Upload size={15} aria-hidden="true" /> Import bundle</button></div>
      <input ref={fileRef} className="sr-only" type="file" accept=".json,application/json" aria-label="Import JSON bundle" onChange={event => void importBundle(event.target.files?.[0])} tabIndex={-1} />
    </div></header>
    <main id="workspace" className="workspace" tabIndex={-1}>
      <div className="breadcrumb"><span>Workspace</span><span>/</span><span>Evidence review</span><span className="version">Contract v1.0</span></div>
      <section className="hero"><div><p className="eyebrow">Observe, compare, verify</p><h1>{product.heading}</h1><p className="hero-copy">{product.introduction}<br className="desktop-break" /> Trace every conclusion back to what was actually recorded.</p></div><div className="hero-stamp"><span>Evidence first<br />Authority never</span></div></section>
      <ScopeBanner runs={scopedRuns} />
      {error && <div className="error-banner" role="alert"><strong>{bundle ? 'Import failed. Previous bundle retained.' : 'No bundle loaded.'}</strong> {error}</div>}
      <div className="workspace-toolbar"><span className="file-origin"><FileJson size={14} aria-hidden="true" /><span title={source}>{source}</span>{bundle && <span className="schema-check"><Check size={13} aria-hidden="true" /> Schema checked</span>}</span></div>
      <div className="filter-bar"><label className="search"><Search size={17} aria-hidden="true" /><span className="sr-only">Search artifacts</span><input ref={searchRef} value={search} onChange={event => setSearch(event.target.value)} placeholder={product.search} /><kbd aria-hidden="true">/</kbd></label>
        <label className="status-filter run-filter"><span className="sr-only">Pack and run</span><select value={runId} onChange={event => { setRunId(event.target.value); setStatus('all'); setSelected(null); }}><option value="all">All packs / runs ({allRuns.length})</option>{allRuns.map(run => <option key={run.manifest.run_id} value={run.manifest.run_id}>{projectName(run.manifest.project_id)} · {display(run.report.pack_id, run.manifest.mode)} · {run.manifest.run_id}</option>)}</select><ChevronDown size={14} aria-hidden="true" /></label>
        <label className="status-filter"><span className="sr-only">Result status</span><select value={status} onChange={event => setStatus(event.target.value)}><option value="all">All reported results</option>{statuses.map(value => <option key={value} value={value}>{value.replaceAll('_', ' ')}</option>)}</select><ChevronDown size={14} aria-hidden="true" /></label>
        {(search || status !== 'all' || runId !== 'all') && <button className="text-button" onClick={() => { setSearch(''); setStatus('all'); setRunId('all'); }}>Clear filters</button>}
      </div>
      <section className="summary-grid single-product" aria-label="Filtered artifact inventory">
        <Inventory label="LabProof findings" value={rows.length} description="Reported lab observations" />
        <Inventory label="Evidence records" value={evidenceRows.length} description="Captured records in this view" />
        <Inventory label="Runs in view" value={visibleRuns.length} description={`${visibleRuns.filter(run => run.manifest.status !== 'completed').length} not completed · no inferred passes`} />
      </section>
      <section className="panel research-panel" aria-label="Artifact workspace" aria-busy={loading}>
        <div className="panel-nav"><div role="group" aria-label="Artifact view">{views.map(({ id, label }) => <button key={id} aria-pressed={view === id} onClick={() => setView(id)}>{label}</button>)}</div><span className="eyebrow">{loading ? 'Reading artifact…' : 'Local artifact review'}</span></div>
        {!bundle ? <div className="empty-state initial"><FlaskConical size={34} strokeWidth={1} aria-hidden="true" /><h2>{loading ? 'Opening the evidence workspace' : 'Your artifacts belong here'}</h2><p>Import a {product.importLabel} JSON bundle.<br />Files stay in your browser. Maximum 5 MiB.</p><p className="small muted">Local execution-pack archives cannot be imported or run here. Replay, local-report-1, and local-report-2 artifacts are supported through the v1 JSON bundle contract. Unknown domain versions are rejected; the browser is not an independent artifact verifier.</p><button className="button primary" onClick={() => fileRef.current?.click()}><ArrowDownToLine size={15} aria-hidden="true" /> Choose a bundle</button></div> : <>
          {view === 'results' && <><div className="content-heading"><div><h2>Assessment findings</h2><p>Reported conclusions, with their original evidence preserved.</p></div><span className="badge">{rows.length} records</span></div><ResultsTable rows={rows} selected={current ? resultKey(current) : null} onSelect={choose} /></>}
          {view === 'evidence' && <><div className="content-heading"><div><h2>Evidence ledger</h2><p>Captured content, provenance, and control labels. No payload execution.</p></div><span className="badge">{evidenceRows.length} records</span></div><div className="ledger">{evidenceRows.map(({ run, record }) => <article key={`${run.manifest.run_id}/${record.id}`}><div><span className="record-id mono">{record.id} · {projectName(run.manifest.project_id)}</span><h3>{display(record.title, record.id)}</h3><p className="excerpt">{display(record.content ?? record.response)}</p></div><button className="button secondary" onClick={() => setEvidence(record)}>Inspect<span className="sr-only"> {record.id}</span><ArrowRight size={14} aria-hidden="true" /></button></article>)}{!evidenceRows.length && <div className="empty-state">No evidence matches this view.</div>}</div></>}
          {view === 'trace' && <div className="trace-view"><h2>Recorded run trace</h2><p className="muted">Event order is schema-checked. The browser does not attest that these actions occurred.</p>{visibleRuns.map(run => <section key={run.manifest.run_id}><div className="section-heading"><h3>{projectName(run.manifest.project_id)} <span className="mono small">{run.manifest.run_id}</span></h3><StatusBadge status={run.manifest.status} /></div><ol className="timeline">{run.events.map(event => <li key={event.sequence}><span className="sequence mono">{event.sequence.toString().padStart(2, '0')}</span><div><strong>{event.type.replaceAll('_', ' ')}</strong><time className="mono small" dateTime={event.timestamp}>{event.timestamp}</time><details><summary>Event data</summary><pre>{display(event.data)}</pre></details></div></li>)}</ol>{!run.events.length && <p className="warning-text">No events recorded.</p>}</section>)}</div>}
          {view === 'original' && <div className="original-view"><h2>Original report records</h2><p className="muted">Read-only records. Digests below are declared, not verified.</p>{visibleRuns.map(run => <OriginalReport key={run.manifest.run_id} run={run} />)}</div>}
        </>}
      </section>
      {view === 'results' && current && <section ref={detailRef} tabIndex={-1} className="panel result-detail" aria-labelledby="detail-title"><div className="section-heading"><span className="eyebrow accent">Selected record · {projectName(current.run.manifest.project_id)}</span><StatusBadge status={itemStatus(current.item)} /></div><span className="mono record-id">{current.item.id} · {current.run.manifest.run_id}</span><h2 id="detail-title">{itemTitle(current.item)}</h2>
        <RunProvenance run={current.run} />
        {Array.isArray(current.item.limitations) && <ul className="finding-limitations">{current.item.limitations.map((line, index) => <li key={index}>{display(line)}</li>)}</ul>}
        <EvidenceComparison run={current.run} item={current.item} onInspect={setEvidence} />
        <details className="raw-record"><summary>All original record fields</summary><pre>{JSON.stringify(current.item, null, 2)}</pre></details>
      </section>}
      {visibleRuns.map(run => <ExperimentDetails key={run.manifest.run_id} run={run} />)}
      <LimitationsPanel runs={visibleRuns} bundle={bundle ?? undefined} />
      <footer><span className="brand-footer">{product.brand} <span>/ evidence workspace</span></span><a href="#limitations-heading">{product.guide}</a><span>{bundle ? `Bundle generated ${bundle.generated_at}` : 'Offline-first · no execution authority'}</span></footer>
    </main>
    <EvidenceInspector evidence={evidence} onClose={() => setEvidence(null)} />
  </>;
}
function Inventory({ label, value, description }: { label: string; value: number; description: string }) {
  return <div className="inventory-card"><div className="inventory-label">{label}</div><strong className="inventory-value">{value}</strong><p>{description}</p></div>;
}
function OriginalReport({ run }: { run: Run }) {
  return <section className="original-run"><div className="section-heading"><h3>{run.report.title}</h3><StatusBadge status={run.manifest.status} /></div><p>{run.report.summary}</p><div className="badge-row"><span className="badge">{projectName(run.manifest.project_id)}</span><span className="badge">{run.manifest.mode}</span><span className="mono small">{run.manifest.run_id}</span></div><details><summary>Original report JSON</summary><pre>{JSON.stringify(run.report, null, 2)}</pre></details><details><summary>Manifest & declared artifact digests</summary><p className="warning-text">Integrity not verified. This viewer does not fetch or hash referenced artifact files.</p><pre>{JSON.stringify(run.manifest, null, 2)}</pre></details></section>;
}

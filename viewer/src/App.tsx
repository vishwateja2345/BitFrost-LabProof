import { useEffect, useMemo, useRef, useState } from 'react';
import { Activity, ArrowDownToLine, ArrowRight, Check, ChevronDown, ClipboardList, FileJson, Files, FlaskConical, Layers, ListTree, RotateCcw, Search, ShieldCheck, Upload } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
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
const views: { id: View; label: string; icon: LucideIcon }[] = [
  { id: 'results', label: 'Results', icon: ClipboardList }, { id: 'evidence', label: 'Evidence ledger', icon: Layers },
  { id: 'trace', label: 'Run trace', icon: ListTree }, { id: 'original', label: 'Original reports', icon: FileJson },
];

export default function App() {
  const [active, setActive] = useState<{ bundle: Bundle; filename?: string } | null>(null);
  const bundle = active?.bundle ?? null;
  const source = active ? active.filename ?? 'Bundled demo' : 'No artifact bundle';
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
  const demoRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    void openDemo();
    return () => demoRequest.current?.abort();
  }, []);

  async function openDemo() {
    demoRequest.current?.abort();
    const controller = new AbortController();
    demoRequest.current = controller;
    const id = ++loadId.current;
    setLoading(true); setError('');
    try {
      const response = await fetch('./demo.json', { signal: controller.signal, credentials: 'omit', redirect: 'error' });
      const data = await readBundleResponse(response);
      if (!controller.signal.aborted && loadId.current === id) activateBundle(data);
    } catch (reason) {
      if (!controller.signal.aborted && loadId.current === id) setError(reason instanceof Error ? reason.message : 'Could not read the demo bundle.');
    } finally {
      if (!controller.signal.aborted && loadId.current === id) setLoading(false);
    }
  }

  function activateBundle(bundle: Bundle, filename?: string) {
    setActive({ bundle, filename }); setSelected(null); setEvidence(null);
    setSearch(''); setStatus('all'); setRunId('all'); setView('results');
  }

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
    demoRequest.current?.abort();
    const id = ++loadId.current;
    setLoading(true); setError('');
    try {
      if (file.size > MAX_BUNDLE_BYTES) throw new Error('Bundle exceeds the 5 MiB upload limit.');
      const imported = parseBundle(await file.text());
      if (loadId.current !== id) return;
      activateBundle(imported, file.name);
    } catch (reason) { if (loadId.current === id) setError(reason instanceof Error ? reason.message : 'Unable to read this file.'); }
    finally {
      if (loadId.current === id) {
        setLoading(false);
        if (fileRef.current) fileRef.current.value = '';
      }
    }
  }
  const allRuns = useMemo(() => bundle?.runs ?? [], [bundle]);
  const scopedRuns = useMemo(() => allRuns.filter(run => runId === 'all' || run.manifest.run_id === runId), [allRuns, runId]);
  const statuses = useMemo(() => [...new Set(scopedRuns.flatMap(run => itemsFor(run).map(itemStatus)))].sort(), [scopedRuns]);
  const query = search.trim().toLowerCase();
  const { rows, visibleRuns, evidenceRows } = useMemo(() => filterArtifacts(scopedRuns, status, query), [scopedRuns, status, query]);
  const current = rows.find(row => resultKey(row) === selected) ?? rows[0] ?? null;

  function choose(row: ResultRow) {
    setSelected(resultKey(row));
    requestAnimationFrame(() => {
      const detail = detailRef.current;
      if (!detail) return;
      detail.focus({ preventScroll: true });
      if (window.matchMedia?.('(max-width: 960px)').matches || detail.getBoundingClientRect().top < 0) {
        detail.scrollIntoView({ block: 'start' });
      }
    });
  }
  const incompleteRuns = visibleRuns.filter(run => run.manifest.status !== 'completed').length;
  const confirmed = rows.filter(row => itemStatus(row.item) === 'confirmed').length;

  return <>
    <a href="#workspace" className="skip-link">Skip to workspace</a>
    <header className="topbar">
      <div className="topbar-inner">
        <a className="brand" href="#workspace">
          <span className="brand-mark"><ShieldCheck aria-hidden="true" /></span>
          <span>{product.brand}<span className="brand-sub">{product.subtitle}</span></span>
        </a>
        <div className="topbar-right">
          <span className="read-only"><span className="status-dot" /> Read-only viewer</span>
          <button className="button primary" onClick={() => fileRef.current?.click()}>
            <Upload size={15} aria-hidden="true" /> Import bundle
          </button>
        </div>
        <input ref={fileRef} className="sr-only" type="file" accept=".json,application/json"
          aria-label="Import JSON bundle" onChange={event => void importBundle(event.target.files?.[0])} tabIndex={-1} />
      </div>
    </header>

    <main id="workspace" className="workspace" tabIndex={-1}>
      <section className="hero">
        <div>
          <h1>{product.heading}</h1>
          <p className="hero-copy">{product.introduction}</p>
        </div>
        <div className="bundle-source">
          <span className="bundle-icon"><FileJson aria-hidden="true" /></span>
          <div className="bundle-info">
            <span className="field-label">Active bundle</span>
            <strong title={source}>{source}</strong>
          </div>
          {bundle && <span className="schema-check"><Check aria-hidden="true" /> Schema checked</span>}
          {active?.filename !== undefined && <button type="button" className="text-button demo-button" disabled={loading} onClick={() => void openDemo()}>
            <RotateCcw aria-hidden="true" /> Open demo
          </button>}
        </div>
      </section>

      <ScopeBanner runs={scopedRuns} />
      {error && <div className="error-banner" role="alert">
        <strong>{bundle ? 'Could not open bundle. Previous bundle retained.' : 'No bundle loaded.'}</strong> {error}
      </div>}

      {bundle && <section className="summary-grid" aria-label="Filtered artifact inventory">
        <Inventory icon={ClipboardList} label="Reported findings" value={rows.length} description={`${confirmed} confirmed`} />
        <Inventory icon={Layers} label="Evidence records" value={evidenceRows.length} description="Captured records in view" />
        <Inventory icon={Activity} label="Runs in view" value={visibleRuns.length} description={`${incompleteRuns} unfinished · ${visibleRuns.length - incompleteRuns} completed`} />
      </section>}

      <section className="panel research-panel" aria-label="Artifact workspace" aria-busy={loading}>
        {!bundle ? <div className="empty-state initial">
          <FlaskConical size={34} strokeWidth={1} aria-hidden="true" />
          <h2>{loading ? 'Opening the evidence workspace' : 'Your artifacts belong here'}</h2>
          <p>Import a {product.importLabel} JSON bundle up to 5 MiB. Files stay in your browser.</p>
          <p className="small muted">Local execution-pack archives cannot be imported or run here. The viewer accepts replay, local-report-1, and local-report-2 records in a version 1.0 bundle.</p>
          <div className="empty-actions">
            <button className="button primary" onClick={() => fileRef.current?.click()}><ArrowDownToLine aria-hidden="true" /> Choose a bundle</button>
            {!loading && <button className="button secondary" onClick={() => void openDemo()}><RotateCcw aria-hidden="true" /> Retry demo</button>}
          </div>
        </div> : <>
          <div className="panel-nav">
            <div role="group" aria-label="Artifact view">
              {views.map(({ id, label, icon: Icon }) => <button key={id} aria-pressed={view === id} onClick={() => setView(id)}>
                <Icon aria-hidden="true" /> {label}
              </button>)}
            </div>
            {loading && <span className="small muted" role="status">Opening bundle…</span>}
          </div>
          <div className="filter-bar">
            <label className="search"><Search size={17} aria-hidden="true" /><span className="sr-only">Search artifacts</span>
              <input ref={searchRef} value={search} onChange={event => setSearch(event.target.value)} placeholder={product.search} />
              <kbd aria-hidden="true">/</kbd>
            </label>
            <label className="status-filter run-filter"><span className="sr-only">Pack and run</span>
              <select value={runId} onChange={event => { setRunId(event.target.value); setStatus('all'); setSelected(null); }}>
                <option value="all">All runs ({allRuns.length})</option>
                {allRuns.map(run => <option key={run.manifest.run_id} value={run.manifest.run_id}>
                  {display(run.report.pack_id, run.manifest.mode)} · {run.manifest.run_id}
                </option>)}
              </select>
              <ChevronDown size={14} aria-hidden="true" />
            </label>
            <label className="status-filter"><span className="sr-only">Result status</span>
              <select value={status} onChange={event => setStatus(event.target.value)}>
                <option value="all">All statuses</option>
                {statuses.map(value => <option key={value} value={value}>{value.replaceAll('_', ' ')}</option>)}
              </select>
              <ChevronDown size={14} aria-hidden="true" />
            </label>
            {(search || status !== 'all' || runId !== 'all') && <button className="text-button" onClick={() => { setSearch(''); setStatus('all'); setRunId('all'); }}>Clear filters</button>}
          </div>

          {view === 'results' && <div className={current ? 'results-layout' : undefined}>
            <div className="results-list">
              <div className="content-heading"><h2>Assessment findings</h2><span className="badge">{rows.length} records</span></div>
              <ResultsTable rows={rows} selected={current ? resultKey(current) : null} onSelect={choose} />
            </div>
            {current && <section key={resultKey(current)} ref={detailRef} tabIndex={-1} className="result-detail" aria-labelledby="detail-title">
              <div className="section-heading"><span className="eyebrow"><Files aria-hidden="true" /> Selected finding</span><StatusBadge status={itemStatus(current.item)} /></div>
              <h2 id="detail-title">{itemTitle(current.item)}</h2>
              <span className="mono record-id">{current.item.id} · {current.run.manifest.run_id}</span>
              <EvidenceComparison run={current.run} item={current.item} onInspect={setEvidence} />
              <RunProvenance run={current.run} />
              {Array.isArray(current.item.limitations) && <ul className="finding-limitations">{current.item.limitations.map((line, index) => <li key={index}>{display(line)}</li>)}</ul>}
              <details className="raw-record"><summary>All original record fields</summary><pre>{JSON.stringify(current.item, null, 2)}</pre></details>
            </section>}
          </div>}
          {view === 'evidence' && <>
            <div className="content-heading"><h2>Evidence ledger</h2><span className="badge">{evidenceRows.length} records</span></div>
            <div className="ledger">
              {evidenceRows.map(({ run, record }) => <article key={`${run.manifest.run_id}/${record.id}`}>
                <div><span className="record-id mono">{record.id} · {display(run.report.pack_id, run.manifest.mode)}</span>
                  <h3>{display(record.title, record.id)}</h3><p className="excerpt">{display(record.content ?? record.response)}</p>
                </div>
                <button className="button secondary" onClick={() => setEvidence(record)}>Inspect<span className="sr-only"> {record.id}</span><ArrowRight aria-hidden="true" /></button>
              </article>)}
              {!evidenceRows.length && <div className="empty-state">No evidence matches this view.</div>}
            </div>
          </>}
          {view === 'trace' && <div className="trace-view">
            <h2>Recorded run trace</h2>
            <p className="muted">Event order is schema-checked. The browser does not attest that these actions occurred.</p>
            {!visibleRuns.length && <div className="empty-state">No runs match this view.</div>}
            {visibleRuns.map(run => <section key={run.manifest.run_id}>
              <div className="section-heading"><h3>{display(run.report.pack_id, run.manifest.mode)} <span className="mono small">{run.manifest.run_id}</span></h3><StatusBadge status={run.manifest.status} /></div>
              <ol className="timeline">{run.events.map(event => <li key={event.sequence}>
                <span className="sequence mono">{event.sequence.toString().padStart(2, '0')}</span>
                <div><strong>{event.type.replaceAll('_', ' ')}</strong><time className="mono small" dateTime={event.timestamp}>{event.timestamp}</time>
                  <details><summary>Event data</summary><pre>{display(event.data)}</pre></details>
                </div>
              </li>)}</ol>
              {!run.events.length && <p className="warning-text">No events recorded.</p>}
            </section>)}
          </div>}
          {view === 'original' && <div className="original-view">
            <h2>Original report records</h2><p className="muted">Digests below are declared by the bundle.</p>
            {!visibleRuns.length && <div className="empty-state">No reports match this view.</div>}
            {visibleRuns.map(run => <OriginalReport key={run.manifest.run_id} run={run} />)}
          </div>}
        </>}
      </section>
      {visibleRuns.map(run => <ExperimentDetails key={run.manifest.run_id} run={run} />)}
      <LimitationsPanel runs={visibleRuns} bundle={bundle ?? undefined} />
      <footer><span className="brand-footer">{product.brand}</span><a href="#limitations-heading">{product.guide}</a>{bundle && <span>Bundle generated <time dateTime={bundle.generated_at}>{bundle.generated_at}</time></span>}</footer>
    </main>
    <EvidenceInspector evidence={evidence} onClose={() => setEvidence(null)} />
  </>;
}

function filterArtifacts(runs: Run[], status: string, query: string) {
  const rows: ResultRow[] = [];
  const visibleRuns: Run[] = [];
  const evidenceRows: { run: Run; record: Evidence }[] = [];
  const matches = (value: unknown) => JSON.stringify(value).toLowerCase().includes(query);

  for (const run of runs) {
    const records = run.report.evidence;
    const matchingEvidence = new Set(query ? records.filter(matches).map(record => record.id) : []);
    const matchesRun = query && [run.manifest.project_id, run.manifest.run_id, run.manifest.mode, run.report.pack_id]
      .some(value => typeof value === 'string' && value.toLowerCase().includes(query));
    const findings = itemsFor(run).filter(item =>
      (status === 'all' || itemStatus(item) === status) &&
      (!query || matchesRun || matches(item) || item.evidence_ids.some(id => matchingEvidence.has(id))));

    if (!findings.length && (status !== 'all' || (query && !matches(run)))) continue;
    visibleRuns.push(run);
    rows.push(...findings.map(item => ({ run, item })));

    const linked = new Set(findings.flatMap(item => item.evidence_ids));
    for (const record of records) {
      if (linked.has(record.id) || (status === 'all' && (!query || matchesRun || matchingEvidence.has(record.id)))) {
        evidenceRows.push({ run, record });
      }
    }
  }

  return { rows, visibleRuns, evidenceRows };
}

function Inventory({ icon: Icon, label, value, description }: { icon: LucideIcon; label: string; value: number; description: string }) {
  return <div className="inventory-card">
    <span className="inventory-icon"><Icon aria-hidden="true" /></span>
    <div className="inventory-label">{label}</div>
    <strong className="inventory-value">{value}</strong>
    <p>{description}</p>
  </div>;
}

function OriginalReport({ run }: { run: Run }) {
  return <section className="original-run"><div className="section-heading"><h3>{run.report.title}</h3><StatusBadge status={run.manifest.status} /></div><p>{run.report.summary}</p><div className="badge-row"><span className="badge">{projectName(run.manifest.project_id)}</span><span className="badge">{run.manifest.mode}</span><span className="mono small">{run.manifest.run_id}</span></div><details><summary>Original report JSON</summary><pre>{JSON.stringify(run.report, null, 2)}</pre></details><details><summary>Manifest & declared artifact digests</summary><p className="warning-text">Integrity not verified. This viewer does not fetch or hash referenced artifact files.</p><pre>{JSON.stringify(run.manifest, null, 2)}</pre></details></section>;
}

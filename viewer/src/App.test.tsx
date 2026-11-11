import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { EvidenceInspector, SourceLink } from './components/EvidenceInspector';
import { LimitationsPanel } from './components/LimitationsPanel';
import { validateBundle } from './contracts';
import { fixture } from './test-fixture';
import bundledReview from '../public/review.json';
import directBrief from '../../evidence/live-brief-03/direct/brief.json';

function mockDownload(value: unknown = fixture()) {
  const bytes = new TextEncoder().encode(JSON.stringify(value));
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, headers: { get: () => null }, body: new ReadableStream({ start(controller) { controller.enqueue(bytes); controller.close(); } }) }));
}

beforeEach(() => { mockDownload(); });
afterEach(() => { vi.unstubAllGlobals(); });

describe('artifact workspace', () => {
  it('opens retained citations from a confirmed finding and returns to its run', async () => {
    mockDownload(bundledReview);
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'View cited remediation' }));
    expect(screen.getByRole('heading', { name: 'Remediation brief' })).toBeInTheDocument();
    expect(screen.getByText('Retained live provider run')).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: /broken object level authorization/i })[0]).toHaveAttribute('rel', 'noopener noreferrer');
    fireEvent.click(screen.getByRole('button', { name: 'Synthetic cross-user object authorization' }));
    expect(screen.getByRole('combobox', { name: 'Pack and run' })).toHaveValue(bundledReview.remediation.source_run.run_id);
    expect(screen.getByRole('button', { name: 'View cited remediation' })).toBeInTheDocument();
  });

  it('loads real-shaped data, scopes results, and never claims integrity', async () => {
    render(<App />);
    expect(await screen.findByRole('button', { name: 'Synthetic observation' })).toBeInTheDocument();
    expect(screen.getByText('Integrity not verified')).toBeInTheDocument();
    expect(screen.getByText('Schema checked')).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledWith('./review.json', expect.objectContaining({ credentials: 'omit', redirect: 'error' }));
  });
  it('keeps every run available through the pack/run selector', async () => {
    const value = fixture();
    const second = structuredClone(value.runs[0]);
    second.manifest.run_id = 'lp-second'; second.report.run_id = 'lp-second';
    second.events.forEach(event => { event.run_id = 'lp-second'; });
    value.runs.push(second);
    mockDownload(value);
    render(<App />);
    await screen.findByRole('option', { name: /lp-second/ });
    fireEvent.change(screen.getByRole('combobox', { name: 'Pack and run' }), { target: { value: 'lp-second' } });
    expect(screen.getAllByRole('button', { name: 'Synthetic observation' })).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
    expect(screen.getAllByRole('button', { name: 'Synthetic observation' })).toHaveLength(2);
  });
  it('supports keyboard search and result filtering', async () => {
    render(<App />);
    await screen.findByRole('button', { name: 'Synthetic observation' });
    fireEvent.keyDown(document.body, { key: '/' });
    expect(screen.getByRole('textbox', { name: 'Search artifacts' })).toHaveFocus();
    fireEvent.change(screen.getByRole('textbox', { name: 'Search artifacts' }), { target: { value: 'does-not-exist' } });
    expect(screen.getByText('No matching results')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
    fireEvent.change(screen.getByRole('combobox', { name: 'Result status' }), { target: { value: 'inconclusive' } });
    expect(screen.getByRole('button', { name: 'Synthetic observation' })).toBeInTheDocument();
  });
  it('keeps linked controls in view when a search matches captured evidence', async () => {
    const value = fixture();
    const report = value.runs[0].report;
    report.evidence.push({ ...report.evidence[0], id: 'e2', title: 'Second control', content: 'Different capture' });
    report.findings[0].evidence_ids.push('e2');
    mockDownload(value);
    render(<App />);
    await screen.findByRole('button', { name: 'Synthetic observation' });
    fireEvent.change(screen.getByRole('textbox', { name: 'Search artifacts' }), { target: { value: 'untrusted' } });
    expect(screen.getByRole('button', { name: 'Synthetic observation' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Evidence ledger' }));
    expect(screen.getByRole('heading', { name: 'Captured control' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Second control' })).toBeInTheDocument();
  });
  it('does not silently replace an unavailable saved review with sample data', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
    render(<App />);
    expect(await screen.findByRole('alert')).toHaveTextContent('No bundle loaded');
    expect(screen.getByText('Open an evidence bundle')).toBeInTheDocument();
    expect(screen.getByText(/Local execution-pack archives cannot be imported or run here/)).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it('shows bundle caveats and labels its recorded source hash as unverified', async () => {
    const value = { ...fixture(), limitations: ['Do not promote a source finding.'], source_report_sha256: 'b'.repeat(64) };
    mockDownload(value);
    render(<App />);
    expect(await screen.findByText('Do not promote a source finding.')).toBeInTheDocument();
    expect(screen.getByText('b'.repeat(64))).toBeInTheDocument();
    expect(screen.getByText(/Recorded source report digest \(not browser-verified\)/)).toBeInTheDocument();
  });
  it('retains the previous valid bundle if upload validation fails', async () => {
    render(<App />);
    await screen.findByRole('button', { name: 'Synthetic observation' });
    const file = new File(['{}'], 'invalid.json', { type: 'application/json' });
    Object.defineProperty(file, 'arrayBuffer', { value: async () => new TextEncoder().encode('{}').buffer });
    fireEvent.change(screen.getByLabelText('Import JSON bundle'), { target: { files: [file] } });
    expect(await screen.findByRole('alert')).toHaveTextContent('Previous bundle retained');
    expect(screen.getByRole('button', { name: 'Synthetic observation' })).toBeInTheDocument();
  });
  it('returns to the saved review and clears the imported bundle view', async () => {
    render(<App />);
    await screen.findByText('Saved lab review');
    const raw = JSON.stringify(fixture());
    const file = new File([raw], 'review.json', { type: 'application/json' });
    Object.defineProperty(file, 'arrayBuffer', { value: async () => new TextEncoder().encode(raw).buffer });
    fireEvent.change(screen.getByLabelText('Import JSON bundle'), { target: { files: [file] } });
    await screen.findByText('review.json');
    fireEvent.change(screen.getByRole('textbox', { name: 'Search artifacts' }), { target: { value: 'missing' } });
    fireEvent.click(screen.getByRole('button', { name: 'Run trace' }));
    expect(screen.getByText('No runs match this view.')).toBeInTheDocument();
    mockDownload();
    fireEvent.click(screen.getByRole('button', { name: 'Open saved review' }));
    await screen.findByText('Saved lab review');
    expect(screen.getByRole('button', { name: 'Results' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('textbox', { name: 'Search artifacts' })).toHaveValue('');
  });
  it('renders incomplete run limitations and original records without inferring a pass', async () => {
    const value = fixture();
    value.runs = [value.runs[0]];
    value.runs[0].manifest.status = 'incomplete'; value.runs[0].events = [];
    mockDownload(value);
    render(<App />);
    expect(await screen.findByText(/run\(s\) in this view are not completed/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Run trace' }));
    expect(screen.getByText('No events recorded.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Original reports' }));
    expect(screen.getByText('Original report JSON')).toBeInTheDocument();
  });
});

describe('remediation bundle validation', () => {
  it('accepts an actual direct Tavily brief alongside the retained relay brief', () => {
    const direct = validateBundle({ ...bundledReview, remediation: directBrief }).remediation;
    expect(direct?.searchVia).toBe('tavily');
    expect(direct?.classes[0].recommendations).toHaveLength(1);
  });

  it('rejects wrong run bindings, fabricated quotations, and citation host lookalikes', () => {
    const wrongRun = structuredClone(bundledReview);
    wrongRun.remediation.source_run.report_sha256 = '0'.repeat(64);
    expect(() => validateBundle(wrongRun)).toThrow('does not match a completed bundled run');

    const wrongQuote = structuredClone(bundledReview);
    wrongQuote.remediation.classes[0].recommendations[0].quotes[0].quote = 'Unrelated wording presented as a retained quotation';
    expect(() => validateBundle(wrongQuote)).toThrow('quotation missing');

    const wrongHost = structuredClone(bundledReview);
    wrongHost.remediation.classes[0].sources[0].url = 'https://owasp.org.example.com/';
    expect(() => validateBundle(wrongHost)).toThrow('citation host outside');
  });

  it('rejects a class whose title/severity/reason has been relabeled away from the fixed catalogue', () => {
    // Same check_id, same genuinely-confirmed finding -- only the displayed severity/title/reason
    // is tampered with, as if to misrepresent a real finding's class (e.g. inflate its severity).
    const relabeled = structuredClone(bundledReview);
    relabeled.remediation.classes[0].severity = 'low';
    expect(() => validateBundle(relabeled)).toThrow('does not match the fixed catalogue');

    const retitled = structuredClone(bundledReview);
    retitled.remediation.classes[0].title = 'Totally different, made-up finding title';
    expect(() => validateBundle(retitled)).toThrow('does not match the fixed catalogue');
  });

  it('rejects a class check_id that does not match its own catalogue entry', () => {
    // An unknown/garbage check_id must never be accepted just because it carries a confirmed finding ID.
    const unknownCheck = structuredClone(bundledReview);
    unknownCheck.remediation.classes[0].check_id = 'not_a_real_check';
    expect(() => validateBundle(unknownCheck)).toThrow('unknown remediation class');
  });
});

describe('untrusted evidence rendering', () => {
  it('escapes captured HTML and exposes an accessible modal', async () => {
    const onClose = vi.fn();
    const { container } = render(<EvidenceInspector evidence={{ id: 'evil', title: 'Untrusted record', content: '<img src=x onerror=alert(1)>', url: 'javascript:alert(1)' }} onClose={onClose} />);
    expect(screen.getByRole('dialog')).toHaveAccessibleName('Untrusted record');
    expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeInTheDocument();
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('a')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Close evidence inspector' }));
    await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
  });
  it('wraps Tab and Shift+Tab inside the evidence dialog', () => {
    render(<EvidenceInspector evidence={{ id: 'focus', title: 'Focus record', content: 'text', url: 'https://docs.example.org' }} onClose={() => undefined} />);
    const close = screen.getByRole('button', { name: 'Close evidence inspector' });
    const link = screen.getByRole('link');
    close.focus();
    fireEvent.keyDown(close, { key: 'Tab', shiftKey: true });
    expect(link).toHaveFocus();
    fireEvent.keyDown(link, { key: 'Tab' });
    expect(close).toHaveFocus();
  });
  it('adds external navigation protections and blocks credentials', () => {
    const { rerender } = render(<SourceLink url="https://docs.example.org/path" />);
    expect(screen.getByRole('link')).toHaveAttribute('rel', 'noopener noreferrer');
    expect(screen.getByRole('link')).toHaveAttribute('referrerpolicy', 'no-referrer');
    rerender(<SourceLink url="https://user:pass@docs.example.org/path" />);
    expect(screen.queryByRole('link')).toBeNull();
  });
  it('keeps trust boundaries visible even with no runs', () => {
    render(<LimitationsPanel runs={validateBundle({ schema_version: '1.0', generated_at: '2026-11-01T00:00:00Z', runs: [] }).runs} />);
    expect(screen.getByText(/Unsigned reports do not prove authenticity/)).toBeInTheDocument();
  });
});

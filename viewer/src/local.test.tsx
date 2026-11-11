import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { validateBundle } from './contracts';
import { fixture } from './test-fixture';
import { LocalEvidence, RunProvenance } from './components/LocalEvidence';
import { EvidenceComparison } from './components/EvidenceComparison';

function localFixture(): Record<string, any> {
  const bundle: Record<string, any> = fixture();
  bundle.runs = [bundle.runs[0]]; bundle.annotations = [];
  const run = bundle.runs[0];
  run.manifest.mode = 'local'; run.report.mode = 'local';
  run.report.schema_version = 'local-report-1'; run.report.pack_id = 'python';
  run.report.provenance = { observations: 'local_container', decisions: 'fixed_catalogue', model: 'not_used', verification: 'fresh_container_reexecution' };
  const evidence = run.report.evidence[0];
  evidence.content = 'Synthetic unit test raw observation';
  evidence.record = { id: evidence.id, phase: 'observation', execution_id: 'execution-unit-test', reset_id: 'reset-unit-test', observation: {
    schema_version: 'parsed-worker-observation-1', operation_id: 'python-invariants', tool: 'unittest', tool_version: 'unit-test', variant: 'alpha', raw_text: evidence.content, raw_sha256: 'a'.repeat(64), ast_nodes: [], cases: [{ case_id: 'case-01', response: { status: 200, body: '<script>untrusted</script>' } }],
  } };
  return bundle;
}
describe('local-report-1 artifact support', () => {
  it('validates and renders normalized cases and declared lineage without verification claims', () => {
    const run = validateBundle(localFixture()).runs[0];
    render(<><RunProvenance run={run} /><LocalEvidence record={run.report.evidence[0].record!} /></>);
    expect(screen.getByText('Pack: python')).toBeInTheDocument();
    expect(screen.getByText('execution-unit-test')).toBeInTheDocument();
    expect(screen.getByText('reset-unit-test')).toBeInTheDocument();
    expect(screen.getByText('case-01')).toBeInTheDocument();
    expect(screen.getByText(/Distinct IDs alone do not establish fresh execution/)).toBeInTheDocument();
    expect(document.querySelector('script')).toBeNull();
  });
  it('distinguishes shared reported execution from matching capture text', () => {
    const bundle = localFixture();
    const report = bundle.runs[0].report;
    const [first] = report.evidence;
    const second = structuredClone(first);
    second.id = second.record.id = 'second-evidence';
    second.record.execution_id = 'second-execution';
    report.evidence.push(second);
    report.findings[0].evidence_ids.push(second.id);

    const comparison = () => {
      const run = validateBundle(bundle).runs[0];
      return <EvidenceComparison run={run} item={run.report.findings![0]} onInspect={() => undefined} />;
    };
    const { rerender } = render(comparison());
    expect(screen.getByText(/contain identical captured text/)).toBeInTheDocument();
    expect(screen.queryByText(/share a reported execution ID/)).toBeNull();

    second.record.execution_id = first.record.execution_id;
    second.content = second.record.observation.raw_text = 'Different capture with the same declared digest';
    rerender(comparison());
    expect(screen.getByText(/share a reported execution ID/)).toBeInTheDocument();
    expect(screen.queryByText(/contain identical captured text/)).toBeNull();
  });
  it.each([
    ['unsupported report version', (b: any) => { b.runs[0].report.schema_version = 'local-report-2'; }],
    ['missing record', (b: any) => { delete b.runs[0].report.evidence[0].record; }],
    ['identity mismatch', (b: any) => { b.runs[0].report.evidence[0].record.id = 'other'; }],
    ['missing reset', (b: any) => { delete b.runs[0].report.evidence[0].record.reset_id; }],
    ['unsupported observation version', (b: any) => { b.runs[0].report.evidence[0].record.observation.schema_version = 'unsupported'; }],
    ['raw text mismatch', (b: any) => { b.runs[0].report.evidence[0].content = 'changed'; }],
    ['duplicate cases', (b: any) => { const o = b.runs[0].report.evidence[0].record.observation; o.cases.push(o.cases[0]); }],
    ['missing cases array', (b: any) => { delete b.runs[0].report.evidence[0].record.observation.cases; }],
    ['invalid digest', (b: any) => { b.runs[0].report.evidence[0].record.observation.raw_sha256 = 'bad'; }],
  ])('rejects %s', (_name, change) => { const bundle = localFixture(); change(bundle); expect(() => validateBundle(bundle)).toThrow(); });
  it('keeps incomplete local reports viewable with required empty arrays', () => {
    const bundle = localFixture(); const run = bundle.runs[0]; run.manifest.status = 'incomplete'; run.events = []; run.report.evidence = []; run.report.findings = [];
    expect(validateBundle(bundle).runs[0].manifest.status).toBe('incomplete');
  });
});

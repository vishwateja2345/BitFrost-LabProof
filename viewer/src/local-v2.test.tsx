import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import actualBlocked from './fixtures/labproof-blocked-v2.json';
import inventedCompleted from './fixtures/labproof-completed-v2-invented.json';
import { validateBundle } from './contracts';
import { ExperimentDetails } from './components/ExperimentDetails';
import { fixture } from './test-fixture';

// Retained actual producer export: unprovisioned/blocked, no executed workers.
function blocked(): Record<string, any> { return structuredClone(actualBlocked); }
describe('LabProof local-report-2', () => {
  it('accepts the actual blocked producer export without inventing experiments', () => {
    const run = validateBundle(blocked()).runs[0];
    expect(run.manifest.status).toBe('blocked');
    expect(run.report.experiments).toEqual([]);
    render(<ExperimentDetails run={run} />);
    expect(screen.getByRole('heading', { name: 'Experiment plan & completion' })).toBeInTheDocument();
    expect(screen.getByText('No experiments recorded. Planned steps and missing controls are not passing results.')).toBeInTheDocument();
    expect(screen.getAllByText('Unknown / not measured — not zero').length).toBeGreaterThan(0);
    expect(screen.getByRole('region', { name: 'Planned experiment steps' }).querySelectorAll('tbody tr')).toHaveLength(6);
    expect(screen.queryByText('Normalized case observations')).not.toBeInTheDocument();
  });
  it('accepts legacy and v2 together without changing the envelope', () => {
    const value = blocked(); value.runs.push(fixture().runs[0]);
    expect(validateBundle(value).runs).toHaveLength(2);
  });
  it.each([
    ['unknown report version', (r: any) => { r.schema_version = 'local-report-3'; }],
    ['unknown plan version', (r: any) => { r.plan.schema_version = 'experiment-plan-3'; }],
    ['unknown operation profile', (r: any) => { r.plan.profile_id = 'hypothesis-experiment-2'; }],
    ['wrong request fixture', (r: any) => { r.plan.steps[0].request.fixture_id = 'unknown'; }],
    ['executable request parameter', (r: any) => { r.plan.steps[0].request.parameters.argv = ['run']; }],
    ['duplicate step', (r: any) => { r.plan.steps[1].id = r.plan.steps[0].id; }],
    ['duplicate slot', (r: any) => { r.plan.steps[1].request = r.plan.steps[0].request; }],
    ['forward replay', (r: any) => { r.plan.steps[3].replay_of = r.plan.steps[4].id; }],
    ['replay request mismatch', (r: any) => { r.plan.steps[3].request.parameters.variant = 'delta'; }],
    ['unknown plan key', (r: any) => { r.plan.command = 'run'; }],
    ['negative budget', (r: any) => { r.plan.budgets.actions = -1; }],
    ['oversize budget', (r: any) => { r.plan.budgets.actions = 9; }],
    ['false completed steps', (r: any) => { r.completion.all_steps_completed = true; }],
    ['missing control removed', (r: any) => { r.completion.missing_controls.pop(); }],
    ['required control removed', (r: any) => { r.completion.required_controls.pop(); }],
    ['wrong budget completion', (r: any) => { r.completion.within_budgets = false; }],
    ['unknown count set to zero', (r: any) => { r.usage.target_invocations = 0; }],
    ['parsed accounting mismatch', (r: any) => { r.usage.parsed_observations = 1; }],
    ['attempt without provenance', (r: any) => { r.usage.tool_attempts = 1; r.usage.unreturned_attempts = 1; }],
    ['fabricated experiment', (r: any) => { r.experiments.push({}); }],
    ['blocked confirmation', (r: any) => { r.findings[0].status = 'confirmed'; }],
    ['mixed report downgrade', (r: any) => { r.schema_version = 'local-report-1'; }],
  ] as const)('rejects %s', (_label, mutate) => {
    const value = blocked(); mutate(value.runs[0].report);
    expect(() => validateBundle(value)).toThrow();
  });
});

// Owner-produced invented data is ONLY schema-test input, never a runtime demo.
describe('invented completed LabProof v2 schema', () => {
  it('accepts owner fixture with six experiments and matching evidence', () => {
    const run = validateBundle(structuredClone(inventedCompleted)).runs[0];
    expect(run.report.title).toContain('INVENTED UNIT-TEST DATA');
    expect(run.report.experiments).toHaveLength(6);
    expect(run.report.evidence).toHaveLength(6);
    expect(run.manifest.status).toBe('completed');
  });
  it.each([
    ['request mismatch', (r: any) => { r.experiments[0].request.parameters.variant = 'delta'; }],
    ['replay mismatch', (r: any) => { r.experiments[3].replay_of = 'observation_beta'; }],
    ['worker reuse', (r: any) => { r.experiments[1].execution_id = r.experiments[0].execution_id; }],
    ['reset reuse', (r: any) => { r.experiments[1].reset_id = r.experiments[0].reset_id; }],
    ['missing evidence', (r: any) => { r.experiments[0].evidence_id = 'missing'; }],
    ['duplicate evidence', (r: any) => { r.experiments[1].evidence_id = r.experiments[0].evidence_id; }],
    ['embedded evidence mismatch', (r: any) => { r.evidence[0].record.request_key = 'f'.repeat(64); }],
    ['raw observation mismatch', (r: any) => { r.experiments[0].observation.raw_text = 'changed'; }],
    ['invalid digest', (r: any) => { r.experiments[0].request_key = 'bad'; }],
    ['unknown parser status', (r: any) => { r.experiments[0].parse_status = 'success'; }],
    ['controller interruption mismatch', (r: any) => { r.experiments[0].timed_out = true; }],
    ['nonboolean cleanup when interrupted', (r: any) => { r.experiments[0].timed_out = true; r.experiments[0].cleanup_ok = 'yes'; }],
    ['nonzero exit promoted to parsed', (r: any) => { r.experiments[0].child_returncode = 1; }],
    ['parsed null observation', (r: any) => { r.experiments[0].observation = null; }],
    ['negative elapsed', (r: any) => { r.experiments[0].elapsed_seconds = -1; }],
    ['raw byte mismatch', (r: any) => { r.experiments[0].output_bytes++; }],
    ['wrong provisioning image', (r: any) => { r.experiments[0].image_id = 'sha256:' + 'f'.repeat(64); }],
    ['missing provisioning', (r: any) => { r.provenance.provisioning = null; }],
    ['unknown provisioning schema', (r: any) => { r.provenance.provisioning.schema_version = 'local-provisioning-3'; }],
    ['unknown oracle hash', (r: any) => { r.provenance.provisioning.oracle_sha256 = null; }],
    ['too many executions', (r: any) => { r.experiments.push(r.experiments[0]); }],
    ['missing execution', (r: any) => { r.experiments.pop(); }],
    ['replay count mismatch', (r: any) => { r.usage.completed_replays = 0; }],
    ['unknown counts invented as zero', (r: any) => { r.usage.shrinks = 0; }],
    ['elapsed sum mismatch', (r: any) => { r.usage.elapsed_seconds = 100; }],
    ['attempt count mismatch', (r: any) => { r.usage.tool_attempts = 5; }],
    ['false missing-control claim', (r: any) => { r.completion.missing_controls = ['observation_alpha']; }],
  ] as const)('rejects %s', (_label, mutate) => {
    const value: Record<string, any> = structuredClone(inventedCompleted); mutate(value.runs[0].report);
    expect(() => validateBundle(value)).toThrow();
  });
});

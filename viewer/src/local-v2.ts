import type { JsonObject, Report } from './contracts';

export interface ExperimentStep { id: string; phase: 'observation' | 'verification'; replay_of: string | null; request: JsonObject }
export interface ExperimentPlan { schema_version: 'experiment-plan-2'; profile_id: string; budgets: { actions: number; wall_seconds: number; output_bytes: number }; steps: ExperimentStep[] }
export interface Experiment extends JsonObject { step_id: string; controller_status: string; parse_status: string; evidence_id: string | null; observation: JsonObject | null }
export interface LocalV2 { plan: ExperimentPlan; experiments: Experiment[]; completion: { required_controls: string[]; missing_controls: string[]; all_steps_completed: boolean; within_budgets: boolean }; usage: JsonObject }
function fail(message: string): never { throw new Error(`local-report-2: ${message}`); }
function obj(v: unknown): JsonObject { if (!v || typeof v !== 'object' || Array.isArray(v)) fail('expected object'); return v as JsonObject; }
function keys(v: JsonObject, names: string) { const expected = names.split(' '); if (Object.keys(v).length !== expected.length || expected.some(k => !(k in v))) fail('unexpected or missing fields'); }
function array(v: unknown): unknown[] { if (!Array.isArray(v)) fail('expected array'); return v; }
function text(v: unknown): string { if (typeof v !== 'string' || !v.length || v.length > 200) fail('invalid bounded text'); return v; }
function identifier(v: unknown): string { const s = text(v); if (!/^[a-zA-Z0-9_-]{1,100}$/.test(s)) fail('invalid identity'); return s; }
function integer(v: unknown, max = Number.MAX_SAFE_INTEGER): number { if (typeof v !== 'number' || !Number.isSafeInteger(v) || v < 0 || v > max) fail('invalid nonnegative integer'); return v; }
function bool(v: unknown): boolean { if (typeof v !== 'boolean') fail('invalid boolean'); return v; }
function digest(v: unknown) { if (typeof v !== 'string' || !/^[a-f0-9]{64}$/.test(v)) fail('invalid digest'); }
function stable(v: unknown): string { if (Array.isArray(v)) return `[${v.map(stable).join(',')}]`; if (v && typeof v === 'object') return `{${Object.entries(v).sort(([a], [b]) => a.localeCompare(b)).map(([k, x]) => `${JSON.stringify(k)}:${stable(x)}`).join(',')}}`; return JSON.stringify(v); }
function equal(a: unknown, b: unknown, label: string) { if (stable(a) !== stable(b)) fail(`${label} mismatch`); }
const operations: Record<string, string> = { python: 'python-invariants', typescript: 'typescript-node-test', c: 'c-gcc', rust: 'rust-cargo-test' };
const controls = ['alpha', 'beta', 'gamma'].flatMap(v => [`observation_${v}`, `verification_${v}`]);
const executionFields = 'step_id request request_key phase replay_of execution_id container_id reset_id image_id runtime_id policy_digest provenance_sha256 controller_status child_returncode timed_out cancelled truncated cleanup_ok elapsed_seconds output_bytes raw_sha256 parse_status observation evidence_id';
const recordFields = 'step_id request request_key phase replay_of execution_id container_id reset_id image_id policy_digest runtime_id provenance_sha256 raw_sha256 observation'.split(' ');

// Structural/correspondence checks over embedded report data only. This does not
// hash raw artifacts, reproduce host grading, or attest execution/containment.
export function validateLocalV2(report: Report, status: string): LocalV2 {
  if (report.schema_version !== 'local-report-2' || report.mode !== 'local' || report.project_id !== 'labproof') fail('domain identity mismatch');
  const pack = text(report.pack_id), operation = operations[pack];
  if (!operation) fail('unsupported experiment pack');
  equal(report.public_remediation_claims, [], 'public remediation claims');
  equal(report.status, status, 'status');
  const plan = obj(report.plan); keys(plan, 'schema_version profile_id budgets steps');
  equal(plan.schema_version, 'experiment-plan-2', 'plan version');
  equal(plan.profile_id, `${operation}-experiment-2`, 'profile');
  const budgets = obj(plan.budgets); keys(budgets, 'actions wall_seconds output_bytes');
  integer(budgets.actions, 8); integer(budgets.wall_seconds, pack === 'rust' ? 504 : 144); integer(budgets.output_bytes, 524288);
  const steps = array(plan.steps).map(raw => {
    const s = obj(raw); keys(s, 'id request phase replay_of'); identifier(s.id);
    if (s.phase !== 'observation' && s.phase !== 'verification') fail('invalid phase');
    const request = obj(s.request); keys(request, 'schema_version pack_id operation_id fixture_id parameters');
    equal(request.schema_version, '1.0', 'request version'); equal(request.pack_id, pack, 'request pack');
    equal(request.operation_id, operation, 'request operation'); equal(request.fixture_id, `${pack}-synthetic-v1`, 'request fixture');
    const parameters = obj(request.parameters); keys(parameters, 'variant');
    if (!['alpha', 'beta', 'gamma', 'delta'].includes(text(parameters.variant))) fail('unsupported request variant');
    return s as unknown as ExperimentStep;
  });
  if (!steps.length || steps.length > 8) fail('expected 1–8 steps');
  const seenSteps = new Map<string, ExperimentStep>(), slots = new Set<string>();
  for (const step of steps) {
    if (seenSteps.has(step.id)) fail('duplicate step');
    const slot = stable([step.request, step.phase]); if (slots.has(slot)) fail('duplicate request/phase'); slots.add(slot);
    if (step.phase === 'observation') equal(step.replay_of, null, 'observation replay');
    else {
      const original = seenSteps.get(text(step.replay_of));
      if (!original || original.phase !== 'observation') fail('dangling/forward replay');
      equal(step.request, original.request, 'replay request');
    }
    seenSteps.set(step.id, step);
  }
  const provenance = obj(report.provenance), provision = provenance.provisioning;
  equal(provenance.adjudication, 'host_control_rules_v1', 'grader');
  equal(provenance.decisions, 'fixed_catalogue', 'decisions'); equal(provenance.model, 'not_used', 'model');
  equal(provenance.observations, 'local_container', 'observations'); equal(provenance.verification, 'fresh_container_reexecution', 'verification');
  if (provision !== null) {
    const p = obj(provision); keys(p, 'schema_version image_id base_digest source_sha256 oracle_sha256 worker_sha256 adapter_sha256 dependency_lock_sha256 compiler_version compiler_flags binary_sha256');
    equal(p.schema_version, 'local-provisioning-2', 'provisioning version');
    if (typeof p.image_id !== 'string' || !/^sha256:[a-f0-9]{64}$/.test(p.image_id) || typeof p.base_digest !== 'string' || !/^[a-z0-9./:_-]+@sha256:[a-f0-9]{64}$/.test(p.base_digest)) fail('invalid provisioning identity');
    for (const k of ['source_sha256', 'oracle_sha256', 'worker_sha256', 'adapter_sha256']) digest(p[k]);
    for (const k of ['dependency_lock_sha256', 'binary_sha256']) if (p[k] !== null) digest(p[k]);
    if (p.compiler_version !== null && text(p.compiler_version).length > 100) fail('invalid compiler version');
    if (p.compiler_flags !== null && (array(p.compiler_flags).length > 32 || array(p.compiler_flags).some(f => text(f).length > 100))) fail('invalid compiler flags');
  }
  const usedIds = new Set<string>(), usedEvidence = new Set<string>();
  const experiments = array(report.experiments).map((raw, index) => {
    const e = obj(raw); keys(e, executionFields);
    const step = steps[index]; if (!step) fail('too many experiments');
    for (const [key, expected] of Object.entries({ step_id: step.id, request: step.request, phase: step.phase, replay_of: step.replay_of })) equal(e[key], expected, `experiment ${key}`);
    if (provision === null) fail('experiment without provisioning');
    equal(e.image_id, obj(provision).image_id, 'experiment image');
    const ownIds = new Set(['execution_id', 'container_id', 'reset_id'].map(k => identifier(e[k])));
    for (const identity of ownIds) { if (usedIds.has(identity)) fail('reused worker/reset identity'); usedIds.add(identity); }
    for (const k of ['request_key', 'runtime_id', 'policy_digest', 'provenance_sha256', 'raw_sha256']) digest(e[k]);
    const flags = ['timed_out', 'cancelled', 'truncated'].map(k => bool(e[k]));
    const cleanupOk = bool(e.cleanup_ok);
    const interrupted = flags.some(Boolean) || !cleanupOk;
    equal(e.controller_status, interrupted ? 'interrupted' : 'completed', 'controller status');
    if (e.child_returncode !== null && (typeof e.child_returncode !== 'number' || !Number.isInteger(e.child_returncode) || e.child_returncode < -2147483648 || e.child_returncode > 2147483647)) fail('invalid child exit');
    if (typeof e.elapsed_seconds !== 'number' || !Number.isFinite(e.elapsed_seconds) || e.elapsed_seconds < 0 || e.elapsed_seconds > 86400) fail('invalid elapsed seconds');
    integer(e.output_bytes, 65536);
    if (!['parsed', 'unrecognized', 'unavailable'].includes(text(e.parse_status))) fail('unsupported parse status');
    const safe = !interrupted && e.child_returncode === 0;
    if (!safe && e.parse_status !== 'unavailable' || safe && e.parse_status === 'unavailable') fail('parse/controller mismatch');
    if (e.parse_status !== 'parsed') {
      equal(e.observation, null, 'unparsed observation'); equal(e.evidence_id, null, 'unparsed evidence');
      if (index !== array(report.experiments).length - 1) fail('continued after incomplete worker');
    } else {
      const evidenceId = identifier(e.evidence_id), evidence = report.evidence.find(r => r.id === evidenceId);
      if (!evidence?.record || usedEvidence.has(evidenceId)) fail('missing/duplicate experiment evidence'); usedEvidence.add(evidenceId);
      for (const field of recordFields) equal(e[field], evidence.record[field], `evidence ${field}`);
      equal(e.observation, evidence.record.observation, 'observation'); equal(e.raw_sha256, evidence.record.observation.raw_sha256, 'raw digest');
      equal(evidence.record.observation.operation_id, operation, 'observation operation'); equal(evidence.record.observation.variant, obj(step.request.parameters).variant, 'observation variant');
      equal(evidence.artifact_path, `evidence/${evidenceId}.json`, 'evidence path');
      equal(e.output_bytes, new TextEncoder().encode(evidence.record.observation.raw_text).byteLength, 'raw bytes');
    }
    return e as Experiment;
  });
  if (usedEvidence.size !== report.evidence.length) fail('unreferenced evidence');
  const completion = obj(report.completion); keys(completion, 'required_controls missing_controls all_steps_completed within_budgets');
  const done = experiments.filter(e => e.parse_status === 'parsed');
  const doneControls = done.map(e => `${e.phase}_${obj(obj(e.request).parameters).variant}`);
  equal(completion.required_controls, controls, 'required controls'); equal(completion.missing_controls, controls.filter(c => !doneControls.includes(c)), 'missing controls');
  equal(completion.all_steps_completed, experiments.length === steps.length && done.length === steps.length, 'step completion');
  const elapsed = experiments.reduce((n, e) => n + Number(e.elapsed_seconds), 0), bytes = experiments.reduce((n, e) => n + Number(e.output_bytes), 0);
  equal(completion.within_budgets, experiments.length <= Number(budgets.actions) && elapsed <= Number(budgets.wall_seconds) && bytes <= Number(budgets.output_bytes), 'budget completion');
  const usage = obj(report.usage); keys(usage, 'tool_attempts model_calls model_usage model_usage_status completed_steps parsed_observations replays target_invocations rejections shrinks elapsed_seconds output_bytes unreturned_attempts completed_replays');
  const attempts = integer(usage.tool_attempts, steps.length), unreturned = integer(usage.unreturned_attempts, 1);
  equal(attempts, experiments.length + unreturned, 'attempt accounting');
  if (attempts > Number(budgets.actions) || attempts && provision === null) fail('invalid attempts');
  if (unreturned && experiments.some(e => e.parse_status !== 'parsed')) fail('attempt after incomplete worker');
  equal(usage.completed_steps, done.length, 'completed steps'); equal(usage.parsed_observations, done.length, 'parsed observations');
  equal(usage.replays, steps.slice(0, attempts).filter(s => s.phase === 'verification').length, 'replays');
  equal(usage.completed_replays, done.filter(e => e.phase === 'verification').length, 'completed replays');
  if (unreturned) equal(usage.elapsed_seconds, null, 'unknown elapsed seconds');
  else if (typeof usage.elapsed_seconds !== 'number' || Math.abs(usage.elapsed_seconds - elapsed) > 1e-9) fail('elapsed accounting mismatch');
  equal(usage.output_bytes, bytes, 'output bytes'); equal(usage.model_calls, 0, 'model calls'); equal(usage.model_usage, null, 'model usage'); equal(usage.model_usage_status, 'not_applicable_deterministic', 'model usage status');
  for (const k of ['target_invocations', 'rejections', 'shrinks']) equal(usage[k], null, `unknown ${k}`);
  if (status === 'completed' && (!completion.all_steps_completed || !completion.within_budgets || array(completion.missing_controls).length || unreturned)) fail('completed run lacks controls or budgets');
  if (status === 'blocked' && attempts) fail('blocked run contains attempts');
  if (status !== 'completed' && report.findings?.some(f => f.status === 'confirmed')) fail('incomplete run promotes confirmation');
  return { plan: { ...plan, steps } as unknown as ExperimentPlan, experiments, completion: completion as unknown as LocalV2['completion'], usage };
}

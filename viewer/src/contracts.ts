import { validateLocalV2 } from './local-v2';
export const MAX_BUNDLE_BYTES = 5 * 1024 * 1024;
export type JsonObject = Record<string, unknown>;
export type Project = 'labproof';
export type Mode = 'replay' | 'local' | 'live';
export interface Artifact { path: string; sha256: string; bytes: number }
export interface Manifest {
  schema_version: '1.0'; project_id: Project; run_id: string; mode: Mode;
  status: string; created_at: string; artifacts: Artifact[]; limitations: string[];
}
export interface LocalCase extends JsonObject { case_id: string; response: JsonObject }
export interface LocalObservation extends JsonObject {
  schema_version: 'parsed-worker-observation-1'; operation_id: string; variant: string;
  tool: string; tool_version: string; raw_sha256: string; raw_text: string;
  cases: LocalCase[]; ast_nodes: unknown[];
}
export interface LocalRecord extends JsonObject {
  id: string; phase: 'observation' | 'verification'; execution_id: string; reset_id: string; observation: LocalObservation;
}
export interface Evidence extends JsonObject { id: string; record?: LocalRecord }
export interface Item extends JsonObject { id: string; evidence_ids: string[] }
export interface Report extends JsonObject {
  project_id: Project; run_id: string; mode: Mode; title: string; summary: string;
  limitations: string[]; evidence: Evidence[]; findings?: Item[];
}
export interface RunEvent { sequence: number; type: string; run_id: string; timestamp: string; data: JsonObject }
export interface Run { manifest: Manifest; report: Report; events: RunEvent[] }
export interface Bundle {
  schema_version: '1.0'; generated_at: string; runs: Run[];
  limitations?: string[]; source_report_sha256?: string;
}

function fail(path: string, message: string): never { throw new Error(`${path}: ${message}`); }
function object(value: unknown, path: string): JsonObject {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) fail(path, 'expected an object');
  return value as JsonObject;
}
function onlyKeys(value: JsonObject, keys: readonly string[], path: string) {
  if (Object.keys(value).some(key => !keys.includes(key))) fail(path, 'unexpected field');
}
function text(value: unknown, path: string, nonempty = false): string {
  if (typeof value !== 'string' || value.length > 200_000 || (nonempty && !value.trim())) fail(path, 'expected a bounded string');
  return value;
}
function list(value: unknown, path: string): unknown[] {
  if (!Array.isArray(value) || value.length > 10_000) fail(path, 'expected an array (maximum 10,000 entries)');
  return value;
}
function strings(value: unknown, path: string): string[] { return list(value, path).map((v, i) => text(v, `${path}[${i}]`)); }
function date(value: unknown, path: string): string {
  const result = text(value, path);
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(result) || !Number.isFinite(Date.parse(result))) fail(path, 'expected an ISO timestamp with timezone');
  return result;
}
function choice<T extends string>(value: unknown, options: readonly T[], path: string): T {
  if (typeof value !== 'string' || !options.includes(value as T)) fail(path, `expected ${options.join(', ')}`);
  return value as T;
}
function id(value: unknown, path: string): string {
  const result = text(value, path, true);
  if (result.length > 200) fail(path, 'identifier is too long');
  return result;
}
function unique(values: string[], path: string) {
  if (new Set(values).size !== values.length) fail(path, 'duplicate identifier or path');
}
export function safeArtifactPath(value: string): boolean {
  return value.length > 0 && value.length < 1024 && !/[\\:\u0000-\u001f\u007f%]/.test(value)
    && value.split('/').every(part => part !== '' && part !== '.' && part !== '..');
}
// This is a navigation guard, not a DNS resolver or a source-authenticity check.
export function safeSourceUrl(value: unknown): string | null {
  if (typeof value !== 'string' || value.length > 4096 || /[\u0000- \u007f\\]/.test(value)) return null;
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase().replace(/\.$/, '');
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) return null;
    if (!host.includes('.') || /[:\[\]]/.test(host) || /^[\d.]+$/.test(host)) return null;
    if (/(^|\.)(localhost|local|internal|intranet|home|lan|onion)$/.test(host) || host.endsWith('.localhost.localdomain')) return null;
    return url.href;
  } catch { return null; }
}
function checkComplexity(root: unknown) {
  const stack: [unknown, number][] = [[root, 0]];
  let count = 0;
  while (stack.length) {
    const [value, depth] = stack.pop()!;
    if (++count > 150_000 || depth > 32) fail('bundle', 'content is too large or too deeply nested');
    if (typeof value === 'string' && value.length > 200_000) fail('bundle', 'text field exceeds 200,000 characters');
    if (value && typeof value === 'object') {
      for (const child of Object.values(value)) stack.push([child, depth + 1]);
    }
  }
}
function localRecord(value: unknown, evidenceId: string, path: string): LocalRecord {
  const record = object(value, path);
  if (record.id !== evidenceId) fail(`${path}.id`, 'does not match evidence identifier');
  const observation = object(record.observation, `${path}.observation`);
  const schema_version = choice(observation.schema_version, ['parsed-worker-observation-1'] as const, `${path}.observation.schema_version`);
  const raw_sha256 = text(observation.raw_sha256, `${path}.raw_sha256`);
  if (!/^[a-f0-9]{64}$/.test(raw_sha256)) fail(`${path}.raw_sha256`, 'expected a SHA-256 digest');
  const cases = list(observation.cases, `${path}.cases`).map((value): LocalCase => {
    const entry = object(value, `${path}.case`);
    return { ...entry, case_id: id(entry.case_id, `${path}.case_id`), response: object(entry.response, `${path}.response`) };
  });
  unique(cases.map(entry => entry.case_id), `${path}.cases`);
  return { ...record, id: evidenceId, phase: choice(record.phase, ['observation', 'verification'] as const, `${path}.phase`),
    execution_id: id(record.execution_id, `${path}.execution_id`), reset_id: id(record.reset_id, `${path}.reset_id`),
    observation: { ...observation, schema_version, operation_id: id(observation.operation_id, `${path}.operation_id`),
      variant: text(observation.variant, `${path}.variant`, true), tool: text(observation.tool, `${path}.tool`, true),
      tool_version: text(observation.tool_version, `${path}.tool_version`, true), raw_sha256,
      raw_text: text(observation.raw_text, `${path}.raw_text`), cases, ast_nodes: list(observation.ast_nodes, `${path}.ast_nodes`) } };
}
// Checks internal structure and cross-references only; does not authenticate artifacts.
export function validateBundle(value: unknown): Bundle {
  checkComplexity(value);
  const bundle = object(value, 'bundle');
  choice(bundle.schema_version, ['1.0'], 'bundle.schema_version');
  const generated_at = date(bundle.generated_at, 'bundle.generated_at');
  const limitations = bundle.limitations === undefined ? undefined : strings(bundle.limitations, 'bundle.limitations');
  const source_report_sha256 = bundle.source_report_sha256 === undefined ? undefined : text(bundle.source_report_sha256, 'bundle.source_report_sha256');
  if (source_report_sha256 !== undefined && !/^[a-f0-9]{64}$/.test(source_report_sha256)) fail('bundle.source_report_sha256', 'expected a SHA-256 digest');
  const rawRuns = list(bundle.runs, 'bundle.runs');
  if (rawRuns.length > 100) fail('bundle.runs', 'maximum 100 runs');
  const runs = rawRuns.map((raw, index): Run => {
    const path = `runs[${index}]`;
    const run = object(raw, path);
    const m = object(run.manifest, `${path}.manifest`);
    onlyKeys(m, ['schema_version', 'project_id', 'run_id', 'mode', 'status', 'created_at', 'artifacts', 'limitations'], `${path}.manifest`);
    const schema_version = choice(m.schema_version, ['1.0'] as const, `${path}.schema_version`);
    const project_id = choice(m.project_id, ['labproof'] as const, `${path}.project_id`);
    const run_id = id(m.run_id, `${path}.run_id`);
    if (!/^[a-zA-Z0-9_-]{1,100}$/.test(run_id)) fail(`${path}.run_id`, 'invalid run identifier');
    const mode = choice(m.mode, ['replay', 'local', 'live'] as const, `${path}.mode`);
    const status = choice(m.status, ['completed', 'incomplete', 'blocked', 'failed', 'cancelled'], `${path}.status`);
    const artifacts = list(m.artifacts, `${path}.artifacts`).map((rawArtifact): Artifact => {
      const a = object(rawArtifact, `${path}.artifact`);
      onlyKeys(a, ['path', 'sha256', 'bytes'], `${path}.artifact`);
      const artifactPath = text(a.path, `${path}.artifact.path`);
      if (!safeArtifactPath(artifactPath)) fail(`${path}.artifact.path`, 'unsafe relative path');
      const sha256 = text(a.sha256, `${path}.artifact.sha256`);
      if (!/^[a-f0-9]{64}$/.test(sha256)) fail(`${path}.artifact.sha256`, 'expected a SHA-256 digest');
      if (typeof a.bytes !== 'number' || !Number.isSafeInteger(a.bytes) || a.bytes < 0) fail(`${path}.artifact.bytes`, 'expected a nonnegative integer');
      return { path: artifactPath, sha256, bytes: a.bytes };
    });
    if (!artifacts.length) fail(`${path}.artifacts`, 'at least one registered artifact is required');
    unique(artifacts.map(a => a.path), `${path}.artifacts`);
    const manifest: Manifest = { schema_version, project_id, run_id, mode, status,
      created_at: date(m.created_at, `${path}.created_at`), artifacts, limitations: strings(m.limitations, `${path}.limitations`) };
    const r = object(run.report, `${path}.report`);
    // Envelope v1 does not imply domain v1. Never render an unknown domain through legacy semantics.
    const localV2 = mode === 'local' && r.schema_version === 'local-report-2';
    const supportedSchema = mode === 'local' ? 'local-report-1' : '1.0';
    if (r.schema_version !== undefined && r.schema_version !== supportedSchema && !localV2) fail(`${path}.report.schema_version`, 'unsupported report version');
    if (!localV2 && ['plan', 'experiments', 'completion'].some(key => r[key] !== undefined)) fail(`${path}.report`, 'unsupported v2 experiment fields in legacy report');
    if (mode === 'local') {
      choice(r.schema_version, ['local-report-1', 'local-report-2'], `${path}.report.schema_version`);
      text(r.pack_id, `${path}.report.pack_id`, true);
      object(r.provenance, `${path}.report.provenance`);
    }
    if (r.status !== undefined && r.status !== status) fail(`${path}.report.status`, 'does not match manifest');
    for (const [key, expected] of Object.entries({ project_id, run_id, mode })) {
      if (r[key] !== expected) fail(`${path}.report.${key}`, 'does not match manifest');
    }
    const evidence = list(r.evidence, `${path}.report.evidence`).map((rawEvidence): Evidence => {
      const e = object(rawEvidence, `${path}.evidence`);
      const evidenceId = id(e.id, `${path}.evidence.id`);
      if (e.artifact_path !== undefined && e.artifact_path !== null) {
        const relative = text(e.artifact_path, `${path}.evidence.artifact_path`);
        if (!safeArtifactPath(relative) || !artifacts.some(a => a.path === relative)) fail(`${path}.evidence.artifact_path`, 'path must be safe and registered');
      }
      const record = mode === 'local' ? localRecord(e.record, evidenceId, `${path}.evidence.record`) : undefined;
      if (e.record !== undefined && record === undefined) fail(`${path}.evidence.record`, 'local LabProof evidence only');
      if (record && (typeof e.content !== 'string' || e.content !== record.observation.raw_text)) fail(`${path}.evidence.content`, 'does not match retained raw observation');
      return { ...e, id: evidenceId, ...(record ? { record } : {}) };
    });
    unique(evidence.map(e => e.id), `${path}.evidence`);
    const items = list(r.findings, `${path}.report.findings`).map((rawItem): Item => {
      const item = object(rawItem, `${path}.findings`);
      const itemId = id(item.id, `${path}.findings.id`);
      const evidence_ids = strings(item.evidence_ids, `${path}.findings.evidence_ids`);
      unique(evidence_ids, `${path}.findings.evidence_ids`);
      if (evidence_ids.some(ref => !evidence.some(e => e.id === ref))) fail(`${path}.findings`, 'unresolved evidence reference');
      return { ...item, id: itemId, evidence_ids };
    });
    unique(items.map(item => item.id), `${path}.findings`);
    const report: Report = { ...r, project_id, run_id, mode, title: text(r.title, `${path}.report.title`),
      summary: text(r.summary, `${path}.report.summary`), limitations: strings(r.limitations, `${path}.report.limitations`),
      evidence, findings: items };
    if (localV2) validateLocalV2(report, status);
    const events = list(run.events, `${path}.events`).map((rawEvent, eventIndex): RunEvent => {
      const event = object(rawEvent, `${path}.event`);
      if (event.sequence !== eventIndex + 1 || event.run_id !== run_id) fail(`${path}.events`, 'invalid event sequence or run identifier');
      return { sequence: eventIndex + 1, run_id, type: text(event.type, `${path}.event.type`, true),
        timestamp: date(event.timestamp, `${path}.event.timestamp`), data: object(event.data, `${path}.event.data`) };
    });
    const completion = events.findIndex(e => e.type === 'run_completed');
    if (status === 'completed' && (completion < 0 || completion !== events.length - 1)) fail(`${path}.events`, 'completed run requires a final completion event');
    if (status !== 'completed' && completion !== -1) fail(`${path}.events`, 'non-completed run cannot contain completion event');
    return { manifest, report, events };
  });
  unique(runs.map(run => run.manifest.run_id), 'runs');
  return { schema_version: '1.0', generated_at, runs,
    ...(limitations === undefined ? {} : { limitations }),
    ...(source_report_sha256 === undefined ? {} : { source_report_sha256 }) };
}
export function parseBundle(raw: string): Bundle {
  if (new TextEncoder().encode(raw).byteLength > MAX_BUNDLE_BYTES) fail('bundle', 'maximum file size is 5 MiB');
  let value: unknown;
  try { value = JSON.parse(raw); } catch { fail('bundle', 'invalid JSON'); }
  return validateBundle(value);
}
export async function readBundleResponse(response: Response): Promise<Bundle> {
  if (!response.ok) throw new Error('Demo bundle is not available. Import an exported bundle to begin.');
  if (Number(response.headers.get('content-length')) > MAX_BUNDLE_BYTES) throw new Error('Bundle exceeds 5 MiB.');
  if (!response.body) throw new Error('Bundle response is empty.');
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_BUNDLE_BYTES) { await reader.cancel(); throw new Error('Bundle exceeds 5 MiB.'); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  return parseBundle(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
}
export function display(value: unknown, fallback = 'Not recorded'): string {
  if (value === undefined || value === null || value === '') return fallback;
  return typeof value === 'string' ? value : JSON.stringify(value, null, 2) ?? fallback;
}
export const itemsFor = (run: Run): Item[] => run.report.findings ?? [];
export const itemTitle = (item: Item): string => display(item.title ?? item.text, item.id);
export const itemStatus = (item: Item): string => display(item.status ?? item.verdict, 'NOT_RECORDED');
export const projectName = (_project: Project): string => 'LabProof';

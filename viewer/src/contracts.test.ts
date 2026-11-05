import { describe, expect, it } from 'vitest';
import { MAX_BUNDLE_BYTES, parseBundle, readBundleResponse, safeArtifactPath, safeSourceUrl, validateBundle } from './contracts';
import { fixture } from './test-fixture';

function mutate(change: (bundle: Record<string, any>) => void) {
  const bundle = fixture(); change(bundle); return bundle;
}

describe('bundle runtime contract', () => {
  it('accepts the common contract and the LabProof domain shape', () => {
    const bundle = parseBundle(JSON.stringify(fixture()));
    expect(bundle.runs).toHaveLength(1);
    expect(bundle.runs[0].report.findings?.[0].id).toBe('f1');
  });
  it('supports an empty bundle', () => {
    expect(validateBundle(mutate(b => { b.runs = []; })).runs).toEqual([]);
  });
  it.each(['incomplete', 'blocked', 'failed', 'cancelled'])('accepts %s with no completion and no results', status => {
    const value = mutate(b => { b.runs = [b.runs[0]]; b.runs[0].manifest.status = status; b.runs[0].report.findings = []; b.runs[0].report.evidence = []; b.runs[0].events = []; });
    expect(validateBundle(value).runs[0].manifest.status).toBe(status);
  });
  it.each([
    ['schema mismatch', (b: any) => { b.schema_version = '2.0'; }],
    ['report identity mismatch', (b: any) => { b.runs[0].report.run_id = 'other'; }],
    ['report status mismatch', (b: any) => { b.runs[0].report.status = 'failed'; }],
    ['missing common field', (b: any) => { delete b.runs[0].report.limitations; }],
    ['duplicate run IDs', (b: any) => { b.runs.push(b.runs[0]); }],
    ['duplicate evidence IDs', (b: any) => { b.runs[0].report.evidence.push(b.runs[0].report.evidence[0]); }],
    ['duplicate finding IDs', (b: any) => { b.runs[0].report.findings.push(b.runs[0].report.findings[0]); }],
    ['dangling evidence', (b: any) => { b.runs[0].report.findings[0].evidence_ids = ['missing']; }],
    ['unregistered evidence path', (b: any) => { b.runs[0].report.evidence[0].artifact_path = 'missing.txt'; }],
    ['unsafe artifact path', (b: any) => { b.runs[0].manifest.artifacts[0].path = '../secret'; }],
    ['unknown manifest key', (b: any) => { b.runs[0].manifest.verified = true; }],
    ['invalid digest', (b: any) => { b.runs[0].manifest.artifacts[0].sha256 = 'not-a-hash'; }],
    ['negative bytes', (b: any) => { b.runs[0].manifest.artifacts[0].bytes = -1; }],
    ['invalid date', (b: any) => { b.generated_at = 'yesterday'; }],
    ['sequence gap', (b: any) => { b.runs[0].events[1].sequence = 3; }],
    ['event identity mismatch', (b: any) => { b.runs[0].events[0].run_id = 'other'; }],
    ['missing completion', (b: any) => { b.runs[0].events.pop(); }],
    ['completion not final', (b: any) => { b.runs[0].events[0].type = 'run_completed'; }],
    ['incomplete with completion', (b: any) => { b.runs[0].manifest.status = 'incomplete'; }],
    ['another product', (b: any) => { b.runs[0].manifest.project_id = 'other-product'; }],
  ])('rejects %s', (_name, change) => { expect(() => validateBundle(mutate(change))).toThrow(); });
  it('rejects invalid JSON, oversized files, oversized text and nesting', () => {
    expect(() => parseBundle('{')).toThrow('invalid JSON');
    expect(() => parseBundle(' '.repeat(MAX_BUNDLE_BYTES + 1))).toThrow('5 MiB');
    expect(() => validateBundle(mutate(b => { b.extra = 'x'.repeat(200_001); }))).toThrow();
    expect(() => validateBundle(mutate(b => { let tail = b; for (let i = 0; i < 34; i++) { tail.extra = {}; tail = tail.extra; } }))).toThrow('deeply nested');
  });
  it.each(['x', {}, { observation: {} }])('rejects a non-local unvalidated evidence record (%j)', record => {
    expect(() => validateBundle(mutate(b => { b.runs[0].report.evidence[0].record = record; }))).toThrow('evidence.record');
  });
  it('keeps bundle-level caveats and the recorded source digest', () => {
    const value = mutate(b => { b.limitations = ['Integration does not change the source finding.']; b.source_report_sha256 = 'a'.repeat(64); });
    expect(validateBundle(value).limitations).toEqual(['Integration does not change the source finding.']);
    expect(validateBundle(value).source_report_sha256).toBe('a'.repeat(64));
    expect(() => validateBundle(mutate(b => { b.source_report_sha256 = 'not a hash'; }))).toThrow('source_report_sha256');
  });
  it('retains hostile content as text without interpreting it', () => {
    expect(validateBundle(fixture()).runs[0].report.evidence[0].content).toBe('<script>alert("untrusted")</script>');
  });
});

describe('safe navigation and paths', () => {
  it.each(['javascript:alert(1)', 'data:text/html,hello', 'file:///etc/passwd', 'https://user:pass@docs.example.org', 'https://localhost', 'https://x.local', 'http://127.0.0.1', 'http://2130706433', 'http://0x7f000001', 'http://10.0.0.1', 'https://[::1]', '//docs.example.org', 'https://docs.example.org\\@localhost', 'https://x.internal'])('blocks %s', value => { expect(safeSourceUrl(value)).toBeNull(); });
  it('allows explicit public HTTP(S) navigation', () => { expect(safeSourceUrl('https://docs.example.org/path?q=1')).toBe('https://docs.example.org/path?q=1'); });
  it.each(['../a', '/a', 'a//b', 'a/./b', 'C:/a', 'a\\b', '%2e%2e/a', 'a\u0000b'])('rejects path %s', path => { expect(safeArtifactPath(path)).toBe(false); });
  it('accepts a registered-style POSIX path', () => { expect(safeArtifactPath('evidence/record.json')).toBe(true); });
});

describe('bounded response loading', () => {
  it('validates downloaded JSON', async () => {
    const bytes = new TextEncoder().encode(JSON.stringify(fixture()));
    const response = { ok: true, headers: { get: () => null }, body: new ReadableStream({ start(controller) { controller.enqueue(bytes); controller.close(); } }) } as unknown as Response;
    expect((await readBundleResponse(response)).runs).toHaveLength(1);
  });
  it('rejects unavailable or oversized downloads', async () => {
    await expect(readBundleResponse({ ok: false } as Response)).rejects.toThrow('not available');
    await expect(readBundleResponse({ ok: true, headers: { get: () => String(MAX_BUNDLE_BYTES + 1) } } as unknown as Response)).rejects.toThrow('5 MiB');
    const response = { ok: true, headers: { get: () => null }, body: new ReadableStream({ start(controller) { controller.enqueue(new Uint8Array(MAX_BUNDLE_BYTES + 1)); controller.close(); } }) } as unknown as Response;
    await expect(readBundleResponse(response)).rejects.toThrow('5 MiB');
  });
});

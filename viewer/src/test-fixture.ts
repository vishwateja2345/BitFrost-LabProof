// Synthetic unit-test data only. Never shipped as a fallback or measured demo.
export function fixture() {
  const timestamp = '2026-11-01T12:00:00Z';
  return {
    schema_version: '1.0', generated_at: timestamp,
    runs: [
      {
        manifest: { schema_version: '1.0', project_id: 'labproof', run_id: 'lp-test', mode: 'replay', status: 'completed', created_at: timestamp,
          artifacts: [{ path: 'report.json', sha256: 'a'.repeat(64), bytes: 1 }], limitations: ['Synthetic unit-test fixture.'] },
        report: { project_id: 'labproof', run_id: 'lp-test', mode: 'replay', title: 'Synthetic lab run', summary: 'Test plumbing only.', limitations: ['No live assessment.'],
          evidence: [{ id: 'e1', title: 'Captured control', content: '<script>alert("untrusted")</script>', variant: 'corrected', control: 'normal', phase: 'observation' }],
          findings: [{ id: 'f1', title: 'Synthetic observation', status: 'inconclusive', expected: 'No disclosure', observed: 'Unknown', evidence_ids: ['e1'] }] },
        events: [{ sequence: 1, run_id: 'lp-test', type: 'run_started', timestamp, data: {} }, { sequence: 2, run_id: 'lp-test', type: 'run_completed', timestamp, data: {} }],
      },
    ],
  };
}

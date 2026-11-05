import type { Run } from '../contracts';
import { display } from '../contracts';
import type { LocalV2 } from '../local-v2';
import { StatusBadge } from './ResultsTable';

export function ExperimentDetails({ run }: { run: Run }) {
  if (run.report.schema_version !== 'local-report-2') return null;
  const { plan, experiments, completion, usage } = run.report as unknown as LocalV2;
  return <section className="panel original-run standalone-panel" aria-label="V2 experiment plan and completion">
    <div className="section-heading"><h2>Experiment plan & completion</h2><StatusBadge status={run.manifest.status} /></div>
    <p className="mono small">{run.manifest.run_id} · {plan.profile_id} · local-report-2</p>
    <p className="note">A plan records intended work, not performed experiments. These unsigned host records do not attest execution, containment, or tool capability. The browser checks embedded structure and correspondence, not raw artifact hashes or host verdict derivation.</p>
    <dl className="provenance-fields"><div><dt>Action ceiling</dt><dd>{plan.budgets.actions}</dd></div><div><dt>Wall-time ceiling · seconds</dt><dd>{plan.budgets.wall_seconds}</dd></div><div><dt>Output ceiling · bytes</dt><dd>{plan.budgets.output_bytes}</dd></div><div><dt>All planned steps completed</dt><dd>{completion.all_steps_completed ? 'Yes — reported' : 'No'}</dd></div><div><dt>Recorded work within budgets</dt><dd>{completion.within_budgets ? 'Yes — not a completion claim' : 'No'}</dd></div></dl>
    <h3>Required controls</h3><p className="mono small">{completion.required_controls.join(', ')}</p>
    <h3>Missing controls</h3><p className={completion.missing_controls.length ? 'warning-text' : 'muted'}>{completion.missing_controls.length ? completion.missing_controls.join(', ') : 'None reported missing'}</p>
    <div className="table-scroll" role="region" aria-label="Planned experiment steps" tabIndex={0}><table><caption>Planned requests — not execution evidence</caption><thead><tr><th>Step / phase</th><th>Full request</th><th>Replay of</th></tr></thead><tbody>{plan.steps.map(step => <tr key={step.id}><td className="mono">{step.id}<br />{step.phase}</td><td><span className="mono">{display(step.request.operation_id)}</span><details><summary>Full request</summary><pre>{JSON.stringify(step.request, null, 2)}</pre></details></td><td className="mono">{step.replay_of ?? 'Not a replay'}</td></tr>)}</tbody></table></div>
    <h3>Recorded experiments ({experiments.length})</h3>
    {!experiments.length && <p className="warning-text">No experiments recorded. Planned steps and missing controls are not passing results.</p>}
    {experiments.map(experiment => <article className="evidence-card" key={experiment.step_id}><h4>{experiment.step_id}</h4><dl className="provenance-fields">{['controller_status', 'child_returncode', 'parse_status', 'timed_out', 'cancelled', 'truncated', 'cleanup_ok', 'execution_id', 'container_id', 'reset_id', 'evidence_id'].map(key => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{experiment[key] === null ? 'Not recorded — unknown' : display(experiment[key])}</dd></div>)}</dl><p className="small muted">Controller completion, child exit, parsing, and host verdict are separate. A nonzero exit or static signal does not confirm a defect.</p><details><summary>Full retained experiment</summary><pre>{JSON.stringify(experiment, null, 2)}</pre></details></article>)}
    <h3>Recorded accounting</h3><dl className="provenance-fields">{Object.entries(usage).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{value === null ? 'Unknown / not measured — not zero' : display(value)}</dd></div>)}</dl>
    <details><summary>Provisioning and oracle provenance · reported</summary><pre>{JSON.stringify(run.report.provenance, null, 2)}</pre></details>
  </section>;
}

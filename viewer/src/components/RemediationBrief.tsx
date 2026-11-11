import { ArrowLeft, ArrowUpRight, BookOpen, FileCheck2 } from 'lucide-react';
import type { Remediation, RemediationSource, Run } from '../contracts';
import { display, itemsFor, itemTitle } from '../contracts';

const briefStatus: Record<string, string> = {
  sourced: 'Cited guidance',
  no_verified_advice: 'No advice passed the quotation check',
  no_sources: 'No reviewed sources returned',
  search_failed: 'Search failed',
  model_failed: 'Model call failed',
};

function Citation({ source, live }: { source: RemediationSource; live: boolean }) {
  return live ? <a className="brief-citation" href={source.url} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">
    {source.title || new URL(source.url).hostname}<ArrowUpRight aria-hidden="true" /><span className="sr-only"> (new tab)</span>
  </a> : <span className="brief-citation muted">{source.title || 'Scripted source'}</span>;
}

export function RemediationBrief({ brief, run, onFinding }: {
  brief: Remediation; run: Run; onFinding: (itemId: string) => void;
}) {
  const live = brief.mode === 'live';
  const pack = display(run.report.pack_id, run.manifest.mode);
  return <section className="brief-view" aria-labelledby="brief-heading">
    <div className="brief-heading">
      <div>
        <span className="eyebrow"><FileCheck2 aria-hidden="true" /> {live ? 'Retained live provider run' : 'Offline demonstration'}</span>
        <h2 id="brief-heading">Remediation brief</h2>
        <p className="muted">Guidance for confirmed findings in the {pack} run.</p>
      </div>
      <dl className="brief-usage">
        <div><dt>{live ? 'Tavily Search' : 'Scripted search'}</dt><dd>{brief.searchCalls} {brief.searchCalls === 1 ? 'call' : 'calls'}{brief.searchVia === 'bifrost_relay' && ' via Bifrost relay'}</dd></div>
        <div><dt>{live ? 'Bifrost model' : 'Scripted model'}</dt><dd>{brief.model || 'No model requested'} · {brief.modelCalls} {brief.modelCalls === 1 ? 'call' : 'calls'}</dd></div>
      </dl>
    </div>
    <p className="note">{live ? 'Saved provider responses from an earlier run. ' : 'This demo uses invented source excerpts and scripted responses. '}
      Review model-generated advice alongside its citations. Use the CLI to verify the source run and brief offline.</p>
    {brief.classes.length === 0 && <p className="muted">The source run has no confirmed findings covered by the brief.</p>}
    {brief.classes.map(entry => <article className="brief-class" key={entry.id}>
      <div className="section-heading">
        <h3>{entry.title}</h3>
        <span className="badge">{entry.severity} severity</span>
      </div>
      <p className="muted">{entry.reason}</p>
      <div className="brief-findings">
        {entry.findings.map(findingId => {
          const item = itemsFor(run).find(finding => finding.id === findingId);
          return <button className="text-button" key={findingId} onClick={() => onFinding(findingId)}>
            <ArrowLeft aria-hidden="true" /> {item ? itemTitle(item) : findingId}
          </button>;
        })}
      </div>
      {entry.recommendations.length === 0 && <p className="warning-text">{briefStatus[entry.status]}</p>}
      {entry.recommendations.map(recommendation => <section className="brief-advice" key={recommendation.id}>
        <h4>Model-generated recommendation</h4>
        <p>{recommendation.text}</p>
        {recommendation.quotes.map(({ source, text }, index) => <figure key={index}>
          <blockquote>{text}</blockquote><figcaption><Citation source={source} live={live} /></figcaption>
        </figure>)}
      </section>)}
      {entry.sources.length > 0 && <details className="brief-sources">
        <summary><BookOpen aria-hidden="true" /> Retained source excerpts ({entry.sources.length})</summary>
        {entry.sources.map(source => <section key={source.id}><Citation source={source} live={live} /><p>{source.excerpt}</p></section>)}
      </details>}
    </article>)}
    {brief.skipped > 0 && <p className="muted">Confirmed findings without catalogue guidance: {brief.skipped}</p>}
    <p className="small muted">Brief recorded <time dateTime={brief.generatedAt}>{brief.generatedAt}</time> · <span className="mono">{brief.runId}</span></p>
  </section>;
}

import { useEffect, useRef } from 'react';
import { ExternalLink, X } from 'lucide-react';
import type { Evidence } from '../contracts';
import { display, safeSourceUrl } from '../contracts';
import { LocalEvidence } from './LocalEvidence';

export function SourceLink({ url }: { url: unknown }) {
  const safe = safeSourceUrl(url);
  if (url === undefined || url === null) return null;
  return safe ? <a className="source-link" href={safe} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">{safe}<ExternalLink size={13} aria-hidden="true" /><span className="sr-only"> (external site, new tab)</span></a>
    : <p className="warning-text small">Source link disabled: {display(url)}. Only public HTTP(S) hostnames without credentials are allowed.</p>;
}
export function EvidenceInspector({ evidence, onClose }: { evidence: Evidence | null; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (!evidence) return;
    const el = dialog.current;
    const previous = document.activeElement;
    el?.showModal();
    return () => { el?.close(); if (previous instanceof HTMLElement) previous.focus(); };
  }, [evidence]);
  return <dialog ref={dialog} className="inspector" onCancel={onClose} onKeyDown={event => {
    if (event.key !== 'Tab') return;
    const targets = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button, a[href], input, select, textarea, summary, [tabindex="0"]')).filter(element => !element.hasAttribute('disabled'));
    const first = targets[0];
    const last = targets.at(-1);
    if (!first || !last) return;
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }} onClick={event => { if (event.target === event.currentTarget) onClose(); }} aria-labelledby="inspector-heading">
    {evidence && <div className="inspector-content"><div className="section-heading"><span className="eyebrow">Evidence record</span><button className="icon-button" onClick={onClose} aria-label="Close evidence inspector" autoFocus><X size={20} aria-hidden="true" /></button></div>
      <span className="mono record-id">{evidence.id}</span><h2 id="inspector-heading">{display(evidence.title, 'Untitled evidence')}</h2>
      <SourceLink url={evidence.url} />
      <p className="note">Untrusted captured content. Displayed as text only; no links or artifact paths are fetched automatically.</p>
      {evidence.record && <LocalEvidence record={evidence.record} />}
      <span className="field-label">Captured content / exact excerpt</span><pre className="captured">{display(evidence.content ?? evidence.excerpt ?? evidence.response)}</pre>
      <h3>Record metadata</h3><dl className="metadata">{Object.entries(evidence).filter(([key]) => !['id', 'title', 'content', 'excerpt', 'url'].includes(key)).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd><pre>{display(value)}</pre></dd></div>)}</dl>
    </div>}
  </dialog>;
}

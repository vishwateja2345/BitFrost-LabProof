import { useState } from 'react';
import { Download } from 'lucide-react';

export function JsonRecord({ label, filename, value }: { label: string; filename: string; value: unknown }) {
  const [expanded, setExpanded] = useState(false);

  function download() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2) + '\n'], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return <details className="json-record" onToggle={event => setExpanded(event.currentTarget.open)}>
    <summary>{label}</summary>
    {expanded && <>
      <div className="json-toolbar">
        <span className="mono">{filename}</span>
        <button className="button secondary" type="button" onClick={download}><Download aria-hidden="true" /> Download JSON</button>
      </div>
      <pre tabIndex={0} aria-label={label}>{JSON.stringify(value, null, 2)}</pre>
    </>}
  </details>;
}

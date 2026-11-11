import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { productProfiles } from '../product-profiles';
import { validateBundle } from './contracts';
import { fixture } from './test-fixture';
import actualBlocked from './fixtures/labproof-blocked-v2.json';
import App from './App';

function preload(value: unknown) {
  const bytes = new TextEncoder().encode(JSON.stringify(value));
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, headers: { get: () => null }, body: new ReadableStream({ start(controller) { controller.enqueue(bytes); controller.close(); } }) }));
}
function upload(value: unknown) {
  const text = JSON.stringify(value);
  const file = new File([text], 'import.json', { type: 'application/json' });
  Object.defineProperty(file, 'arrayBuffer', { value: async () => new TextEncoder().encode(text).buffer });
  fireEvent.change(screen.getByLabelText('Import JSON bundle'), { target: { files: [file] } });
}
afterEach(() => { vi.unstubAllGlobals(); });

describe('LabProof viewer', () => {
  it('renders branding, scope, inventory and the interpretation guide', async () => {
    const value = fixture();
    preload(value);
    const { container } = render(<App />);
    await screen.findByText('Schema checked');
    const profile = productProfiles.labproof;
    expect(screen.getByRole('heading', { name: profile.heading })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: profile.guide })).toHaveAttribute('href', '#limitations-heading');
    expect(screen.getByPlaceholderText(profile.search)).toBeInTheDocument();
    expect(container.querySelectorAll('.inventory-card')).toHaveLength(3);
    expect(container.querySelectorAll('tbody tr')).toHaveLength(value.runs.length);
  });
  it('rejects a bundle from another product on preload and keeps the loaded bundle on import', async () => {
    const foreign = fixture(); foreign.runs[0].manifest.project_id = 'other-product'; foreign.runs[0].report.project_id = 'other-product';
    expect(() => validateBundle(foreign)).toThrow('project_id');
    preload(foreign);
    const { unmount } = render(<App />);
    expect(await screen.findByRole('alert')).toHaveTextContent('project_id');
    expect(screen.queryByText('Schema checked')).not.toBeInTheDocument();
    unmount();
    preload(fixture());
    render(<App />);
    await screen.findByText('Schema checked');
    fireEvent.change(screen.getByRole('textbox', { name: 'Search artifacts' }), { target: { value: 'Synthetic' } });
    fireEvent.click(screen.getByRole('button', { name: 'Synthetic observation' }));
    upload(foreign);
    expect(await screen.findByRole('alert')).toHaveTextContent('Previous bundle retained');
    expect(screen.getByRole('textbox', { name: 'Search artifacts' })).toHaveValue('Synthetic');
    expect(screen.getByRole('heading', { name: 'Synthetic observation' })).toBeInTheDocument();
    expect(screen.getByText('Saved lab review')).toBeInTheDocument();
    upload(fixture());
    expect(await screen.findByText('import.json')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
  it('loads actual blocked LabProof v2 and retains it on unknown-version or false-completion imports', async () => {
    preload(actualBlocked); render(<App />);
    await screen.findByRole('heading', { name: 'Recorded experiments (0)' });
    expect(screen.getByText('No experiments recorded. Planned steps and missing controls are not passing results.')).toBeInTheDocument();
    const unsupported = structuredClone(actualBlocked); unsupported.runs[0].report.schema_version = 'local-report-3';
    upload(unsupported);
    expect(await screen.findByRole('alert')).toHaveTextContent('Previous bundle retained');
    expect(screen.getByRole('alert')).toHaveTextContent('unsupported report version');
    const incorrect = structuredClone(actualBlocked); incorrect.runs[0].report.completion.missing_controls = [];
    upload(incorrect);
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('missing controls mismatch'));
    expect(screen.getByRole('heading', { name: 'Recorded experiments (0)' })).toBeInTheDocument();
  });
});

describe('legacy-only domain dispatch', () => {
  it('rejects v2 experiment fields even with version fields stripped', () => {
    const value = fixture(); Object.assign(value.runs[0].report, { experiments: [] });
    expect(() => validateBundle(value)).toThrow('unsupported v2 experiment fields');
  });
  it('rejects an unknown report schema', () => {
    const value = fixture(); Object.assign(value.runs[0].report, { schema_version: '3.0' });
    expect(() => validateBundle(value)).toThrow(/unsupported/);
  });
});

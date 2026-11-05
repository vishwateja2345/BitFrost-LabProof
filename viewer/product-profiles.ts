// Trusted source configuration. Never read profile selection from an artifact,
// URL, browser storage, or a run's declared metadata.
export const productProfiles = {
  labproof: {
    id: 'labproof', brand: 'LabProof', mark: 'L', subtitle: 'lab evidence',
    title: 'LabProof — Evidence viewer', heading: 'Lab observations, with receipts',
    description: 'A read-only viewer for LabProof findings and recorded controls.',
    introduction: 'Inspect findings, controls, and recorded execution lineage.',
    search: 'Search findings or evidence', importLabel: 'LabProof', guide: 'LabProof interpretation guide',
  },
} as const;
export type ProductProfileId = keyof typeof productProfiles;
export type ProductProfile = typeof productProfiles[ProductProfileId];

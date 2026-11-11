// Trusted source configuration. Never read profile selection from an artifact,
// URL, browser storage, or a run's declared metadata.
export const productProfiles = {
  labproof: {
    id: 'labproof', brand: 'LabProof', subtitle: 'Evidence review',
    title: 'LabProof — Evidence viewer', heading: 'Evidence workspace',
    description: 'A read-only viewer for LabProof findings and recorded controls.',
    introduction: 'Review lab findings, compare controls, and trace each result to its recorded evidence.',
    search: 'Search findings or evidence', importLabel: 'LabProof', guide: 'LabProof interpretation guide',
  },
} as const;
export type ProductProfileId = keyof typeof productProfiles;
export type ProductProfile = typeof productProfiles[ProductProfileId];

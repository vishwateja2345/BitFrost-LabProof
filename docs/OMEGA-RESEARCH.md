# OMEGA research and LabProof

This inventory follows the materials recovered in `OMEGA_All_Research_Code_and_Artifacts`. The archive contains the v15 paper and the executable v18.1 study, including its v18.0 audit. Its historical notes summarize v10–v14. The individual atlas entries and source archives for v10–v14 and v16–v17 were unavailable.

| Research | What OMEGA tried | Evidence and relevance to LabProof |
| --- | --- | --- |
| v10 lab atlas | 426 laboratory concepts across several domains. | The archive describes the atlas and its size. Individual specifications and adapters are unavailable. |
| v11 hypothesis selection | Seeded authorization and ASan toy fixtures, followed by 600 synthetic planning scenarios. | The comparison found no reliable lookahead advantage. LabProof's fixed experiment planner remains available for evaluating declared hypotheses. |
| v12 adaptive planning | Adaptive and fixed policies on owned Python fixtures with seeded defects and clean controls. | Adaptive planning showed no advantage over the fixed pipeline on those cases. |
| v13 contaminated observations | Planner comparisons using development and held-out synthetic cases. | Deliberately polluted service logs drove the reported gain. Clean cases tied. |
| v14 duplicate observations | Exact duplicate source grouping in synthetic cases. | The v15 paper describes the expected effect of grouping duplicates. The original v14 study files are unavailable. |
| v15 evidence fusion | Compared policies that combine observations with reported or authenticated provenance. | The primary comparison missed the preregistered superiority threshold, and the authenticated policy reduced coverage. A shared source or recorded execution is useful context for a reviewer. It does not establish independent corroboration. |
| v16–v17 | Historical work referenced by the archive. | The source and study artifacts were unavailable for review. |
| v18.0–v18.1 action authorization | Signed one-use permission bound to a task, tool, arguments, phase, expiry, and nonce. | V18.1 corrected the v18.0 expiry baseline. It denied 2,700/2,700 unauthorized proposals and allowed 300/300 valid proposals in generated deterministic cases. The study also checked 300 metadata-only changes and 300 protected-field mutations. |

LabProof applies the v18.1 authorization pattern to a concrete operation. The [review export command](REVIEW-EXPORT.md) binds an approval to one source manifest, an optional remediation brief, and one destination. It consumes approvals transactionally across processes. Closing a task ends its export authority in that ledger. The verifier opens artifacts through directory handles on supported POSIX systems and checks the opened file before reading. The evidence comparison flags linked records with identical captured text or a shared reported execution ID.

The v18.1 reviewer proposed complete mediation in an instrumented MCP host, a model-based benchmark against matched baselines, key separation and rotation, a cross-language argument encoding, and independent review of the host and traces. These are future research directions. The local export tests exercise the LabProof command and ledger. The archived conformance study measures its own generated cases.

Archive sources are `README_ALL.md`, `OMEGA_Research_Loop_v18_1/ARCHIVE_CONTEXT.md`, `REPORT.md`, `REVIEWER_REPORT.md`, and `papers/OMEGA_v15_Research_Note.pdf`.

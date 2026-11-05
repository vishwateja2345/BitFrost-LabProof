# Offline evaluation protocol — not measured effectiveness

This protocol defines future evaluation. No held-out accuracy, vulnerability recall or human review quality result is claimed.

## Keep implementation checks separate

Unit tests, malformed-input tests, synthetic control outcomes, artifact consistency, browser journeys and clean installation checks answer implementation questions. Historical LabProof language-pack controls are purpose-built examples, not independently selected targets.

## Candidate corpus and split

Before tuning, independently review and freeze a corpus manifest containing case ID, family/entity, source provenance, allowed scope, expected outcome, rationale and reviewer identity claim. Record disagreements rather than resolving them by consulting the system output. Do not treat an identity claim as authenticated review.

- Only authorized synthetic fixtures. Split by fixture family and underlying defect mechanism, not by random variants of the same program. Include defective, corrected, normal and ambiguous cases, malformed/truncated output and intentionally missing controls. Keep controls/replays tied to their parent case. New tool families require their own containment and parser acceptance first.

Use separate development, validation and sealed test partitions. Publish the split manifest and hashes before reporting results. Reserve the sealed test set for a fixed release candidate; reusing it for tuning invalidates the held-out claim. No corpus or independent gold-label review is supplied by this release.

## Measures and reporting

Report sample counts and denominators per family, verdict and abstention category. Include an outcome/confusion table, abstention coverage, false promotion of ambiguous/missing-control cases, and reproducibility failures. Additionally report measured target invocations, replay completion, cleanup failures and budget exhaustion; unknown measurements remain null. Do not collapse these into an unsupported security or confidence score.

Report uncertainty and review disagreement; small synthetic samples do not establish generalization. Compare a preregistered fixed baseline and any selector with identical budgets and separate held-out families.

## Stop conditions

Stop on containment/cleanup failure, unsupported provisioning, source-to-wheel mismatch, missing controls, data leakage between partitions or unreviewed labels. Preserve blocked/inconclusive states and failed attempts. Never weaken sandbox policy, run fixtures on the host or use unauthorized live sources to complete an evaluation.

## Implemented mechanics: synthetic planner benchmark

`labproof evaluate-planner` applies this protocol's mechanics to one narrow, fully synthetic task: choosing read-only observations to name a seeded condition. Rules are fixed in source, policies are selected on development cases only and frozen, the test split is scored once with paired case-level bootstrap intervals, unpolluted and polluted cases are reported separately, and `verify-planner-evaluation` recomputes every artifact byte for byte. It does **not** supply an independently reviewed corpus, human labels, fixture-family or time-period splits, or any measurement of real tools, targets, models or sources. The test split shares a simulator family with development (with shifted pollution and probe quality), a single run cannot show when the rules were fixed, and a favorable result supports only that benchmark.

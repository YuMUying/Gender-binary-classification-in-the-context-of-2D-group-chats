# Annotation Guidelines (English version)

Corresponds to Appendix A of the paper. Version: 2026-09-08. Chinese authoritative version: `guideline.zh.md`.

## Labels

- **F** = female.
- **SM** = soft-register male: a male whose softened style leads style-based classifiers to judge him female.
- **M** = other males.
- **Unknown** = insufficient evidence; candidate placed on the observation list (delayed adjudication).

The final target of the task is a binary decision; SM is folded into M at evaluation.

## Evidence packet

For each candidate the packet contains: sampled messages, nickname and group-card history, interaction roles, the softness score, the source-community type, and third-party corroboration where available. **Annotators judge only from the packet**; during blinded re-annotation both the ledger's existing label and the model posterior were hidden.

## Operational criteria

- **Softness score** = fraction of a speaker's eligible messages (>= 2 characters) containing any of eleven softness markers: particle clusters (qwq, awa), soft particles (wu, miao, ma, nie, la, ya, heng in Chinese), and wavy dashes.
- **Two-factor prototype score** = 0.5 x softness + 0.5 x min(1, male-core messages / 200).
- **Screening line** for native soft-register females: softness score 0.15, calibrated on confirmed prototype cases (0.09-0.53). Below-line candidates are not excluded outright but require corroborating evidence.

## Decision rules

1. A gender call requires evidence beyond style: interaction roles and corroboration take precedence over register.
2. An SM call requires softened register AND male-side evidence (self-reference context, community role, etc.).
3. Ambiguous cases go to the observation list; adjudication is delayed until the evidence threshold is met.
4. Labels overturned by later evidence are demoted; the old calibration is archived before the new one takes effect.

## Relation to the released data

`annotations_deidentified.csv` provides, for the 190 labeled speakers, an alias, the softness score, the community type, the profile-card gender, and the annotated gender. Third parties can re-derive the 0.15 screening-line hit distribution and compare it with the double-annotation experiment reported in Section 3.3 of the paper.

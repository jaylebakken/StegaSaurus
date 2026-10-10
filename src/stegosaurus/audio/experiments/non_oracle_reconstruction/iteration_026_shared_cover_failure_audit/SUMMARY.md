# Iteration 026: Shared-Cover Failure Audit

## Goal

Determine whether iteration 025's shared seed-`7404` abstention has any bounded phase recovery ridge.

## Result

It does. Both crop directions recover at phase delta `-24` with post-hoc RS cost `9`: trailing uses offset `0`; leading uses offset `16`. The original selected signed phase did not reach these points.

## Decision

Use this as calibration for a separately seeded global `center - 24` validation only. It does not show that one global phase works broadly.

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_026_shared_cover_failure_audit.run
```

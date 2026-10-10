# Iteration 029: Gap Relaxation Audit

## Goal

Check whether the sole iteration 028 trailing abstention is caused by the frozen local pilot rival-gap threshold.

## Result

For seed `7600` trailing crop, every tested gap from `0.24` through `0.14` produced one duration-feasible hypothesis and no RS-successful decoded payload.

## Decision

Reject pilot-gap relaxation as the next recovery lever. The remaining failure is a carrier-reliability or candidate-map-quality problem, not a local pilot erasure-threshold problem.

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_029_gap_relaxation_audit.run
```

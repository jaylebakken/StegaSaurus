# Iteration 024: Leading Phase Audit

## Goal

Map the one leading-crop abstention from iteration 023 before choosing any additional phase rule.

## Result

For seed `7309`, two duration-feasible offsets (`16` and `15`) shared the same phase surface. The inherited center missed at RS cost `19`; deltas `-16`, `-12`, `+12`, and `+16` recovered at RS cost `16`.

## Decision

This is post-hoc calibration only. The resulting signed fixed phase rule is tested separately in iteration 025.

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_024_leading_phase_audit.run
```

# Iteration 022: Trailing Phase Audit

## Goal

Diagnose iteration 021's sole trailing-crop abstention without selecting a production decoder rule from its post-hoc labels.

## Result

For trailing seed `7205`, the duration-feasible offset was `0`. The inherited center phase had RS cost `17`, but several nearby phases recovered the known handle: `-16`, `-12`, `-8`, `-4`, `+8`, `+12`, and `+16` samples yielded costs `15`, `15`, `15`, `15`, `16`, `15`, and `14` respectively.

## Decision

Treat this as calibration only. It motivates a separately seeded phase-rule validation, not a robustness claim or a direct decoder change.

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_022_trailing_phase_audit.run
```

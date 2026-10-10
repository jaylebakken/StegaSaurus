# Iteration 028: Adaptive Phase Fallback

## Goal

Preserve the iteration 021 center path when it has an RS-successful candidate, then try bounded phase deltas `[-24, -16, -12, +12, +16]` only after abstention.

## Results

On fresh seeds `7600-7609`, leading crops recovered `10/10` and every selected result had post-hoc RS cost at most `16` (median `9.5`). Trailing crops recovered `9/10`, with all nine selected results within budget (median `9`). One trailing sample invoked the fallback but remained an abstention. No unwatermarked or wrong-secret control selected a result.

## Decision

The fallback is safer than a globally fixed phase bias but does not reach the requested reliable trailing recovery threshold. The remaining error is not fixed by the phase grid used here.

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_028_adaptive_phase_fallback.run
```

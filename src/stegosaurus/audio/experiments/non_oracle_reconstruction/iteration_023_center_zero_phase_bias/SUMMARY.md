# Iteration 023: Center-Zero Phase Bias

## Goal

Validate the iteration 022 calibration rule: add `+16` analysis samples only when the blind duration-model center is zero.

## Results

On fresh seeds `7300-7309`, the rule recovered trailing crops `10/10` with all selected RS costs at most `16` (median `10.5`). Leading crops recovered `9/10`, with all selected costs at most `16` (median `11`). Neither unwatermarked nor wrong-secret controls produced a selected result.

## Decision

The trailing gain did not eliminate leading abstentions, so this fixed phase bias is not promoted. See iteration 024 for the separate leading-case audit.

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_023_center_zero_phase_bias.run
```

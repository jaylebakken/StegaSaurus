# Iteration 027: Negative Phase Bias Validation

## Goal

Validate a global duration-model center-minus-24 sample bias on fresh seeds `7500-7509`.

## Results

The rule recovered `9/10` trailing and `8/10` leading crops. Only `8/10` selected results per crop had post-hoc RS cost at most `16`; controls did not select outputs.

## Decision

Reject this fixed phase rule. The shared-cover calibration recovery does not generalize and can push selected results beyond the RS budget.

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_027_negative_phase_bias_validation.run
```

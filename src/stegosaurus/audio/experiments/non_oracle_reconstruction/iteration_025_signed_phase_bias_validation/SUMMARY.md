# Iteration 025: Signed Phase Bias Validation

## Goal

Validate a fixed rule selected from the two phase audits: use center `+16` when the center is zero and center `+12` otherwise.

## Results

On fresh seeds `7400-7409`, the rule recovered `9/10` trailing and `9/10` leading crops. Each selected recovery was correct, but one selected trailing result had post-hoc RS cost `17`, and seed `7404` abstained under both crop directions. Negative controls had no selected outputs.

## Decision

Reject the signed fixed phase rule. Its audit-derived offsets do not generalize across the fresh fixture.

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_025_signed_phase_bias_validation.run
```

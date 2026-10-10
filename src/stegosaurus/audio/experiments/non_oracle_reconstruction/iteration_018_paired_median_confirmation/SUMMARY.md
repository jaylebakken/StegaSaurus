# Iteration 018: Paired Median Confirmation

## Goal

Confirm or reject the fixed five-phase median combiner against center-only decoding on identical fresh crop inputs, stratifying the comparison by shared blind coarse/center feasibility.

## Method

- Covers: ten fresh seeded, 30-second synthetic music-like variants with seeds `7000-7009`, unused by prior crop experiments.
- Attacks: unchanged `250 ms` leading and trailing crops.
- Shared alignment: unchanged blind keyed coarse scan and deterministic one-edge-model center phase.
- Strategies: unchanged `center_only` and fixed `median_neighborhood_5` with offsets `[-8, -4, 0, +4, +8]`. No phase evidence ranking, payload selection, or parameter tuning occurs.
- Pairing: both strategies process the same transformed watermarked input, controls, carrier plan, and alignment outcome for each attack/seed. Paired analysis counts only shared center-feasible trials.
- Controls: independently decoded transformed unwatermarked and wrong-secret samples for every strategy/crop/cover.

## Results

| Crop attack | Strategy | Exact recovery | Conditional center recovery | Median RS cost | Negative-control accepts |
| --- | --- | ---: | ---: | ---: | ---: |
| 250 ms trailing crop | Center only | 7 / 10 | 7 / 7 | 12.5 | 0 / 20 |
| 250 ms trailing crop | Five-phase median | 7 / 10 | 7 / 7 | 11.0 | 0 / 20 |
| 250 ms leading crop | Center only | 6 / 10 | 6 / 7 | 11.5 | 0 / 20 |
| 250 ms leading crop | Five-phase median | 6 / 10 | 6 / 7 | 10.5 | 0 / 20 |

All forty fresh-cover strategy/crop decodes complete without execution failures or exact known-handle control accepts. The strategies share identical coarse acceptance and deterministic-center feasibility in every paired trial, as intended.

The primary paired result shows **no recovery transition** attributable to median combining. Among seven shared-feasible trailing trials, both strategies recover all seven. Among seven shared-feasible leading trials, both recover six and both fail one. There are zero median-only and zero center-only recoveries.

Median combining changes byte-level damage but not the correction outcome on this seed set: its RS-cost delta relative to center-only ranges from `-2` to `+2` symbols, with median delta `0` for both crop directions. It reduces several already-recoverable costs, but also increases others; none cross the 14-symbol recovery boundary.

## Interpretation Rules

- The paired analysis is the primary combiner comparison; unconditional results additionally include synchronization failures that neither combiner can repair.
- This remains synthetic single-edge-crop evidence only.
- No post-hoc strategy or parameter selection is permitted from this confirmation run.

## Interpretation

- The paired experiment does not support further optimization of this fixed median combiner as the highest-value path. Its apparent gain in iteration 016 does not reproduce as a same-input recovery advantage here.
- Median aggregation may smooth payload evidence modestly, but it cannot address the three non-feasible coarse paths per crop direction and has not demonstrated a consistent ability to move marginal feasible failures across the Reed--Solomon boundary.
- Coarse synchronization remains the largest observed source of unrecoverable crop loss. Among payload-layer interventions, a parity-allocation change is now more plausible than additional median tuning, but it requires an explicit registry-handle entropy and collision/reissue decision.
- These observations remain restricted to this synthetic fixture and named crop settings.

## Decision

Freeze the five-phase median implementation as an evaluated candidate; do not add further median variants now. The next decision is architectural: either preserve the 48-bit handle and focus on coarse synchronization, or approve a registry model for a shorter collision-checked handle and test a fixed-codeword `5-byte payload + 15 parity` configuration. Any parity test must be paired on fresh covers and retain byte-level RS, coarse-feasibility, and control reporting.

## Reproduce

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_018_paired_median_confirmation.run
```

The complete strategy records and same-input paired transition archive are retained in `RESULTS.json` beside this summary.

# Iteration 017: Fixed Median Held-Out Validation

## Goal

Validate iteration 016's exact fixed five-phase median payload combiner on another disjoint seed set without changing its phase offsets, aggregation rule, alignment logic, transport allocation, or decision thresholds.

## Method

- Covers: ten fresh seeded, 30-second synthetic music-like variants with seeds `6900-6909`, unused by every prior crop study.
- Attacks: unchanged `250 ms` leading and trailing crops.
- Alignment: unchanged secret-pilot coarse scan and deterministic one-edge-model center phase.
- Combiner: exactly `[-8, -4, 0, +4, +8]` sample offsets around that center, median payload score per physical carrier, then unchanged four-replica extraction and `6-byte + 14-parity` Reed--Solomon recovery.
- Controls: independently decoded transformed unwatermarked and wrong-secret samples for each crop and cover.

## Results

| Crop attack | Coarse accepts | Center feasible | Exact recovery | Conditional center recovery | Median / maximum RS cost | Negative-control accepts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 250 ms trailing crop | 8 / 10 | 7 / 10 | 3 / 10 | 3 / 7 | 15 / 20 | 0 / 20 |
| 250 ms leading crop | 7 / 10 | 5 / 10 | 3 / 10 | 3 / 5 | 18 / 20 | 0 / 20 |

All twenty fresh-cover crop decodes complete without execution failures. Every transformed unwatermarked and wrong-secret control remains an exact known-handle non-match.

The fixed median strategy does not reproduce iteration 016's `5 / 10` result on this new seed set. It recovers three trials per crop direction. Trailing feasible failures occur at RS costs `15` or `16`; leading feasible failures occur at `15` or `16`; other failures are deliberate all-erasure outputs after coarse abstention or an offset incompatible with the bounded center model.

## Interpretation Rules

- This is a fixed-strategy validation, not an optimization study. Do not alter the phase offsets, aggregation, or thresholds based on these results.
- Report unconditional and center-feasible recovery separately.
- The result remains limited to the named synthetic single-edge crop fixture.

## Interpretation

- This standalone confirmation does not establish that the fixed median combiner transfers reliably across fresh synthetic covers. Its unconditional outcomes are lower than iteration 016's, while controls remain clean.
- It also does not establish that median combining is worse than center-only on these covers: iteration 017 deliberately validates only the fixed median strategy and lacks a paired same-seed center-only arm. Seed-to-seed variation in coarse acceptance and center-phase channel damage remains confounded with the combiner result.
- The per-trial RS margins reinforce the earlier conclusion that feasible cases often miss recovery narrowly (`15` or `16` against a `14`-symbol budget), but coarse synchronization remains a separate high-impact failure mode.
- No parameter change is warranted from this result alone.

## Decision

Do not promote the five-phase median combiner beyond experimental status. The next study should run a paired center-only versus fixed-median comparison on another fresh seed set, stratify results by identical coarse/center feasibility, and pre-register a combined analysis across iterations 016 and 017. Only after that comparison should the project evaluate a separately predeclared alternative aggregation rule or a fixed-codeword `5-byte + 15-parity` tradeoff.

## Reproduce

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_017_fixed_median_held_out_validation.run
```

The complete machine-readable archive for all fresh-cover trials and controls is retained in `RESULTS.json` beside this summary.

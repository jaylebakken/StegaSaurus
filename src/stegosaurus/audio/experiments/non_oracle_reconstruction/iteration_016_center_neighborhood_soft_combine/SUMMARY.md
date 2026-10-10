# Iteration 016: Center-Neighborhood Soft Combine

## Goal

Measure whether robustly combining payload evidence from a small fixed neighborhood around the deterministic model-center phase improves fresh-cover crop recovery over the single-center decoder.

## Method

- Covers: ten fresh seeded, 30-second synthetic music-like variants with seeds `6800-6809`, disjoint from all prior crop studies.
- Attacks: unchanged `250 ms` leading and trailing crops.
- Alignment: unchanged blind keyed coarse frame scan plus exactly one deterministic duration-model center phase. Neither strategy performs residual pilot ranking or uses a phase label.
- Strategies: `center_only` uses the center phase once. `median_neighborhood_5` evaluates center offsets `-8`, `-4`, `0`, `+4`, and `+8` samples, then takes the median available payload score for each physical carrier before ordinary four-replica extraction and Reed--Solomon recovery.
- Controls: independently decoded transformed unwatermarked and wrong-secret inputs under each strategy.

## Results

| Crop attack | Strategy | Exact recovery | Conditional center recovery | Median / maximum RS cost | Negative-control accepts |
| --- | --- | ---: | ---: | ---: | ---: |
| 250 ms trailing crop | Center only | 4 / 10 | 4 / 7 | 16 / 20 | 0 / 20 |
| 250 ms trailing crop | Five-phase median | 5 / 10 | 5 / 7 | 15 / 20 | 0 / 20 |
| 250 ms leading crop | Center only | 4 / 10 | 4 / 6 | 16 / 20 | 0 / 20 |
| 250 ms leading crop | Five-phase median | 5 / 10 | 5 / 6 | 15 / 20 | 0 / 20 |

All forty fresh-cover strategy/crop trials complete without execution failures. The strategies have identical coarse acceptance and center feasibility because they share the exact same synchronization path; the median operates only after a deterministic center is available.

The median strategy improves each crop direction by one exact recovery. In the paired fresh trial that changes outcome, the center-only RS cost is `15`, one symbol beyond budget, while the fixed median neighborhood reduces it to `13` and recovers exactly. The median also increases one already-recoverable trial's cost from `8` to `12`, so it is a modest robustness tradeoff rather than uniformly superior carrier evidence.

## Interpretation

- The fixed `±8`-sample median neighborhood provides preliminary fresh-fixture evidence that phase-local payload aggregation can recover marginal byte damage without changing the codeword, parity budget, or coarse synchronization policy.
- It does not address coarse failures: three trailing and four leading paths remain center-infeasible or incorrectly aligned before either strategy can extract payload evidence.
- The gain is small (`+1 / 10` per direction) and arises on one paired seed, so this experiment cannot select the median combiner for production or imply crop robustness.
- Zero exact known-handle accepts in the limited controls are regression evidence only, not an open-world false-positive estimate.

## Decision

Keep the five-phase median as a candidate payload combiner. The next study should validate this exact fixed combiner on a further fresh seed set and compare it against a predeclared trimmed-mean or confidence-weighted alternative only if its weights are fixed before execution. Preserve the 20-byte transport, coarse/center reporting, and negative controls.

## Interpretation Rules

- The neighborhood is fixed before execution and derived only from the deterministic center; it is not a pilot-evidence or payload-outcome search.
- This study still supports only the declared bounded single-edge crop model and synthetic fixture.
- Compare unconditional recovery, conditional center feasibility, RS damage, and controls separately.

## Reproduce

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_016_center_neighborhood_soft_combine.run
```

The complete machine-readable paired trial archive is retained in `RESULTS.json` beside this summary.

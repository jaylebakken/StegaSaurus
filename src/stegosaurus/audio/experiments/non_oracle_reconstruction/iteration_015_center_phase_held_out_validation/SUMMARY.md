# Iteration 015: Center-Phase Held-Out Validation

## Goal

Validate the deterministic model-center sample phase on fresh covers after iteration 014 found that residual pilot rank is not a reliable selector.

## Method

- Covers: ten fresh seeded, 30-second synthetic music-like variants with seeds `6700-6709`, never used by iterations 011-014.
- Attacks: unchanged `250 ms` leading and trailing crops.
- Transport and coarse synchronization: unchanged 6-byte handle, 14 Reed--Solomon parity symbols, contrastive profile, frozen payload thresholds, and blind `±32` keyed frame-offset scan.
- Residual selection: no residual phase evidence scan, rank, post-hoc phase label, or oracle map. For each accepted coarse result, use exactly the bounded one-edge-crop model center derived from nominal duration, received sample-length deficit, coarse offset, and hop size.
- Controls: independently decoded transformed unwatermarked and wrong-secret samples per crop and fresh cover.

## Results

| Crop attack | Coarse accepts | Center feasible | Exact recovery | Conditional center recovery | Median / maximum RS cost | Negative-control accepts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 250 ms trailing crop | 10 / 10 | 8 / 10 | 6 / 10 | 6 / 8 | 14 / 20 | 0 / 20 |
| 250 ms leading crop | 8 / 10 | 7 / 10 | 5 / 10 | 5 / 7 | 15.5 / 20 | 0 / 20 |

All twenty fresh-cover crop decodes complete without execution failures. Every transformed unwatermarked and wrong-secret control remains an exact known-handle non-match.

The deterministic center-phase model transfers beyond the telemetry fixture: when it is feasible, it recovers six of eight trailing and five of seven leading crop trials. The model uses center phase `0` for coarse offset `0`, `96` samples for the common leading coarse offset `16`, and `-160` samples for the valid leading coarse offset `15`; it does not consult phase evidence rank or post-hoc crop labels.

Recovery failures split into two types. Five trials have no feasible deterministic center because coarse synchronization abstains or returns an offset incompatible with the bounded one-edge model. Four feasible center-phase trials exceed the 14-symbol Reed--Solomon budget at RS cost `17`, so their phase geometry is usable but residual carrier damage remains too high for the current codeword allocation.

## Interpretation Rules

- This is a fresh synthetic-cover validation, not recorded-audio or general-edit robustness evidence.
- Report coarse-scan acceptance separately from conditional payload recovery; phase-infeasible results are intentional erasures, not successful synchronization.
- The model remains restricted to the declared single-edge crop setting.

## Interpretation

- The fresh-cover result supports retaining deterministic center-phase reframing as a candidate crop-alignment component. It is not yet reliable enough for a crop-robustness claim: unconditional recovery is `6 / 10` trailing and `5 / 10` leading.
- Coarse synchronization is the first remaining bottleneck: it prevents a center-phase attempt on three trailing and three leading trial paths, including incorrect accepted offsets and abstentions.
- The second bottleneck is correction headroom after feasible alignment. The failed feasible trials cost `17`, just beyond the 14-symbol budget, so a later study should distinguish payload soft-combining improvements from a larger codeword or different payload/parity tradeoff.
- These are fresh synthetic-cover measurements only; no result applies to recorded audio, codecs, other DSP, arbitrary crop lengths, or multiple timing edits.

## Decision

Keep deterministic center-phase reframing as the current blind crop-alignment candidate, but do not claim it supports either crop direction. The next study should use fresh covers to compare a narrowly bounded center-neighborhood payload soft combiner against the single-center decoder while retaining the same coarse scan, 20-byte transport, controls, and attack definitions. It must report coarse acceptance, conditional recovery, and byte-level RS damage separately.

## Reproduce

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_015_center_phase_held_out_validation.run
```

The complete machine-readable archive for all fresh-cover crop trials and controls is retained in `RESULTS.json` beside this summary.

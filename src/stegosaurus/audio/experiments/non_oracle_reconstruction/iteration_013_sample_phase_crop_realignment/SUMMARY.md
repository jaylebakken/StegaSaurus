# Iteration 013: Sample-Phase Crop Realignment

## Goal

Test whether a bounded sample-domain analysis-origin scan after iteration 012's blind coarse keyed offset decision can repair the fractional-hop STFT displacement that prevented leading-crop payload recovery.

## Method

- Fixture: exactly reuse iterations 011 and 012's ten synthetic 30-second covers (`6600-6609`) and unchanged 250 ms leading/trailing crop transforms.
- Transport and payload decoding: unchanged 6-byte registry handle, 14 Reed--Solomon parity symbols, contrastive `4`-pilot / `12`-payload allocation, and frozen local-pilot thresholds.
- Coarse synchronization: unchanged iteration 012 secret-pilot scan over `-32` to `+32` source-frame offsets.
- Residual phase: for an accepted coarse offset, derive the analysis-origin residual implied by the received sample-length deficit under a one-edge-crop model. Search that residual plus/minus `16` samples in `4`-sample increments (`9` candidates), using secret pilot evidence at the coarse frame offset.
- Reframing: positive residuals trim that many received samples before STFT; negative residuals prepend zeros. The chosen residual and coarse offset are then used for full blind candidate ranking.
- Controls: independently scanned transformed unwatermarked and wrong-secret decodes for every crop and cover.

## Results

| Crop attack | Coarse scan accepts | Post-hoc correct coarse offsets | Residual scan accepts | Exact recovery | Median / maximum RS cost | Negative-control accepts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 250 ms trailing crop | 8 / 10 | 7 / 10 | 0 / 10 | 0 / 10 | 20 / 20 | 0 / 20 |
| 250 ms leading crop | 10 / 10 | 7 / 10 | 0 / 10 | 0 / 10 | 20 / 20 | 0 / 20 |

All twenty attacked decodes complete without execution failures, and no transformed unwatermarked or wrong-secret control exactly returns the known handle. Every residual phase scan deliberately rejects, causing an all-erasure payload decode (`184` median carrier erasures) rather than choosing an insufficiently separated timing phase.

This is an acceptance-policy result, not evidence that the keyed residual pilot signal is absent. Best residual mean pilot evidence ranges from `0.097298` to `0.147299` for trailing crops and `0.087041` to `0.153290` for leading crops, comfortably above the `0.02` absolute threshold. However, the nearby four-sample STFT-origin candidates are highly correlated: their best-minus-runner gaps range from `0.000418` to `0.003448` for trailing and `0.000171` to `0.003497` for leading, all below the inherited `0.005` acceptance requirement.

## Interpretation Rules

- This search is restricted to a single bounded edge-crop model and does not support arbitrary insertion, deletion, or time-scale edits.
- Known crop direction, sample displacement, and encoder maps are not decoder inputs. They are post-hoc labels only.
- The reused fixture provides a direct comparison with iteration 012, not a held-out robustness claim.

## Interpretation

- The coarse frame scan remains useful: it reproduces iteration 012's accepted coarse-offset pattern, including seven post-hoc correct leading and seven correct trailing offsets.
- Applying the coarse frame scan's gap threshold unchanged to dense sample-phase candidates is overly conservative. Candidate phases only four samples apart share most of their STFT content, so a large best-minus-runner separation is not an appropriate expectation.
- Because the decoder abstains before payload extraction, iteration 013 cannot measure whether the selected sample phase would improve leading-crop recovery. It must not be treated as a leading-crop failure of the underlying phase-alignment idea.
- The zero known-handle control accepts remain regression evidence only; they do not estimate open-world false positives.

## Decision

Do not lower the residual gap threshold ad hoc inside this completed iteration. The next study should first collect post-hoc residual-phase telemetry across the nine candidates: selected pilot evidence, phase distance from the known fixture label, payload RS cost at every phase, and control behavior. That calibration can choose a residual-specific acceptance policy on a separate validation set, then test it on fresh covers. Keep the coarse frame policy unchanged.

## Reproduce

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_013_sample_phase_crop_realignment.run
```

The complete machine-readable output for all twenty crop trials and their forty independently scanned controls is archived in `RESULTS.json` beside this summary.

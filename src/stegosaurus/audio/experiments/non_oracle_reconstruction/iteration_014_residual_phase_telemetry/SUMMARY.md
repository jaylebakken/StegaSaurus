# Iteration 014: Residual Phase Telemetry

## Goal

Measure all feasible bounded sample-phase candidates after the existing blind coarse frame scan, rather than applying iteration 013's inherited residual gap threshold.

## Method

- Fixture: exactly reuse the direct-comparison synthetic covers (`6600-6609`) and unchanged `250 ms` leading/trailing crop transforms from iterations 011-013.
- Encoding and coarse synchronization: unchanged 6-byte handle, 14 parity symbols, contrastive `4`-pilot / `12`-payload profile, frozen payload thresholds, and iteration 012 `±32` keyed frame-offset scan.
- Residual candidates: unchanged one-edge-crop phase model and nine candidates centered on its residual, from `-16` to `+16` samples in 4-sample steps.
- Telemetry: for each available phase candidate, record pilot evidence/rank, post-hoc phase error for watermarked inputs, exact token recovery, byte-level RS cost, erasures, and whether a control exactly returns the known handle.
- Streams: watermarked, independently scanned unwatermarked, and independently scanned wrong-secret audio per crop/cover.

## Results

| Crop attack | Watermarked coarse accepts | Feasible phase rows | Center/label phase recovery | Best-evidence phase recovery | Minimum phase-cost median |
| --- | ---: | ---: | ---: | ---: | ---: |
| 250 ms trailing crop | 8 / 10 | 63 | 7 / 10 overall; 7 / 7 feasible | 5 / 7 feasible | 10 |
| 250 ms leading crop | 10 / 10 | 63 | 7 / 10 overall; 7 / 7 feasible | 5 / 7 feasible | 8 |

The `63` phase rows per attack represent seven feasible coarse-aligned trials times nine residual candidates. The remaining trials either abstain during the coarse scan or select a coarse offset incompatible with the bounded one-edge residual model. All phase-level watermarked rows completed without execution failures.

At the post-hoc center/label phase, all seven feasible trailing trials recover exactly at median RS cost `10`, and all seven feasible leading trials recover exactly at median RS cost `9`. This is the first direct evidence that the sample-domain phase model can restore leading-crop payload recovery after the coarse scan succeeds.

The highest pilot-evidence candidate is not the exact labeled phase in any feasible trial and recovers only `5 / 7` per crop. The telemetry therefore rejects the idea of choosing the residual phase solely by maximum pilot evidence. Neighboring phases remain payload-tolerant: phase error `4` or `8` samples recovers `13 / 14` rows in both crop directions, while recovery declines at larger offsets.

All unwatermarked controls abstain before a feasible residual phase is produced. Eighteen wrong-secret phase rows are produced across leading-crop trials, with `0` exact known-handle matches. These limited outcomes are regression controls; they are not a false-positive-rate estimate.

## Interpretation Rules

- These post-hoc labels are not decoder inputs and must not be used to choose a production phase policy directly.
- This study is calibration data only. A residual policy selected from it requires a separate fresh-cover validation.
- The reused synthetic crop fixture does not establish real-audio, codec, DSP, or general edit robustness.

## Interpretation

- The model-derived residual center is more useful than maximum local pilot evidence on this fixture. It is computed from the blind coarse offset, known nominal source duration, received length deficit, and bounded one-edge-crop modelnot from the retained encoder map or post-hoc label.
- Maximum pilot evidence is a poor single-phase selector because adjacent STFT origins share most of their audio and can reorder their evidence without materially changing payload quality.
- The result remains conditional on correct/feasible coarse synchronization: only seven of ten trials per crop reach the center-phase payload measurement.
- The broad `±8` sample recovery ridge suggests a future phase-neighborhood combiner may be viable, but this telemetry alone cannot justify its design or security policy.

## Decision

Keep this iteration as calibration data only. The next experiment should pre-register the deterministic model-center residual (no residual pilot winner selection), retain the unchanged coarse scan and controls, and validate it on fresh unseen cover seeds. It should report coarse acceptance separately from conditional center-phase recovery. Do not use the post-hoc labels or best-evidence ranks in that decoder.

## Reproduce

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_014_residual_phase_telemetry.run
```

The complete machine-readable archive contains every phase-level watermarked and control row in `RESULTS.json` beside this summary.

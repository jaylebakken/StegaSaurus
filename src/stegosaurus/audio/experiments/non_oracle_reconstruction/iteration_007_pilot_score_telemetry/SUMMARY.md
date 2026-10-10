# Iteration 007: Pilot Score Telemetry

## Goal

Create an offline diagnostic table for future non-oracle decoder design. The table records blind two-candidate pilot decisions and payload evidence, then joins retained oracle labels only after reconstruction to determine which scores distinguish correct map choices, wrong choices, and downstream Reed--Solomon damage.

## Method

- Covers: ten seeded, 30-second synthetic music-like variants.
- Encoder: iteration 005 contrastive calibration with the fixed 4-pilot / 12-payload pair allocation.
- Decoder: select the larger expected-pilot candidate without applying a new threshold policy. No encoder frame map, token bit, oracle score, or telemetry is supplied to that reconstruction path.
- Post-hoc labels: compare the selected frame to the retained encoder map and the payload decision to the known carrier bit only after the blind decision is recorded.
- Tables: one physical-carrier row per replica and carrier position; one four-copy logical-carrier row per framed carrier bit; one deinterleaved codeword-byte row per Reed--Solomon symbol.

## Table Schema

`RESULTS.json` contains 7,360 physical rows, 1,840 logical-carrier rows, and 200 codeword-byte rows. Physical rows include candidate frame indices, selected and rival expected-pilot margins, pilot gap, selected payload score and margin, oracle-map correctness, physical payload correctness, and the associated codeword bit and byte. Logical rows contain the four-copy combined payload score, observed carrier bit, expected bit, erasure state, and codeword mapping. Byte rows contain expected and observed codeword bytes, error or erasure classification, and each byte's `0`, `1`, or `2` Reed--Solomon cost contribution.

## Results

| Metric | Result |
| --- | ---: |
| Median embedding SNR | 41.67 dB |
| Blind raw map accuracy | 96.36% |
| Median selected-pilot margin, correct map | 0.4844 |
| Median selected-pilot margin, wrong map | 0.2572 |
| Median pilot gap, correct map | 0.7306 |
| Median pilot gap, wrong map | 0.1406 |
| Threshold-free logical carrier-bit errors | 213 / 1,840 |
| Threshold-free byte erasures | 0 / 200 |
| Threshold-free unknown byte errors | 117 / 200 |
| Median per-trial RS cost | 24 |
| Trials within the 12-symbol RS budget | 0 / 10 |

The pilot-gap distribution is more useful than absolute pilot strength. Correct-map gaps have quantiles `0.2685`, `0.4416`, `0.7306`, `1.1113`, and `1.5437` at the 10th, 25th, 50th, 75th, and 90th percentiles; wrong-map gaps have `0.0249`, `0.0624`, `0.1406`, `0.3203`, and `0.6143`. The distributions overlap, so these values inform a policy search but do not justify a threshold on their own.

## Interpretation

- Local-pilot gap separates correct and wrong map choices substantially better than absolute selected-pilot margin, making the gap the primary candidate control for the next decoder policy.
- For illustration only, a gap of `0.32` retains 83.6% of physical carriers with a 1.09% wrong-map rate among retained positions; a gap of `0.48` retains 69.3% with a 0.69% wrong-map rate. These are physical-layer observations, not token-recovery results, because four-copy combining, framing, interleaving, and byte erasures must still be replayed.
- The table is an offline experimental artifact. It is not embedded in audio, transmitted to a decoder, or part of the final watermark format.

## Decision

Use this telemetry only to define a future threshold policy. The next experiment should replay the full channel from raw physical rows to Reed--Solomon bytes for a declared wider gap-focused threshold set, select one policy on a calibration split, and validate that frozen policy blindly on fresh unseen variants. Oracle labels remain post-hoc diagnostics only.

## Reproduce

The complete machine-readable telemetry tables are archived in `RESULTS.json` beside this summary.

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_007_pilot_score_telemetry.run
```

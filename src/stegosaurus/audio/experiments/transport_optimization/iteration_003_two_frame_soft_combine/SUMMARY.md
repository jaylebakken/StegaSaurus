# Iteration 003: Two-Frame Soft Combining — 2026-10-08

## Goal And Pipeline State

This iteration repeats each of the 144 framed/interleaved token bits in two source-frame halves of a 30-second synthetic music-like cover signal. It follows iteration 002, where one oracle-aligned frame per bit produced 50 confident bit errors and 3 erasures on a clean six-second fixture. The pipeline remains detector-only outside this isolated experiment; frame mapping is still oracle supplied.

## Method

- **Cover:** deterministic 30-second, 16 kHz, music-like mono waveform.
- **Token transport:** 8 opaque payload bytes, 8 Reed--Solomon parity bytes, 128 data bits, and two 8-bit sync frames for 144 logical carrier bits.
- **Repetition:** every logical carrier bit is embedded twice, once in each half of the cover signal. The selected replica positions are at least 938 STFT hops apart, approximately 15.0 seconds with the 256-sample hop at 16 kHz.
- **Combining:** extraction retains each copy's signed score, then uses an absolute-score-weighted signed average. A low-confidence combined result becomes an erasure.
- **Sweep:** relative spectral modulation values `0.48`, `0.60`, `0.72`, and `0.84`.

## Clean Oracle-Aligned Results

| Relative difference | Sample SNR (dB) | Bit errors | Carrier erasures | Byte erasures | Token recovered |
| ---: | ---: | ---: | ---: | ---: | --- |
| 0.48 | 56.74 | 36 | 3 | 3 | No |
| 0.60 | 54.82 | 26 | 1 | 1 | No |
| 0.72 | 53.27 | 23 | 1 | 1 | No |
| 0.84 | 51.96 | 17 | 0 | 0 | No |

All four settings exhausted Reed--Solomon's correction budget and returned `codeword could not be corrected`. No attack was needed to demonstrate that the transport remains below the clean-channel recovery gate.

## Interpretation

Two-frame repetition and soft combining improve the clean baseline materially:

```text
iteration 002, one frame at 0.48: 50 confident bit errors
iteration 003, two frames at 0.48: 36 confident bit errors
iteration 003, two frames at 0.84: 17 confident bit errors
```

The improvement is not sufficient. The 17 remaining confident bit errors are unknown errors, which are more expensive to Reed--Solomon than declared erasures. The highest tested margin also lowers sample SNR by about 4.8 dB relative to the lowest setting, so simply increasing modulation is not a free solution.

## Next Decision

Do not add an opaque fingerprint to the production path yet. The 30-second cover budget can support a four-frame repetition experiment (`144 × 4 = 576` physical carrier frames) while retaining substantial space in the roughly 1,875-frame cover. The next iteration should compare:

1. four-frame confidence-weighted combining at the current margin sweep;
2. erasure thresholds that reject weak or conflicting evidence rather than count it as an unknown error;
3. byte-level RS recovery rate before any compression or synchronization attack.

Only a configuration that repeatedly recovers the clean token should progress to attacked-token measurements.

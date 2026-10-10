# Iteration 002: Oracle-Aligned Token-Bit Experiment — 2026-10-08

## Purpose

This experiment tests whether the current spectral pilot can carry the schema's complete opaque-token bit plan, rather than merely provide aggregate statistical detection evidence. It is deliberately **oracle aligned**: extraction receives the exact STFT frame indices selected during embedding. A deployable decoder will not have that side information, so this is an optimistic transport baseline.

## Setup

- **Fixture:** deterministic six-second, 16 kHz, speech-like mono waveform used by the audio tests.
- **Token:** fixed 8-byte opaque value `0123456789abcdef`.
- **Transport:** 8 payload bytes plus 8 Reed--Solomon parity bytes, serialized and interleaved into 128 data bits; two 8-bit synchronization frames produce 144 required carrier bits.
- **Carrier mapping:** each planned bit is embedded into the next eligible unique STFT frame. All 144 planned carriers fit in 144 selected frames.
- **Extraction:** the experiment revisits those exact frame indices, emits `0`, `1`, or erasure, then calls the schema's normal deframe, deinterleave, byte-erasure, and Reed--Solomon recovery path.

## Results

| Condition | Confident bit errors | Carrier erasures | Byte erasures | Token recovered |
| --- | ---: | ---: | ---: | --- |
| Clean oracle-aligned WAV | 50 | 3 | 3 | No |
| MP3 96 kbps | 50 | 1 | 1 | No |
| 30 dB white noise | 52 | 4 | 2 | No |
| 44.1 kHz resample round trip | 50 | 3 | 3 | No |

The clean embedding measured 54.03 dB sample SNR. Despite that low waveform difference and the oracle frame map, Reed--Solomon reported `codeword could not be corrected` in every condition. No corrected-byte result was produced.

## Interpretation

This is the expected distinction between a statistical detector and a multibit channel:

- The detector succeeds from an aggregate surplus of slightly biased frame observations.
- The token experiment requires each individual planned carrier bit to be accurate enough to reconstruct a 16-byte codeword.
- Fifty confident raw bit errors far exceed the current 8-parity-symbol Reed--Solomon budget. The three erased bytes are not the primary failure; the unknown erroneous bits are.

Therefore, the current carrier is **not ready** to embed an opaque fingerprint, even under oracle alignment and before attack robustness is considered. No attribution integration should be added until a clean-channel token recovery gate passes reliably.

## Next Experiments

1. **Increase individual carrier margin:** measure a per-pair or per-frame embedding rule that targets a minimum extractable decision margin instead of applying only a relative log-ratio shift.
2. **Use repeated evidence per token bit:** compare one, two, and three frame observations per planned bit with confidence-weighted voting and explicit erasures. The six-second fixture has enough observed-frame budget for a two-fold repetition experiment, but not a free three-fold budget.
3. **Record soft decisions:** retain signed pair scores and test likelihood or majority combining before hard bit decisions.
4. **Re-run byte-level accounting:** for every profile recipe, report raw bit errors, carrier erasures, byte erasures, corrected bytes, and full-token recovery rate.
5. **Replace oracle alignment:** only after clean transport passes should the experiment introduce deterministic carrier selection, sync scanning, non-hop crop recovery, and time-scale alignment.
6. **Authenticate any recovered token:** add versioning and a MAC or authenticated local-ledger reference after transport recovery; Reed--Solomon does not prove origin.

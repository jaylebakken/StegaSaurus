# Iteration 004: Four-Frame Soft Combining

## Goal

Test whether four oracle-mapped STFT-frame copies of each framed and interleaved attribution bit can provide clean-channel recovery for the fixed 8-byte token and 8-byte Reed--Solomon parity budget. Weak combined scores are converted to erasures, then measured at the Reed--Solomon byte-symbol level.

## Method

- Fixture: deterministic 30-second, 16 kHz synthetic music-like mono waveform.
- Transport: 8-byte token, 8 Reed--Solomon parity bytes, keyed interleaving, and two sync bytes: 144 logical carrier bits.
- Repetition: every logical bit appears in four disjoint contiguous STFT-frame quarters, using 576 physical carrier frames total.
- Embedding: `relative_difference=0.84`; measured waveform embedding SNR was 48.76 dB.
- Extraction: oracle source-frame maps, signed absolute-score-weighted combining, and a sweep of post-combination confidence thresholds.
- Verification: a returned decoder payload counts only when it exactly equals the known embedded token. This oracle-only equality check stands in for the authenticated token format that a production attribution path will require.

## Results

| Threshold | Bit Errors | Bit Erasures | Unknown Byte Errors | Byte Erasures | RS Cost / 8 | Decoder Returned | Exact Token Match |
| ---: | ---: | ---: | ---: | ---: | ---: | :---: | :---: |
| 0.010 | 8 | 0 | 8 | 0 | 16 | No | No |
| 0.030 | 6 | 5 | 4 | 5 | 13 | No | No |
| 0.050 | 3 | 8 | 2 | 7 | 11 | No | No |
| 0.055 | 3 | 9 | 1 | 8 | 10 | Yes | No |
| 0.060 | 3 | 9 | 1 | 8 | 10 | Yes | No |
| 0.065 | 3 | 9 | 1 | 8 | 10 | Yes | No |
| 0.070 | 3 | 11 | 1 | 10 | 12 | No | No |
| 0.080 | 2 | 14 | 0 | 12 | 12 | No | No |
| 0.120 | 1 | 21 | 0 | 13 | 13 | No | No |

`RS Cost` is `2 * unknown_byte_errors + byte_erasures`; the configured parity budget is eight symbols. All thresholds exceeded the correction bound, so no threshold produced a verified input-token recovery.

## Decision

- Four-copy soft combining lowers clean carrier errors from iteration 003's best 17 to 8 before confidence erasures, but it does not make this transport reliable.
- The `0.055` through `0.065` range caused the Reed--Solomon library to return a payload despite a cost of 10. The bytes did not equal the embedded token, so these are explicitly failures rather than recoveries.
- A Reed--Solomon decode result is error correction, not authenticity. Future opaque tokens need a versioned MAC or authenticated ledger lookup; an unauthenticated returned byte string must not be attributed to a user.
- Do not run attack recovery experiments yet. Clean, authenticated token recovery must succeed repeatedly before testing compression or DSP resilience.

## Next Step

Create iteration 005 to test an attribution format with an explicit authenticity check and lower raw byte error rate through adaptive carrier selection or a stronger per-frame carrier. Retain four-copy spacing, oracle alignment, and byte-level error/erasure reporting until clean recovery is consistently verified.

## Reproduce

```powershell
python -m stegosaurus.audio.experiments.transport_optimization.iteration_004_four_frame_soft_combine.run
```

# Iteration 005: Duration And Reed--Solomon Parity Budget

## Goal

Find the smallest tested Reed--Solomon parity budget that exactly recovers the known 8-byte token with four-copy soft combining, and determine the shortest successful cover duration between 30 seconds and two minutes.

## Method

- Fixture: one deterministic 16 kHz, synthetic music-like mono waveform at 30, 45, 60, 90, and 120 seconds.
- Carrier: iteration 004's oracle-aligned, four-quarter frame maps, `relative_difference=0.84`, signed soft-score combining, and exact input-token equality verification.
- Sweep: 8, 10, 12, 16, 20, 24, 32, 40, and 48 Reed--Solomon parity bytes; nine post-combination confidence thresholds from `0.010` to `0.120`.
- Selection: prefer exact token recovery, then the fewest physical carrier frames, then the shortest cover duration. A non-null decoder result that differs from the input remains a failure.

## Best Tested Configuration

The smallest verified plan was **30 seconds with 12 parity bytes** at a confidence threshold of **0.030**:

| Field | Measurement |
| --- | ---: |
| Token bytes | 8 |
| RS parity bytes | 12 |
| Protected codeword bits | 160 |
| Framed logical carrier bits | 184 |
| Four-copy physical carrier frames | 736 |
| STFT frames in the 30-second fixture | 1,876 |
| Frames required per quarter | 184 |
| Frames available per quarter | 469 |
| Embedding SNR | 47.41 dB |
| Unknown byte errors | 2 |
| Declared byte erasures | 6 |
| RS cost / budget | 10 / 12 |
| Exact input-token match | Yes |

The 184 logical bits comprise 160 Reed--Solomon-protected data bits plus three 8-bit synchronization prefixes. The four-copy mapping therefore requires 184 eligible frames in each waveform quarter.

## Duration Analysis

At 16 kHz with a 256-sample STFT hop, the 736 physical-frame plan has an idealized frame-capacity lower bound of about **11.76 seconds**. That assumes every candidate frame is eligible and leaves essentially no selection margin, so it is not a recovery claim.

The shortest **measured** exact recovery was **30 seconds**. The 30-second fixture provides 469 frames per quarter, leaving 285 frames per quarter beyond the 184 required mappings. This is the current practical lower bound for this specific fixture and pipeline; it is not yet a corpus-level production minimum.

| Tested Duration | Smallest Verified Parity | Logical Bits | Physical Frames | Best Threshold | RS Cost / Budget |
| ---: | ---: | ---: | ---: | ---: |
| 30 s | 12 | 184 | 736 | 0.030 | 10 / 12 |
| 45 s | 16 | 216 | 864 | 0.050 | 16 / 16 |
| 60 s | 12 | 184 | 736 | 0.070 | 7 / 12 |
| 90 s | 20 | 256 | 1,024 | 0.050 | 18 / 20 |
| 120 s | 12 | 184 | 736 | 0.050 | 10 / 12 |

Results are intentionally non-monotonic across duration because the four copies occupy different source-frame regions as clip duration changes. More audio creates more capacity and separation, but it does not guarantee that the selected regions have the same spectral quality. The 48-parity configuration could not be embedded at 30 seconds because it needs 504 eligible frames per quarter while that fixture supplies 469 total frames per quarter.

## Decision

- Use **12 parity bytes** as the current experimental default for the 8-byte fingerprint and four-copy carrier layout.
- Treat **30 seconds** as the shortest observed clean recovery duration, not a supported production requirement. Do not infer that 12 seconds or an arbitrary 30-second recording will recover.
- Do not increase parity automatically: larger codewords require more carrier frames and often lower embedding SNR. Several larger budgets verified, but none used fewer than 736 physical frames.
- The known-input equality check is an experiment-only oracle. A real fingerprint must include a versioned MAC or an authenticated ledger lookup before any decoded token can be attributed.

## Next Step

Test the 12-parity, 30-second plan over a varied licensed corpus with independent clips, then measure MP3 and DSP attacks only for candidates that first pass clean authenticated recovery. Report a duration-success curve and quality metrics rather than promoting this single-fixture result to a general guarantee.

## Reproduce

The complete machine-readable output for all 45 duration/parity candidates is archived in `RESULTS.json` beside this summary.

```powershell
python -m stegosaurus.audio.experiments.transport_optimization.iteration_005_duration_parity_budget.run
```

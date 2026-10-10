# Iteration 001: Detector Pilot Benchmark — 2026-10-08

## Purpose

This report records a reproducible, **synthetic-fixture** benchmark of the detector-only spectral WAV pilot. It informs the design of a future opaque fingerprint and attribution transport; it does not demonstrate deployment readiness, perceptual transparency, corpus-level robustness, or adversarial resistance.

## Method

- **Fixture:** deterministic six-second, 16 kHz, speech-like mono waveform used by the focused audio tests.
- **Watermark setup:** `SpectralAudioPilot` with the fixture key and epoch `2026-10-07`.
- **Controls:** each named or stochastic transformation was applied independently to both the marked waveform and the unmarked fixture.
- **Entropy run:** 20 `EntropicAttackProfile` recipes sampled from root seed `20261008`. Every trial records its complete recipe and child seeds for replay.
- **Decision:** the detector reports `verified`, `inconclusive`, or `absent`; the bounded offset scan uses a Bonferroni-corrected p-value.

The clean marked waveform was `verified` with 365 observed frames, 243 matches (66.6%), and corrected p-value `3.83e-09`. The clean unmarked control was `absent` with 364 observations and 51.9% matches. The embedding reported approximately 40 dB sample SNR.

## Fixed Attack Matrix

| Transformation | Marked result | Unmarked control |
| --- | --- | --- |
| MP3 128 kbps | verified | absent |
| MP3 96 kbps | verified | absent |
| MP3 64 kbps | verified | absent |
| 8 kHz resample round trip | inconclusive | absent |
| 44.1 kHz resample round trip | verified | absent |
| Peak normalization to 0.85 | verified | absent |
| 4 kHz low-pass filter | verified | absent |
| 30 dB white noise | verified | absent |
| 0.25-second leading crop | verified | absent |
| Self-concatenation | verified | absent |
| 1.05x time scale | absent | absent |

All 11 transformed controls were `absent`. These are repeated transformations of one synthetic fixture, not independent samples for estimating a false-positive rate.

## Entropy-Profile Results

| Population | Verified | Inconclusive | Absent |
| --- | ---: | ---: | ---: |
| 20 marked stochastic trials | 12 (60%) | 4 (20%) | 4 (20%) |
| 20 unmarked stochastic controls | 0 | 0 | 20 (100%) |

The default profile composes bounded resampling, low-pass filtering, synthetic reverb, slight time scaling, leading crop, noise, gain normalization, and optional MP3. Effects overlap in each recipe, so the following association table is **not causal**:

| Effect present | Trials | Verified / Inconclusive / Absent |
| --- | ---: | --- |
| Resample | 13 | 7 / 4 / 2 |
| Low-pass | 5 | 2 / 1 / 2 |
| Synthetic reverb | 12 | 5 / 3 / 4 |
| MP3 | 6 | 3 / 1 / 2 |
| Leading trim | 4 | 3 / 0 / 1 |
| Time scale | 3 | 1 / 0 / 2 |

The profile result is therefore a design warning: ordinary composite processing already reduces presence verification to 60% on this limited fixture. The direct 1.05x time-scale test is absent, and time-scale-containing stochastic recipes are also often absent. Synchronization is the highest-priority robustness gap.

## Attribution Implications

The current schema defines an 8-byte opaque token with 8 Reed--Solomon parity bytes. Its framed/interleaved transport requires **144 carrier bits**. The clean fixture supplied 365 observed frame decisions, about 2.5 observed decisions per required carrier bit, so a nominal frame-count budget exists.

That is **not** evidence that attribution fits. The current WAV pilot only tests aggregate agreement with a daily pseudorandom pattern. It does not map token bits to audio frames, measure token-bit errors and erasures, deinterleave a received audio codeword, or recover the opaque token after attacks. Reed--Solomon can only correct a codeword when `2 * unknown_symbol_errors + known_symbol_erasures <= parity_symbols`; this must be measured at the byte-symbol level.

## Required Next Steps

1. **Freeze an evaluation protocol:** choose a licensed speech corpus, profile bounds, root seeds, attack counts, control population, false-positive metric, and perceptual-quality metrics before changing the algorithm.
2. **Build an attribution-only experiment:** map the existing 144-bit plan to explicit audio-frame decisions, record each observation as `0`, `1`, or erasure, and report bit and byte error rates per recipe.
3. **Run actual Reed--Solomon recovery:** deinterleave received carrier bits, declare erased bytes, verify full opaque-token recovery, and record the correction budget consumed for every trial.
4. **Address synchronization first:** add alignment resilient to non-hop-aligned crop, insertion/deletion, and time-scale drift before interpreting attribution failures as coding failures.
5. **Authenticate attribution:** bind the recovered opaque token to a versioned MAC or authenticated local-ledger record; Reed--Solomon provides recovery, not authenticity.
6. **Set a gate before fingerprint integration:** do not embed a user fingerprint until the pre-registered presence and token-recovery tests meet their target rates on marked audio while unmarked controls remain below the allowed false-positive rate.

## Reproduction

Use `EntropicAttackProfile` with root seed `20261008` and `AudioPilotBenchmark.evaluate_entropic()` for replayable stochastic trials. The API retains each `EntropicAttackRecipe`; rerun an individual recipe with `profile.apply(audio, recipe)` and the same detector secret and epoch.

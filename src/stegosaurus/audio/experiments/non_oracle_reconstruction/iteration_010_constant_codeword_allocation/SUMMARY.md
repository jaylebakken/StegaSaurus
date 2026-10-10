# Iteration 010: Constant-Codeword Allocation

## Goal

Measure whether replacing an 8-byte opaque token with a shorter registry-backed opaque handle can allocate more Reed--Solomon parity without increasing carrier demand.

## Method

- Covers: ten fresh seeded, 30-second synthetic music-like variants with seeds `6500-6509`.
- Encoder: fixed iteration 005 contrastive calibration, 4 pilot / 12 payload spectral-pair allocation, `500-3800 Hz` band, and `0.95` relative difference.
- Decoder: fixed blind policy from iteration 008: expected-pilot threshold `0.00` and pilot-gap threshold `0.24`.
- Protected codeword: held at 20 bytes in every allocation. The schema retains 3 framing/checksum bytes, so every allocation should use 184 logical carrier bits and 736 four-replica physical placements.
- Allocations: 8-byte token + 12 parity, 7-byte registry handle + 13 parity, and 6-byte registry handle + 14 parity.
- Controls: unwatermarked and wrong-secret blind decodes per cover/allocation. A control is an accept only if it exactly returns the known opaque token or handle.

## Results

| Opaque value / RS parity | Protected bytes | Framed bits | Physical frames | Exact recovery | Median / maximum RS cost | Median SNR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 8-byte token + 12 parity | 20 | 184 | 736 | 7 / 10 | 9 / 14 | 37.24 dB |
| 7-byte registry handle + 13 parity | 20 | 184 | 736 | 8 / 10 | 9.5 / 15 | 37.22 dB |
| 6-byte registry handle + 14 parity | 20 | 184 | 736 | 10 / 10 | 10 / 14 | 37.22 dB |

All thirty trials completed without execution errors. Every unwatermarked and wrong-secret control set records `0 / 10` exact known-token or known-handle accepts. The encoder selected different valid carrier candidates as payload bytes changed, but the plan size, four-replica transport demand, SNR range, frozen policy, and cover seeds remained fixed.

The 8-byte/12-parity allocation misses three covers at RS cost `14`, above its 12-symbol correction budget. The 7-byte/13-parity allocation misses two covers at costs `14` and `15`. The 6-byte/14-parity allocation recovers every cover; its highest observed cost is exactly `14`, consuming its full declared budget.

## Interpretation Rules

- Treat a shorter payload as a versioned registry key, not self-contained user/time metadata and not proof that a truncated hash is collision-safe.
- A production registry must retain complete provenance, namespace/version, collision policy, keying/authentication policy, and issuance/audit records.
- Prefer an allocation only if it improves held-out exact recovery or materially reduces Reed--Solomon failure cost at unchanged carrier demand and no control accepts.

## Interpretation

- On this fresh, synthetic, clean-audio fixture, the 6-byte registry handle with 14 parity symbols is the strongest allocation tested. It improves recovery without requiring additional audio duration, carrier frames, or embedding strength.
- This is a bounded result, not a production selection: the configuration must next be tested on disjoint realistic audio and the named compression/DSP attack suite before it replaces the current baseline.
- A 6-byte value has only 48 bits of identifier space. Use it as a randomly issued or keyed registry lookup handle with collision checks and reissuance, not as a bare digest of user/time data. The registry must hold the original provenance record and an independently verifiable authentication value.

## Reproduce

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_010_constant_codeword_allocation.run
```

The complete machine-readable output for all thirty trials and their controls is archived in `RESULTS.json` beside this summary.

# Iteration 009: Parity Headroom Sweep

## Goal

Measure whether increasing Reed--Solomon parity from 12 to 14 or 16 symbols improves blind non-oracle recovery enough to justify the larger carrier plan.

## Method

- Covers: ten fresh seeded, 30-second synthetic music-like variants with seeds `6400-6409`.
- Encoder: fixed iteration 005 contrastive calibration and the 4-pilot / 12-payload pair allocation.
- Decoder: fixed blind policy from iteration 008: absolute expected-pilot threshold `0.00`, pilot-gap threshold `0.24`.
- Token: unchanged 8-byte opaque value.
- Sweep: 12, 14, and 16 Reed--Solomon parity symbols. Each changes codeword length, framed carrier count, interleaving, candidate strata, and physical carrier demand.
- Controls: unwatermarked and wrong-secret decodes per cover and parity level; a control counts only when it exactly returns the known token.

## Results

| Parity symbols | Framed carrier bits | Physical carrier frames | Exact recovery | Median / maximum RS cost | Median SNR |
| --- | ---: | ---: | ---: | ---: | ---: |
| 12 | 184 | 736 | 10 / 10 | 8.5 / 12 | 38.02 dB |
| 14 | 200 | 800 | 9 / 10 | 8.5 / 19 | 37.72 dB |
| 16 | 216 | 864 | 9 / 10 | 13.5 / 17 | 37.46 dB |

All control sets record `0 / 10` exact known-token accepts. The 12-symbol configuration recovers every declared fresh variant. The 14-symbol configuration has one failure at RS cost 19; the 16-symbol configuration has one failure at cost 17. The results do not imply that lower parity is generally superior; they show that, on this fixed 30-second synthetic fixture, the additional carrier demand changes the channel enough to offset the added correction budget.

## Interpretation

- Increasing parity is not a free correction gain because it increases the framed transport from 184 to 200 or 216 logical carriers, multiplied across four physical replicas.
- The 12-symbol configuration has the smallest carrier plan, the highest observed SNR, and the only `10 / 10` recovery result in this bounded sweep. Keep it as the current full 8-byte-token candidate.
- The result supports separating **total protected codeword length** from **payload-versus-parity allocation**. A shorter opaque payload could increase parity without expanding the carrier plan.
- A hash alone cannot preserve self-contained identity or timestamp information. A shorter payload is appropriate only as a versioned registry-backed opaque identifier or keyed digest whose full provenance record is retained externally and whose collision and authentication model is explicitly evaluated.

## Decision

Do not increase parity beyond 12 for the current 8-byte token on this fixture. The next transport-design study should hold the 20-byte protected codeword and 184-carrier plan constant while comparing, for example, `8 payload + 12 parity`, `7 payload + 13 parity`, and `6 payload + 14 parity` byte allocations. The shortened payload must be a deliberately designed opaque registry handle, not an unqualified truncation of user data or a claim that hashing makes information recoverable.

## Reproduce

The complete machine-readable output for all thirty fresh parity trials and their controls is archived in `RESULTS.json` beside this summary.

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_009_parity_headroom_sweep.run
```

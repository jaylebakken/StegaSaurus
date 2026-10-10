# Iteration 002: Local Selection Pilots

## Goal

Test whether a decoder-known local pilot embedded in every selected carrier frame can replace iteration 001's data-driven candidate-map selection. The decoder must choose each map position only from the pilot signal, then read the opaque payload bit from disjoint spectral pairs in that selected frame.

## Method

- Covers: ten seeded, 30-second synthetic music-like variants per profile.
- Transport: 8-byte token, 12 Reed--Solomon parity symbols, four repeated copies, `relative_difference=0.95`, and the `500-3800 Hz` carrier band.
- Encoder: retains the calibrated two-candidate selection procedure, but partitions its 16 keyed pairs into a local-pilot group and a payload group.
- Profiles: small pilot with 4 pilot and 12 payload pairs; balanced pilot with 8 pilot and 8 payload pairs.
- Decoder: regenerates two observed candidates per stratum, scores only the secret-derived known pilot value to select a frame, and treats weak or ambiguous pilot margins as map erasures. Payload extraction uses the selected frame's payload group only.
- Controls: original unwatermarked cover and watermarked cover under a wrong secret. A control counts only when it exactly returns the known input token.

## Results

| Profile | Exact recovery | Median candidate coverage | Median selected-map accuracy | Median map-erasure rate | Median RS cost | Median SNR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 4 pilot / 12 payload pairs | 0 / 10 | 99.32% | 61.28% | 17.87% | 33 | 41.72 dB |
| 8 pilot / 8 payload pairs | 0 / 10 | 99.46% | 66.23% | 16.17% | 33 | 41.60 dB |

The small profile had median 42 known carrier-bit errors and 3 carrier erasures. The balanced profile had median 40.5 known carrier-bit errors and 2 carrier erasures. Both profiles exceeded the 12-symbol RS budget on every trial. Each profile recorded `0 / 10` exact known-token acceptances for both unwatermarked and wrong-secret controls.

## Interpretation

- Candidate coverage remains high, so the decoder still regenerates nearly all oracle choices as one of two candidates.
- The balanced pilot improves selected-map accuracy over the small pilot, but neither allocation is close to the map accuracy needed for transport recovery.
- The local-pilot split underperforms iteration 001's 84.51% median map accuracy. The likely structural mismatch is that the retained calibration procedure selects frames using post-round-trip **payload** margins only; it does not require the independently embedded local pilot to be strong or unambiguous in that same frame.
- This is a bounded inference from the experiment design, not proof that all local-pilot methods fail. The controls are too small to establish a false-positive rate.

## Decision

Do not extend these pair allocations to attacks. The next clean study should use joint calibration: probe both pilot and payload groups after the full round trip, then choose each candidate by a conservative joint objective such as maximizing the weaker signed margin while rejecting candidates below a pilot threshold. Compare that design against the current iteration 002 profiles before changing parity, duration, or attack conditions.

## Reproduce

The complete machine-readable result for both profiles, all twenty watermarked trials, and their controls is archived in `RESULTS.json` beside this summary.

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_002_local_selection_pilot.run
```

# Attribution V1 Decision Record

## Purpose

V1 completes the application attribution surface as a **claimed-handle
verifier**, not a blind watermark-discovery system. A registry issues a four-byte
opaque handle; the encoder embeds it and retains a private carrier-frame map;
a verifier checks the claimed handle against received PCM with that retained map.

## Experimental Basis

- `iteration_004_four_frame_soft_combine` establishes the four-replica
  score-combining carrier pattern used by `attribution_repetition.py`.
- `iteration_020_sixteen_parity_registry_handle` selects the fixed 4-byte handle
  plus 16-parity allocation inside a 20-byte protected codeword. On its named
  synthetic bounded-crop fixture, it recovers 6/10 trailing and 7/10 leading
  claims; the result is not sufficient to claim blind crop robustness.
- The same iteration requires a collision-checked authenticated registry because
  a 32-bit handle is not collision-resistant by itself.
- `iteration_032_edge_mode_coarse_bank` later measures a separate non-oracle
  leading/trailing edge-crop decoder. Its named synthetic crop result does not
  alter this v1 retained-map contract or establish general blind discovery.

## V1 Contract

```text
provenance -> registry issues random 4-byte candidate handle
          -> encoder embeds four replicas
          -> encoder self-verifies the clean result against the claimed codeword
          -> retry a handle candidate if its clean claim exceeds RS budget
          -> registry retains handle, authentication tag, provenance, and frame map

claimant supplies handle -> registry resolves authenticated entry and frame map
                         -> decoder combines four retained-map score streams
                         -> claim-aware RS cost <= 16 accepts the claim
```

The claim-aware cost is `2 * differing byte symbols + declared byte erasures`.
Because the claimant supplies the handle, the verifier can compare the received
carrier codeword with that claim. This is a verification protocol, not recovery
of an unknown handle.

## Key And Metadata Boundaries

V1 keeps watermark derivation separate from registry authentication:

```text
watermark master secret
  -> domain-separated attribution/interleaver key
  -> keyed spectral pairs, pilots, transport permutation

registry authentication secret
  -> handle/provenance authentication tag
  -> authenticated local record lookup
```

The registry must not expose the watermark master secret. The current
interleaver key is `HMAC-SHA256(master_secret,
"stegosaurus-audio-v1|attribution")`; the transport then derives a deterministic
HMAC-driven Fisher--Yates bit permutation for the protected codeword length.
A deployment should provide watermark-key access through an encoder/decoder
service or KMS/HSM boundary, while registry lookup supplies only authenticated
claim data. The expected sample rate and original sample count are claim/profile
geometry for the experimental edge-mode decoder, not a substitute for v1's
retained carrier-frame map.

## Explicit Limits

- The in-memory registry is a local prototype. A deployment needs persistent,
  access-controlled storage, authenticated lookup, rate limiting, collision
  metrics, reissue handling, and private retention of `AttributionRecord`.
- V1 has a clean synthetic 30-second application test and wrong-secret control.
  It makes no claim for codecs, DSP, crops, recorded audio, speech, arbitrary
  resynthesis, or unknown-handle discovery.
- Blind local-pilot reconstruction remains research. Iteration 032 reaches
  10/10 on each named `250 ms` crop direction in its fresh synthetic fixture,
  with selected post-hoc RS cost at most 16 and no selected negative controls.
  It is not promoted into v1 and makes no claim for other crop durations,
  multi-edit timelines, codecs, DSP, recorded audio, or open-world false rates.

## Application Files

| Responsibility | Code |
| --- | --- |
| Public attribution API | `src/stegosaurus/audio/attribution.py` |
| Fixed v1 profile and verification records | `src/stegosaurus/audio/attribution_models.py` |
| Four-replica carrier embed and claim verification | `src/stegosaurus/audio/attribution_repetition.py` |
| Directional encoder and decoder | `src/stegosaurus/audio/attribution_encoder.py`, `src/stegosaurus/audio/attribution_decoder.py` |
| Local authenticated handle registry | `src/stegosaurus/audio/attribution_registry.py` |

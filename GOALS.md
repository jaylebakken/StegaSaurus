# Stegosaurus Goals

## Project Goal

Build an audio watermarking system that can eventually outperform relevant
industry baselines on two separate dimensions:

1. **Attribution:** reliably bind an authorized copy to an opaque external
   registry claim, recover or verify that claim under declared conditions, and
   reject unauthorized claims.
2. **Robustness:** preserve detection and attribution evidence under a broader,
   pre-registered set of realistic and adversarial waveform transformations
   while maintaining acceptable audio quality.

“Beat the industry standard” is a future benchmark outcome, not a current
claim. The comparison target must be named for each use case: a commercial
forensic watermark, a learned payload watermark, a classical watermark, an
audio fingerprint, or a hybrid system may optimize different goals.

## Current Assessment

| Goal | Current position | Assessment |
| --- | --- | --- |
| Claimed attribution | V1 embeds a 4-byte handle with 16 RS parity symbols and verifies a supplied claim using a private retained carrier map. | Useful local prototype; not a durable registry or blind attribution product. |
| Non-oracle reconstruction | Iteration 032 recovers all 20 named fresh synthetic `250 ms` single-edge crop trials within the RS budget. | Promising synchronization result, but narrow synthetic smoke evidence. |
| Robustness | Detector and transport experiments cover named synthetic transformations. | Insufficient for an industry comparison: no varied licensed corpus, open-world false-rate study, or perceptual evaluation. |
| Security | Master-secret derivation, registry authentication, key separation, and negative controls are documented. | Needs production key management, registry access control, threat modeling, and external review. |
| Competitive evidence | No head-to-head baseline study exists. | Cannot claim leadership or parity with industry systems yet. |

## Near-Term Plan

1. **Freeze the current experimental contract.** Keep the iteration 032
   edge-mode bank separate from the v1 application API until broader validation
   succeeds.
2. **Build a benchmark corpus and scorecard.** Use licensed/generated speech
   and music, declared quality metrics, exact-claim recovery, detection rate,
   false accepts, RS damage, runtime, and audio quality.
3. **Run baseline comparisons.** Compare the same corpus and attack matrix
   against at least one classical watermark, one learned payload watermark or
   comparable implementation, and a fingerprint baseline where appropriate.
4. **Harden attribution infrastructure.** Replace the local registry with
   authenticated durable storage, explicit waveform geometry metadata,
   rate-limited claim lookup, key-management boundaries, and audit logs.
5. **Validate broader synchronization.** Test clean PCM, varied crop lengths,
   leading/trailing/multi-edit cases, resampling, codecs, filtering, noise, and
   time-scale changes under pre-registered success criteria.

## Adversarial Evaluation Workflow

At a later stage, an adversarial agent may propose waveform attacks against the
embedded audio. Stegosaurus work should then follow this loop:

```text
attack proposal
  -> classify the threat and identify its assumptions
  -> reproduce it with a fixed recipe and negative controls
  -> measure detection, exact attribution, RS errors/erasures, and quality
  -> diagnose the failure mechanism
  -> research and implement bounded countermeasure candidates
  -> validate on disjoint inputs and preserve the attack as a regression
```

The defensive objective is not to hide failures. Each credible attack should
become a replayable experiment with an explicit result, scope boundary, and
regression contract. Countermeasures must be evaluated against both the new
attack and the prior named transformation suite to avoid trading one failure
for another.

## Decision Rules

- Do not call a result industry-leading without a named, reproducible baseline
  comparison on the same corpus and attack matrix.
- Do not promote experimental non-oracle logic into the application API based
  on a single fixture family.
- Prefer explicit abstention to a confident but unsupported attribution.
- Treat Reed--Solomon recovery, registry authentication, watermark secrecy,
  and provenance policy as distinct controls; none replaces the others.

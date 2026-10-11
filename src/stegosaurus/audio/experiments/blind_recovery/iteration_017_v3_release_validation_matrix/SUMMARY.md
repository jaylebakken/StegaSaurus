# Iteration 017 - V3 Release Validation Matrix

## Goal

Convert the optimized V3 waterfall from iteration 016 into a release validation
matrix. This identifies what can be core V3, what remains experimental, and
what evidence is still missing before stronger blind-recovery claims.

## Method

This is a planning artifact over current measured experiments. It does not run
new DSP and does not expand the claim surface.

## Current Result

Recommended V3 buckets:

| Capability | Bucket | Current evidence | Missing validation |
| --- | --- | --- | --- |
| `repeated_30s_block_schema` | V3 core | iteration 011 exact-window block recovery; v2 retained-record codec | held-out clean fixture and runtime budget |
| `pilot_window_prefilter` | V3 core | iterations 012 and 014 ranked exact starts into top windows | held-out 2.5 min / 5 min songs and bounded crops |
| `fast_block_vote` | V3 core | iteration 014 top-three two-vote recovery | wrong-secret and unwatermarked repeated-block controls |
| `cross_block_carrier_pooling` | V3 core after controls | iteration 015 top-five pooled RS cost 0; iteration 016 zero-vote pooling route | negative controls, non-block-window ablation, bounded-crop pooling |
| `geometry_fallback` | experimental V3 fallback | non-oracle iteration 032 and blind crop-search iterations | block-localization integration, more crop lengths, runtime cap |
| `unknown_arbitrary_crop_length` | V3-later | bounded crop explorations only | broad crop sweep, stopping policy, false-positive analysis |
| `codec_recorded_audio_claims` | out of scope for V3 | synthetic PCM experiments only | codec, playback/capture, perceptual, and content-diversity studies |

## Interpretation

V3 should not claim fully general blind recovery yet. The releaseable core is a
bounded blind-attribution controller for repeated 30-second blocks:

1. rank windows with the pilot prefilter,
2. accept with a two-vote fast block policy when available,
3. pool carrier evidence across localized repeated blocks when block votes are
   weak or higher assurance is requested,
4. keep geometry fallback as an experimental offline path for localization or
   timing distress.

The go/no-go rule for promoting pooling is especially important: pooled recovery
must reject wrong-secret and unwatermarked controls and remain stable when top-K
contains overlapping non-block windows. Until that validation lands, pooling is
the V3 core direction, but its stronger claim should be gated.

Codec, recorded-audio, arbitrary-crop, and perceptual claims remain explicitly
outside V3.


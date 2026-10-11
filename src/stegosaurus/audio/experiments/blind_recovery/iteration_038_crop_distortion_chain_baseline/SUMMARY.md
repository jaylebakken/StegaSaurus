# Iteration 038: Crop-Distortion Chain Baseline

This suite measures the current V4 workflow across parent/child registry-only
exports, arbitrary crop offsets, and named synthetic distress profiles.

## Method

The suite uses a deterministic 150-second music-like sample so hardening changes
can be measured quickly during development. The registry contains a parent
export, two child exports generated from the clean master, and one unrelated
control export.

The verification path uses `verify_excerpt_with_fallbacks`:

1. Run the clean default recovery profile.
2. If nothing is accepted, reuse the same localization candidates with a
   stricter deep phase search.

An experimental relaxed RS budget was tested and rejected for product use: it
accepted parent, sibling, and unrelated records in the light recorded-proxy
case, so it increased misattribution risk instead of adding reliable recovery.

## Results

| Scenario | Correct rank | Correct RS cost | Accepted | Status |
| --- | ---: | ---: | --- | --- |
| Parent clean 37.25s crop | 1 | 6 | yes | `pass` |
| Child A clean 37.25s crop | 1 | 10 | yes | `pass` |
| Child A peak-normalized 37.25s crop | 1 | 11 | yes | `pass` |
| Child A light recorded proxy 37.25s crop | 1 | 20 | no | `decode_failure_after_localization` |

## Interpretation

The parent/child registry-only model remains clean under cropped, undistorted
audio: only the visible export is accepted.

The baseline now passes the clean parent crop, clean child crop, and
peak-normalized child crop. The deep phase fallback fixes the peak-normalized
case without relaxing the RS acceptance budget or accepting parent/sibling
records.

The light recorded proxy remains unsolved:

- It localizes enough to rank the correct child first.
- The best child evidence lands at RS cost 20, above the strict 16-symbol
  budget.
- Relaxing to RS 24 accepted multiple retained records, so that path is not safe
  enough to promote.

## Product Changes From This Iteration

- Added `RecoveryProfile` so verification cost and acceptance knobs can be
  explicit instead of ambient.
- Added `verify_excerpt_with_fallbacks` with clean first-pass and strict deep
  phase fallback.
- Updated fanout to compare pooled evidence with the best single localized
  window, preventing a weak extra candidate from drowning out a good block.
- Expanded localized anchors into consecutive crop-local block candidates so an
  arbitrary crop can contribute later full blocks.

## Next Hardening Target

The next iteration should attack the two remaining failure modes separately:

1. Build a stronger evidence discriminator for low-pass/resample/noise/reverb
   proxy cases.
2. Keep relaxed RS acceptance out of product flow unless it can prove a unique
   winner across parent, child, sibling, and unrelated controls.


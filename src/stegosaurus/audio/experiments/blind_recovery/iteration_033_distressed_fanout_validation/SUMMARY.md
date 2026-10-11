# Iteration 033 - Distressed Fanout Validation

## Goal

Apply realistic suspicious-excerpt distress to the known-song fanout workflow
from iteration 032. This was the final check before deciding whether V4 should
claim clean-file attribution only or include light real-world distress.

## Method

The suite reused the same workflow as iteration 032:

```text
known song
  -> 12 simulated export records
  -> crop export_07 as the suspicious excerpt
  -> shared source-audio prefilter
  -> fine phase search
  -> fanout verification across all exports
```

It then applied named distress profiles to the suspicious 90-second excerpt
before localization and attribution:

1. `clean`
2. `peak_normalized`
3. `light_recorded_proxy`
4. `moderate_recorded_proxy`

The recorded-proxy profiles use deterministic resampling, low-pass filtering,
synthetic reverb, white noise, and peak normalization. These are named synthetic
distress tests only, not claims about microphone, room, platform, or device
robustness.

## Results

| Distress | Correct rank | Correct recovered | Correct RS cost | False accepts | Workflow |
| --- | ---: | --- | ---: | ---: | --- |
| `clean` | 1 | yes | 15 | 0 | pass |
| `peak_normalized` | 1 | no | 33 | 0 | fail |
| `light_recorded_proxy` | 8 | no | 32 | 0 | fail |
| `moderate_recorded_proxy` | 8 | no | 29 | 0 | fail |

The clean workflow repeated the iteration 032 success: the correct export ranked
first and recovered with no false acceptances.

The distressed cases rejected safely, but they did not recover the correct
export. Peak normalization still ranked the correct export first, but the pooled
RS cost rose above the acceptance budget. The recorded-proxy cases also broke
the source-audio prefilter, which selected the wrong region before attribution
fanout.

## Interpretation

This creates a clean V4 release boundary:

```text
V4 should target known-song clean-file leak attribution first.
```

The known-song registry workflow is viable for clean suspicious excerpts:

```text
selected song -> shared source localization -> phase-refined fanout
    -> matching export record
```

But distress robustness is not ready for a production claim. Even simple
post-crop peak normalization can move pooled evidence outside the current RS
budget, and recorded-proxy transforms can confuse the source-audio prefilter.

## V4 Implication

The V4 product workflow should be scoped as:

```text
Register song
Create recipient/export watermarked copies
Upload suspicious WAV excerpt
Select known song
Identify the matching export record for clean or lightly edited file leaks
```

The UI can include distress testing as an experimental lab panel, but the main
verification result should not claim recorded-audio or normalized-upload
robustness yet.

## Follow-Up Research

Distress robustness should become its own focused V4.x line:

1. Make carrier extraction gain-invariant or normalize expected evidence before
   scoring.
2. Add source-prefilter features that survive low-pass/resample/reverb better
   than long-window log-band fingerprints.
3. Calibrate RS acceptance against transformed clean controls.
4. Re-test with additional modern pop/rap samples.
5. Explore shorter block profiles so a distressed crop has more independent
   evidence opportunities.

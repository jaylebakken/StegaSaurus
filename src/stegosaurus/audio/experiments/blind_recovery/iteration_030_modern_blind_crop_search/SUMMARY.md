# Iteration 030 - Modern Blind Crop Search

## Goal

Replace the oracle surviving-block geometry from iteration 029 with a
registry-backed search over an unknown crop. This suite assumes the user or
application has selected the correct song registry candidate, but the uploaded
excerpt may start at an unknown offset inside the song.

## Registry Bookmark

The intended product flow remains:

```text
Upload suspicious excerpt
  -> select known registered song, or search the user's catalog
  -> load all embedding records for that song
  -> search each record for matching watermark evidence
  -> report the matching recipient/export record
```

One song may have many embedding records. The user should normally select the
song, not the exact embedding. StegaSaurus should then run all active embedding
records for that song and identify which recipient/export record, if any,
matches the excerpt.

## Method

This iteration tests a maximum-cost fallback rather than a cheap prefilter:

1. Watermark `10. Lovers Rock.wav` with the current 30-second repeated-block
   attribution profile.
2. Crop off-grid excerpts at 60 and 90 seconds.
3. Slide 30-second candidate windows across each crop with a 10-second stride.
4. For each candidate window, try every retained block record for that song.
5. Rank candidate windows by lowest claim RS cost.
6. Pool the top three windows.
7. Compare against unwatermarked source and wrong-record controls.

## Result

| Crop | Watermarked recovered | Source control | Wrong-record control | Runtime per control |
| ---: | --- | --- | --- | ---: |
| 60 s | no, RS cost 37 | rejected | rejected | about 3.5 s |
| 90 s | no, RS cost 38 | rejected | rejected | about 6.3 s |

Controls behaved correctly, but the watermarked crops did not recover. The top
ranked windows were not accurate enough for pooled recovery, even on a track
that recovered in the iteration 029 oracle upper-bound test.

## Interpretation

The naive expensive fallback is not sufficient by itself. Trying every retained
block record against coarse sliding windows creates a large runtime cost and
does not reliably select the windows that preserve the original block geometry.

This result narrows the next design:

```text
cheap pilot/localization prefilter -> fine phase refinement -> pooled evidence
```

The fallback should not begin with full retained-record verification every 10
seconds. It needs a cheaper localization layer that can search around likely
pilot-aligned starts at sub-stride resolution before spending the expensive
Reed-Solomon reconstruction budget.

## Next Iteration

The next experiment should focus on phase refinement rather than a wider brute
force grid:

1. Use a cheap pilot-only score to rank coarse windows.
2. Around each coarse winner, search fine offsets such as `-2.5s` to `+2.5s`.
3. Pool the best non-overlapping windows.
4. Keep the same source and wrong-record controls.
5. Measure whether a 60-90 second modern excerpt can recover without oracle
   geometry.

If that still fails, the current 30-second block profile is likely too brittle
for arbitrary crops without shorter independently recoverable blocks.

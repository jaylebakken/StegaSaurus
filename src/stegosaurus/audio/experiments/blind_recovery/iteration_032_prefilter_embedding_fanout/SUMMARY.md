# Iteration 032 - Prefilter To Embedding Fanout

## Goal

Test the core leak-attribution workflow:

```text
User selects the known leaked song
  -> StegaSaurus localizes the suspicious excerpt once
  -> the app checks many recipient/export embedding records
  -> the matching leaked export is identified
```

This connects the shared registry-audio prefilter from iteration 031 to
recipient/export-specific attribution records.

## Method

The experiment used `10. Lovers Rock.wav` as the registered song.

1. Simulate 12 embedding records for one song, each with a different handle.
2. Treat `export_07` as the leaked copy.
3. Crop a 90-second off-grid excerpt from `export_07`.
4. Run the shared source-audio prefilter once for the selected song.
5. Keep one top candidate per localized registry block.
6. Around each candidate, run a fine attribution phase search of +/- 0.30
   seconds at 0.025 second stride.
7. Pool candidate evidence for each export record and rank the records.

## Result

| Metric | Value |
| --- | ---: |
| Embedding records checked | 12 |
| Leaked export | `export_07` |
| Correct export rank | 1 |
| Correct export recovered | yes |
| Correct export pooled RS cost | 15 |
| False acceptances | 0 |
| Prefilter time | 5.71 s |
| Verification fanout time | 67.94 s |

The prefilter localized two useful block candidates:

| Candidate | Crop-local start | Registry block | Boundary error |
| ---: | ---: | ---: | ---: |
| 1 | 29.0 s | block 3 | 0.123 s |
| 2 | 59.0 s | block 4 | 0.123 s |

The first run without fine phase refinement failed because a 0.123 second
boundary error was enough to break retained-frame attribution recovery. After
adding the local phase search, the correct export recovered and every wrong
export rejected.

`recovered_windows` stayed at zero because no single candidate window recovered
as a full independent block vote. The accepted result came from pooled carrier
evidence across localized candidates.

## Interpretation

This is the first complete positive result for the intended known-song registry
workflow. It supports the pipeline shape:

```text
known song registry candidate
  -> shared source-audio crop localization
  -> fine attribution phase search
  -> fanout across embedding records
  -> pooled evidence ranking
```

The cost is too high for a polished UI if run serially across many exports, but
the structure is now right. The expensive dimension is limited to:

```text
embedding records x localized candidates x local phase offsets
```

instead of:

```text
embedding records x all crop windows x all phase offsets
```

## Next Steps

The next optimization work should focus on reducing fanout cost:

1. Cache source-song fingerprints at embed/import time.
2. Parallelize export-record verification.
3. Stop early when one record recovers and the next-best records are far above
   the RS threshold.
4. Share STFT work across phase offsets where possible.
5. Test fanout sizes such as 25, 50, and 100 exports.

The next robustness work should repeat this workflow under light recorded-proxy
distortion and with additional modern pop/rap samples.

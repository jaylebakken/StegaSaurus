# Iteration 031 - Registry Audio Prefilter

## Goal

Analyze the prefilter as a shared registry step, assuming the application may
need to check many embedding records for one known song. The central question
was:

```text
Can we localize useful crop windows once per song, before running expensive
watermark verification across many recipient/export records?
```

## Method

This iteration uses the original source audio from the selected song registry
candidate as a cheap localization reference.

For each tested modern-production sample:

1. Embed the current 30-second repeated-block watermark.
2. Crop 60, 90, and 120 second excerpts at off-grid starts.
3. Build log-band energy fingerprints for complete 30-second source blocks.
4. Slide coarse 30-second windows across the crop at a 5-second stride.
5. Refine the top coarse windows within a +/- 3 second neighborhood at 0.5
   second stride.
6. Measure whether the top candidates land within 1 second of complete original
   block boundaries that survived inside the crop.

This is not watermark verification. It is song-level crop localization that can
be reused before checking many embedding records under the same song.

## Results

| Source | Trials | Top-1 hits | Top-5 hits | Median runtime |
| --- | ---: | ---: | ---: | ---: |
| `08. Gutta Bitch.wav` | 9 | 9 | 9 | 4.08 s |
| `10. Lovers Rock.wav` | 9 | 9 | 9 | 3.76 s |
| `19. Get Low.wav` | 9 | 9 | 9 | 4.45 s |

All tested 60, 90, and 120 second modern-production crops localized at least
one useful surviving block boundary in the top candidate. Most best errors were
well under 0.3 seconds after fine refinement.

## Interpretation

This is the clearest route toward a usable workflow so far. The search should
not start by checking every embedding record. It should first use the selected
song's registry audio to find likely crop positions, then fan those few
candidates out across recipient/export-specific watermark records.

The product pipeline can therefore become:

```text
known song or top-K song candidates
  -> shared audio-localization prefilter per song
  -> top localized windows
  -> expensive attribution verification across that song's embedding records
  -> pooled evidence decision
```

This converts the expensive dimension from:

```text
embeddings x all windows
```

to:

```text
one song prefilter + embeddings x top windows
```

That matters if a song has tens or hundreds of embedded exports.

## Caveats

The current prefilter compares against source audio, so the registry needs
access to either the source file, a local fingerprint index, or a cached
fingerprint representation. The measured implementation computes long FFT
fingerprints directly and took about 3.8-4.5 seconds per crop trial. That is
acceptable for an experiment, but production should cache source fingerprints
and use shorter rolling features.

The test used modern dense samples and synthetic crops of the watermarked file.
It does not yet measure lossy codecs, recorded proxies, speed changes, or
source-audio edits.

## Next Step

Iteration 032 should connect this prefilter to attribution:

1. Use the registry-audio prefilter to produce top localized windows.
2. Run expensive watermark verification only on those windows.
3. Check all embedding records for a song-like fanout simulation.
4. Include source and wrong-record controls.
5. Measure total runtime as:

```text
prefilter time + embedding_count * top_window_verification_time
```

If this works, the early product workflow becomes much more realistic:

```text
User selects leaked song -> app localizes excerpt -> app identifies matching
recipient/export record.
```

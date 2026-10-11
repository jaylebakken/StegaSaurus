# Iteration 026 - Cry Me a River Capacity Audit

## Goal

Run the same real-track recorded-proxy test path on:

```text
C:\Users\jay\Downloads\10. Cry Me a River.wav
```

## Result

The recorded-proxy distortion sweep could not run because the current V2
attribution carrier could not embed into any scanned 30-second excerpt.

The file was read successfully:

- duration: 302.60 seconds,
- scanned starts: 0 through 270 seconds in 5 second steps,
- candidate excerpts were peak-normalized to 0.90 before the capacity check.

The detector pilot was able to embed in every scanned excerpt, with thousands
of embedded frames per 30-second window. The V2 attribution carrier failed
every excerpt with `FourFrameCapacityError`.

## Capacity Range

- detector-pilot embedded frames ranged from 3009 to 5116 per excerpt,
- detector-pilot SNR ranged from 35.11 dB to 47.13 dB,
- V2 attribution capacity result was `FourFrameCapacityError` for every
  scanned excerpt.

## Interpretation

This track is not currently usable for the repeated-block V2 attribution
robustness sweep. As with the OnClassical file, the blocker is not the basic
detector pilot; it is the current V2 attribution frame-map capacity rule.

No clean or distorted attribution artifacts were written because there was no
successful clean V2 attribution embedding to attack and recover.

The next useful experiment is a lower-capacity or adaptive attribution profile
for real music tracks, then rerunning the recorded-proxy severity ladder.

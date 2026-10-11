# Iteration 025 - Real Track Recorded Proxy Sweep

## Goal

Run the same recorded-audio proxy severity sweep on the user-supplied WAV:

```text
C:\Users\jay\Downloads\onclassical_demo_luisi_bach_partita_a-minor_bwv-827_1_small-version.wav
```

The file is 98.1 seconds long, so the experiment uses the first 90 seconds as
three complete 30-second watermark blocks.

## Method

- Read and downmix the PCM16 WAV.
- Scan for capacity-valid 30-second excerpts, normalizing candidate excerpts to
  0.90 peak before embedding.
- Embed the same attribution handle into each block.
- Run the recorded-proxy severity ladder from iteration 024.
- Require watermarked recovery and unwatermarked plus wrong-secret rejection.
- Save a clean watermarked reference and the highest recovered distorted WAV.

## Current Result

The recorded-proxy sweep could not run because the current V2 attribution
carrier could not embed into any scanned 30-second excerpt from this file.

The source was successfully read:

- sample rate: 44.1 kHz,
- duration: 98.10 seconds,
- scanned starts: 0 through 65 seconds in 5 second steps.

Each candidate excerpt was peak-normalized to 0.90 before the capacity check.
The simpler detector pilot could embed thousands of frames in every excerpt,
but the V2 attribution carrier failed every excerpt with
`FourFrameCapacityError`.

| Start (s) | Detector pilot embedded frames | Detector pilot SNR (dB) | V2 attribution capacity |
| ---: | ---: | ---: | --- |
| 0 | 4971 | 43.72 | `FourFrameCapacityError` |
| 5 | 5058 | 43.29 | `FourFrameCapacityError` |
| 10 | 5083 | 44.07 | `FourFrameCapacityError` |
| 15 | 5090 | 43.64 | `FourFrameCapacityError` |
| 20 | 4939 | 42.90 | `FourFrameCapacityError` |
| 25 | 4956 | 42.76 | `FourFrameCapacityError` |
| 30 | 4903 | 41.97 | `FourFrameCapacityError` |
| 35 | 4927 | 43.23 | `FourFrameCapacityError` |
| 40 | 4945 | 42.18 | `FourFrameCapacityError` |
| 45 | 4915 | 42.75 | `FourFrameCapacityError` |
| 50 | 4961 | 42.67 | `FourFrameCapacityError` |
| 55 | 4783 | 42.74 | `FourFrameCapacityError` |
| 60 | 4727 | 43.49 | `FourFrameCapacityError` |
| 65 | 4638 | 44.00 | `FourFrameCapacityError` |

No clean or distorted V2 attribution artifacts were written, because there was
no capacity-valid V2 attribution embedding to attack and recover.

## Interpretation

This file is not currently usable for the repeated-block V2 attribution
robustness sweep. The distinction matters:

- detector-pilot watermarking appears feasible on this source,
- current V2 attribution embedding is blocked by carrier-frame map capacity,
- distortion upper-bound testing requires a successful clean attribution
  embedding first.

The next implementation/research step is a lower-capacity or adaptive
attribution profile for sparse classical piano material, not a recorded-proxy
attack sweep.

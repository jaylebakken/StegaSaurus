# Iteration 041: Robust Profile Baseline

This suite validates the 15-second robust profile against the compact
parent/child crop-distortion baseline.

## Method

The robust profile uses 15-second repeated attribution blocks with registry-only
parent/child exports. The registry contains:

- parent export,
- visible child export,
- sibling child export,
- unrelated control export.

The suite verifies parent and child off-grid 90-second crop cases:

1. clean crop,
2. peak-normalized crop,
3. light recorded-proxy crop.

The light recorded-proxy profile is a deterministic synthetic transform using
resampling, low-pass filtering, synthetic reverb, white noise, and peak
normalization. It is not a broad microphone, room, codec, or platform claim.

## Results

| Scenario | Accepted | Best RS | False Accepts | Status |
| --- | --- | ---: | ---: | --- |
| Parent clean crop | parent | 5 | 0 | `pass` |
| Parent peak-normalized crop | parent | 6 | 0 | `pass` |
| Parent light recorded-proxy crop | parent | 11 | 0 | `pass` |
| Child clean crop | child | 5 | 0 | `pass` |
| Child peak-normalized crop | child | 9 | 0 | `pass` |
| Child light recorded-proxy crop | child | 7 | 0 | `pass` |

## Interpretation

The 15-second robust profile passes the compact parent/child crop-distortion
baseline that the 30-second profile could not pass. Parent and child exports
remain the only accepted claims under both peak normalization and the named
light recorded-proxy transform.

The cost is runtime and a likely capacity/perceptual tradeoff. This profile
should be exposed as an explicit robust/distressed workflow rather than silently
replacing the clean 30-second default.

## Recommendation

Promote the 15-second robust profile into the application workflow as an
opt-in robust export/recovery mode, then add UI plumbing and runtime messaging.


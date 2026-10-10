# Iteration 014 - Block Fallback Optimization

## Goal

Compare top-K block voting, vote thresholds, and fallback budgets on one shared ranked-window fixture. The question is where the controller should stop, where it should spend geometry fallback, and where it should hand off to a future cross-block evidence combiner.

## Method

- Fixture: the same 2.5-minute synthetic song with five independently embedded 30-second blocks.
- Rank the strongest seven candidate windows with the pilot prefilter.
- Run cheap received-duration recovery once over those seven windows.
- Evaluate policy choices over the shared recovery records.
- Spend real fallback only for strict policies that are below threshold.

## Current Result

The top-seven prefilter ranking contained the five exact block starts first,
then two overlapping non-block windows. Cheap recovery found three valid block
votes among the exact starts.

Shared timing:

- pilot prefilter over the song: 1.78 s,
- cheap recovery over seven windows: 12.45 s,
- one fallback attempt: 8.92 s,
- two fallback attempts: 17.83 s.

| Policy | Top windows | Threshold | Cheap votes | Fallback attempts | Final votes | Accepted | Next tool |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `fast_any_top3` | 3 | 1 | 2 | 0 | 2 | yes | stop |
| `fast_two_vote_top3` | 3 | 2 | 2 | 0 | 2 | yes | stop |
| `strict_three_top3_with_fallback` | 3 | 3 | 2 | 1 | 2 | no | symbol pooling |
| `balanced_three_top5` | 5 | 3 | 3 | 0 | 3 | yes | stop |
| `strict_four_top5_with_fallback` | 5 | 4 | 3 | 2 | 3 | no | symbol pooling |
| `wide_three_top7` | 7 | 3 | 3 | 0 | 3 | yes | stop |

## Interpretation

For this repeated-block fixture, the best controller shape is:

1. score windows cheaply,
2. try top three first,
3. accept a two-vote threshold for fast/high-confidence attribution,
4. expand to top five when a three-vote threshold is desired,
5. route high-pilot block failures to cross-block symbol pooling before geometry fallback.

The expensive 125-500 ms geometry fallback did not recover either high-pilot
exact block failure. That makes those failures look like block evidence distress
rather than alignment distress. Spending broad crop search on those blocks
added roughly 9 seconds per attempted window without improving the vote.

The next optimization target should be a pooled block decoder: keep partial
carrier, erasure, and RS-burden evidence from the failed exact windows and
combine it with the recovered windows before the final attribution decision.


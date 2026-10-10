# Iteration 010: Distress Fallback Voting Model

## Goal

Model a maximum-cost recovery waterfall for repeated song blocks. The controller
tries cheap received-duration recovery first, then spends the `500 ms`
single-edge fallback only when block voting still needs more recovered blocks.

## Method

- Analytical planning model using local timings from iteration 008:
  - received-only block recovery: about `2.2 s`,
  - single-edge `500 ms` grid: about `9.0 s`.
- Scenarios cover `2.5 min` and `5 min` songs with any-block and two-block
  voting thresholds.
- This is a maximum-cost model: if cheap recovery does not meet the voting
  threshold, it spends fallback search across the remaining blocks.

## Scope Boundary

This does not run audio recovery. It estimates controller cost and acceptance
behavior for block-voting designs so the next audio experiment can target the
most promising schema.

## Result

| Scenario | Accepted | Recovered blocks | Received-only attempts | Fallback attempts | Estimated time |
| --- | --- | ---: | ---: | ---: | ---: |
| `2_5min_many_clean_any_block` | yes | 3 | 5 | 0 | `11.0 s` |
| `2_5min_distressed_two_vote` | yes | 3 | 5 | 4 | `38.2 s` |
| `5min_sparse_clean_any_block` | yes | 1 | 10 | 0 | `22.0 s` |
| `5min_distressed_two_vote` | yes | 4 | 10 | 9 | `83.2 s` |

The cost shape is acceptable for offline or asynchronous verification, but too
slow for a naive interactive path if every block reaches fallback. The useful
controller policy is therefore:

1. Run received-only recovery across candidate blocks first.
2. Accept immediately for any-block workflows once one clean block recovers.
3. Spend the `500 ms` single-edge fallback only when voting still needs more
   blocks.
4. Cap fallback attempts or move the remainder to an offline maximum-cost mode.

## Recommendation

For early production, default to any-block acceptance for user-facing
verification and reserve two-block voting for high-assurance or offline jobs.
For `2.5 min` and `5 min` songs, repeated `30 s` blocks give enough recovery
opportunities that the pipeline can usually avoid the expensive path.

## Reproduce

```powershell
python -m stegosaurus.audio.experiments.blind_recovery.iteration_010_distress_fallback_voting_model.run
```

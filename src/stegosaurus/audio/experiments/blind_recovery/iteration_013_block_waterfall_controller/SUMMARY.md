# Iteration 013 - Block Waterfall Controller

## Goal

Prototype the maximum-cost controller shape for early blind attribution:

1. rank likely 30-second block windows with cheap pilot-only evidence,
2. run received-duration recovery on only the top windows,
3. accept once enough independent block votes recover,
4. spend expensive single-edge crop fallback only when the requested vote threshold is still unmet.

This is still a claimed-plan synthetic repeated-block experiment. It measures controller scheduling behavior, not arbitrary unknown-handle attribution.

## Method

- Source fixture: one 2.5-minute synthetic song made from five independently embedded 30-second blocks.
- Candidate windows: 30-second windows every 15 seconds.
- Prefilter: median local-pilot margin score from iteration 012.
- Cheap recovery: received-duration staged controller.
- Fallback recovery: single-edge declared crop hypotheses at 125, 250, 375, and 500 ms.

Policies:

| Policy | Vote threshold | Fallback window budget |
| --- | ---: | ---: |
| `online_any_block` | 1 | 0 |
| `high_assurance_two_block` | 2 | 0 |
| `max_cost_four_block` | 4 | 2 |

## Current Result

The top-five pilot prefilter found all five exact 30-second block starts.

| Policy | Cheap recoveries | Fallback attempts | Fallback recoveries | Accepted | Total runtime |
| --- | ---: | ---: | ---: | --- | ---: |
| `online_any_block` | 3 | 0 | 0 | yes | 10.82 s |
| `high_assurance_two_block` | 3 | 0 | 0 | yes | 10.82 s |
| `max_cost_four_block` | 3 | 2 | 0 | no | 28.78 s |

Shared timing:

- pilot prefilter: 1.81 s,
- cheap recovery over the top five windows: 9.01 s,
- bounded fallback for two distressed windows: 17.96 s.

## Interpretation

The intended production shape is a waterfall, not a fixed maximum-cost search. The controller should stop as soon as the evidence standard is met and reserve broad crop search for distressed or high-assurance cases.

On this clean repeated-block fixture, the fallback did not rescue the two block windows that failed received-duration recovery. That is useful: it says the single-edge crop fallback is primarily a geometry-distress tool, not a general cure for weak block votes. For early production, a two-block threshold looks feasible in this fixture, while four-block acceptance is too strict unless the embedder or decoder increases per-block recovery reliability.


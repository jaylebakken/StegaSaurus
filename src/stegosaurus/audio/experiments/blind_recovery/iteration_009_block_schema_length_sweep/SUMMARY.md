# Iteration 009: Block Schema Length Sweep

## Goal

Compare repeated independently recoverable watermark blocks against a single
full-song codeword across `30 s`, `2.5 min`, and `5 min` covers.

## Method

- Analytical planning model, not a new audio robustness experiment.
- Assumes the current `30 s` block profile from blind-recovery experiments.
- Evaluates:
  - one full-song codeword,
  - non-overlapping `30 s` blocks,
  - overlapping `30 s` blocks every `15 s`,
  - any-block and two-block voting.
- Uses a configurable independent per-block recovery probability; default is
  `0.8` so the sweep is conservative relative to the known-good fixtures.

## Scope Boundary

This does not account for perceptual accumulation from multiple embeddings,
codec behavior, corpus variation, or correlated block failures. It is a schema
planning iteration for deciding what to test with audio next.

## Result

Using a conservative independent per-block recovery assumption of `0.8`:

| Song length | Schema | Blocks | Any-block estimate | Two-block estimate |
| --- | --- | ---: | ---: | ---: |
| `30 s` | one 30-second block | 1 | `0.800000` | n/a |
| `2.5 min` | `30 s` stride | 5 | `0.999680` | `0.993280` |
| `2.5 min` | `30 s` block every `15 s` | 9 | `0.999999` | `0.999981` |
| `5 min` | `30 s` stride | 10 | `0.9999999` | `0.9999958` |
| `5 min` | `30 s` block every `15 s` | 19 | `~1.0` | `~1.0` |

The planning result strongly favors repeated independently recoverable blocks
over one full-song codeword. Longer audio should buy more recovery
opportunities, not just one larger fragile transport.

## Recommendation

For the next audio-bearing prototype, use `30 s` block-local watermarks. A
`30 s` stride gives five opportunities in a `2.5 min` song and ten in a
`5 min` song. A `15 s` stride roughly doubles the opportunities but needs a
separate perceptual and interference audit before it should become default.

## Reproduce

```powershell
python -m stegosaurus.audio.experiments.blind_recovery.iteration_009_block_schema_length_sweep.run
```

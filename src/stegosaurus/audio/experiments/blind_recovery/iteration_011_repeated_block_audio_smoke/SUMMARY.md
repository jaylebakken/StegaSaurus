# Iteration 011: Repeated Block Audio Smoke

## Goal

Move the block-voting schema from analytical planning to an audio-bearing smoke
test. This embeds the same claimed handle into independent `30 s` blocks,
concatenates those blocks into longer synthetic songs, and recovers from exact
block windows.

## Method

- Synthetic song lengths:
  - `30 s`: one block,
  - `2.5 min`: five blocks,
  - `5 min`: ten blocks.
- Each block is independently embedded with the same claimed handle.
- Recovery uses exact block windows and the received-duration stage only.
- Voting checks whether any block recovers and whether at least two blocks
  recover.

## Scope Boundary

This is not localization yet. The verifier receives exact block windows. The
purpose is to verify that repeated independent blocks are compatible with the
current recovery path before adding a pilot prefilter or unknown window search.

## Result

| Song length | Blocks | Recovered blocks | Any-block vote | Two-block vote | Elapsed |
| --- | ---: | ---: | --- | --- | ---: |
| `30 s` | 1 | 1 | accept | abstain | `2.63 s` |
| `2.5 min` | 5 | 3 | accept | accept | `12.98 s` |
| `5 min` | 10 | 8 | accept | accept | `25.99 s` |

This is strong smoke evidence for repeated independently recoverable `30 s`
blocks. The longer synthetic songs do not need one giant codeword: they provide
more chances to recover the same claimed handle. The exact-window requirement is
still a major limitation, but the block-voting schema itself is compatible with
the current received-duration recovery path.

## Recommendation

Use repeated `30 s` block-local watermarks as the next production-oriented
schema prototype. Any-block voting is suitable for the first online recovery
path; two-block voting is feasible for longer songs when a higher-assurance or
offline result is desired. The next missing piece is localization: a cheap
pilot-window prefilter that proposes the exact block windows used here.

## Reproduce

```powershell
python -m stegosaurus.audio.experiments.blind_recovery.iteration_011_repeated_block_audio_smoke.run
```

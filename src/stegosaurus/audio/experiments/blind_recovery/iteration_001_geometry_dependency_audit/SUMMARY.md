# Iteration 001: Geometry Dependency Audit

## Goal

Start a blind-recovery experiment track by measuring the current edge-mode
non-oracle decoder's dependence on original waveform geometry. The practical
question is how much a verifier must know about the original sample duration
before it can recover attribution without the retained encoder frame map.

## Method

- Fresh 30-second synthetic cover for the default audit: seed `7800`.
- Fixed transport and local-pilot path from non-oracle iteration 032:
  4-byte handle, 16 Reed--Solomon parity symbols, 20 protected bytes,
  184 logical carriers, four replicas, and the `500-3800 Hz` carrier band.
- Attacks: clean PCM, named `250 ms` leading crop, and named `250 ms`
  trailing crop.
- Decoder assumptions:
  - exact original duration,
  - received duration only,
  - original duration shifted by `-10 ms`, `+10 ms`, `-50 ms`, and `+50 ms`.
- Selection still uses only decoder-visible RS success, framing burden, and
  pilot evidence. The retained encoder map and expected handle are not used to
  choose a hypothesis.
- The default run omits independent unwatermarked and wrong-secret controls to
  keep the first geometry audit lightweight. The JSON marks this as
  `controls_evaluated: false`; future validation iterations should restore
  controls after narrowing the geometry-search policy.

## Observed Results

| Attack | Geometry assumption | Exact recovery | Selected offset | RS cost |
| --- | --- | ---: | --- | ---: |
| Clean PCM | exact original duration | 1/1 | `0` | 13 |
| Clean PCM | received duration only | 1/1 | `0` | 13 |
| Clean PCM | original duration shifted by `+/-10 ms` or `+/-50 ms` | 0/4 | none | n/a |
| Trailing `250 ms` crop | exact original duration | 1/1 | `0` | 13 |
| Trailing `250 ms` crop | original duration underestimated by `10 ms` | 1/1 | `0` | 13 |
| Trailing `250 ms` crop | received duration only or other shifted assumptions | 0/4 | none | n/a |
| Leading `250 ms` crop | exact original duration | 1/1 | `15` | 13 |
| Leading `250 ms` crop | received duration only or shifted assumptions | 0/5 | none | n/a |

## Interpretation

The current edge-mode recovery is more geometry-sensitive than the offset list
alone suggests. Small duration errors can still include a plausible edge offset,
but changing the assumed nominal duration also changes the nominal frame count
and therefore the four-replica carrier strata used for local candidate
generation. In the default seed, `+/-10 ms` geometry error was enough to break
clean recovery, and the leading-crop case recovered only when the original
duration was exact.

For the goal of reliable attribution with minimal original geometry, the next
experiment should avoid committing the replica strata to a single nominal
duration. A better blind-recovery search should bank nearby nominal frame counts
or source-duration hypotheses, then rank only decoder-visible RS-successful
results. That would directly test whether duration uncertainty can be treated
like the successful edge-offset bank from non-oracle iteration 032.

## Scope Boundary

This is not unknown-handle discovery. The decoder still receives the claimed
transport plan so it can evaluate a fixed 4-byte handle layout. The experiment
isolates geometry dependence before attempting broader blind registry lookup,
unknown duration search, codec/DSP combinations, or recorded-audio validation.

## Reproduce

```powershell
python -m stegosaurus.audio.experiments.blind_recovery.iteration_001_geometry_dependency_audit.run
```

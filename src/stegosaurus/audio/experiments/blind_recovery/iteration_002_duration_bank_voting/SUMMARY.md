# Iteration 002: Duration-Bank Voting

## Goal

Test whether blind recovery can depend on a small, declared application
pipeline policy instead of an exact original duration. Iteration 001 showed
that even small duration errors can break recovery because the assumed nominal
frame count changes replica strata. This iteration runs synchronized recovery
attempts under multiple plausible source-duration hypotheses, then accepts only
a uniquely best decoder-visible Reed--Solomon success.

## Method

- Fresh 30-second synthetic cover for the default audit: seed `7900`.
- Fixed transport and local-pilot path from non-oracle iteration 032:
  4-byte handle, 16 Reed--Solomon parity symbols, 20 protected bytes,
  184 logical carriers, four replicas, and the `500-3800 Hz` carrier band.
- Attacks: clean PCM, named `250 ms` leading crop, and named `250 ms`
  trailing crop.
- Duration-bank policies:
  - `received_only`: original duration equals received duration.
  - `clean_or_250ms_edge_loss`: original duration is received duration or
    received duration plus `250 ms`.
  - `clean_or_250ms_edge_loss_jittered`: original duration is received
    duration plus `0`, `240 ms`, `250 ms`, or `260 ms`.
- Selection ranks only decoder-visible RS successes by correction burden,
  erasures, synchronization mismatches, and then smaller inferred pipeline loss.

## Observed Results

| Attack | Duration bank | Exact recovery | Selected inferred loss | Selected offset | RS cost |
| --- | --- | ---: | ---: | --- | ---: |
| Clean PCM | received only | 1/1 | `0 ms` | `0` | 4 |
| Clean PCM | clean or `250 ms` edge loss | 1/1 | `0 ms` | `0` | 4 |
| Clean PCM | jittered around `250 ms` edge loss | 1/1 | `0 ms` | `0` | 4 |
| Trailing `250 ms` crop | received only | 0/1 | n/a | none | n/a |
| Trailing `250 ms` crop | clean or `250 ms` edge loss | 1/1 | `250 ms` | `0` | 4 |
| Trailing `250 ms` crop | jittered around `250 ms` edge loss | 1/1 | `240 ms` | `0` | 4 |
| Leading `250 ms` crop | received only | 0/1 | n/a | none | n/a |
| Leading `250 ms` crop | clean or `250 ms` edge loss | 1/1 | `250 ms` | `16` | 4 |
| Leading `250 ms` crop | jittered around `250 ms` edge loss | 1/1 | `250 ms` | `16` | 4 |

## Interpretation

A small pipeline-informed duration bank recovers both named crop directions in
the default seed without requiring an exact original duration from the user.
This supports treating blind recovery partly as an application policy: run
synchronized decode attempts for declared pipeline possibilities, then accept a
single lowest-burden RS success.

The jittered trailing case selected `240 ms` rather than the exact `250 ms`
because both candidates had the same decoder-visible correction burden and the
tie-break prefers smaller inferred loss. That still recovered the handle, but it
shows the voting rule itself is now part of the experimental contract. Wider
validation should report ambiguous equal-burden successes and restore controls
before expanding the bank.

## Scope Boundary

This is an application-policy experiment, not a new carrier design. It still
receives the claimed transport plan and does not attempt unknown-handle
discovery. It also does not include controls in the default run; wider sweeps
must restore independent unwatermarked and wrong-secret controls because every
extra duration hypothesis increases the false-accept surface.

## Reproduce

```powershell
python -m stegosaurus.audio.experiments.blind_recovery.iteration_002_duration_bank_voting.run
```

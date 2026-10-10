# Iteration 003: Flexibility And Control Audit

## Goal

Compare a narrow duration-bank policy against a broader single-edge policy while
restoring independent unwatermarked and wrong-secret controls. This tests the
practical path toward a maximally flexible recovery scheme: synchronize multiple
recovery runs and vote only among decoder-visible RS successes.

## Method

- Fresh 30-second synthetic cover for the default compact audit: seed `7900`.
- Fixed transport and local-pilot path from non-oracle iteration 032:
  4-byte handle, 16 Reed--Solomon parity symbols, 20 protected bytes,
  184 logical carriers, four replicas, and the `500-3800 Hz` carrier band.
- Attacks: clean PCM and named `250 ms` leading crop. The leading crop is the
  compact stress case because recovery must choose an edge offset.
- Duration banks:
  - `clean_or_250ms_edge_loss`: received duration plus `0` or `250 ms`.
  - `single_edge_loss_to_500ms`: received duration plus `0`, `125 ms`,
    `250 ms`, `375 ms`, or `500 ms`.
- Controls: transformed unwatermarked source audio and wrong-secret decoding of
  the transformed watermarked audio.

## Result

| Attack | Bank | Watermarked acceptances | Exact recoveries | Unwatermarked acceptances | Wrong-secret acceptances | Median RS cost |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `clean_pcm` | `clean_or_250ms_edge_loss` | 1/1 | 1/1 | 0/1 | 0/1 | 4 |
| `clean_pcm` | `single_edge_loss_to_500ms` | 1/1 | 1/1 | 0/1 | 0/1 | 4 |
| `leading_crop_025s` | `clean_or_250ms_edge_loss` | 1/1 | 1/1 | 0/1 | 0/1 | 4 |
| `leading_crop_025s` | `single_edge_loss_to_500ms` | 1/1 | 1/1 | 0/1 | 0/1 | 4 |

No watermarked vote was ambiguous under the unique lowest-RS-burden policy. The
broader five-candidate bank did not increase observed false acceptances in this
compact audit, but it did increase runtime roughly in proportion to the number
of synchronized decoder runs.

An exploratory seed probe with cover seed `8000` abstained even on clean
watermarked audio. That is a limitation of the current pilot/transport
operating point, not a duration-bank fix: maximal flexibility must include a
baseline signal-quality gate before expanding geometry hypotheses.

## Next Direction

The flexible recovery policy should become a staged controller:

1. Run a cheap baseline quality probe on the received audio and claimed plan.
2. Expand duration hypotheses only when the baseline probe has enough pilot and
   carrier evidence to justify the runtime and false-accept surface.
3. Vote across synchronized runs by unique lowest RS burden, then require
   control-derived acceptance thresholds before exposing attribution.
4. Add optional banks for trailing crop, leading crop, narrow duration jitter,
   and eventually resampling or codec-specific transforms as separate declared
   pipeline hypotheses.

## Scope Boundary

This is still claimed-handle recovery with a supplied transport plan, not
unknown-handle discovery. A broader bank increases runtime and false-accept
surface, so controls and ambiguity counts are part of the experiment contract.

## Reproduce

```powershell
python -m stegosaurus.audio.experiments.blind_recovery.iteration_003_flexibility_control_audit.run
```

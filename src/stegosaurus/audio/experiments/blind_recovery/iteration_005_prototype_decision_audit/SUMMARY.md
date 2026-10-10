# Iteration 005: Prototype Decision Audit

## Goal

Evaluate the staged controller as a production-shaped accept/abstain policy.
The important question is no longer only whether recovery can succeed on a
fixture, but whether the prototype can make bounded decisions when recovery
does not succeed.

## Method

- Fixed claimed-plan transport path from the blind-recovery track.
- Staged controller from iteration 004:
  - received duration,
  - declared `250 ms` edge loss,
  - broad single-edge fallback up to `500 ms`.
- Scenarios:
  - known-good clean seed `7900`,
  - known-good `250 ms` leading crop seed `7900`,
  - weak clean probe seed `8000`, which iteration 003 found did not recover.
- Controls: unwatermarked source and wrong-secret decode for every scenario.
- Decision policy: accept only when watermarked audio has a unique low-burden
  success and both controls abstain. Otherwise reject on control acceptance or
  abstain after bounded search exhaustion.
- The experiment now uses the application `BlindRecoveryDecisionPolicy`, so the
  measured prototype behavior and reusable production-facing policy share one
  decision contract.

## Expected Interpretation

If the known-good cases accept, controls stay quiet, and the weak clean probe
abstains instead of drifting into a false acceptance, the current approach is a
workable bounded verifier prototype for declared pipeline hypotheses. It is not
yet a robust production product because the weak probe still represents a
signal-floor failure, but it gives the production pipeline a safe decision:
attribute, reject, or abstain.

## Result

| Scenario | Attack | Decision | Reason | Stage | Attempts | Exact recovery | Control acceptances | RS cost |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| `known_good_clean` | `clean_pcm` | accept | `unique_low_burden_success` | `received_only` | 1 | 1/1 | 0 | 4 |
| `known_good_leading_crop` | `leading_crop_025s` | accept | `unique_low_burden_success` | `single_250ms_edge_loss` | 2 | 1/1 | 0 | 4 |
| `weak_clean_probe` | `clean_pcm` | abstain | `bounded_search_exhausted` | none | 5 | 0/1 | 0 | n/a |

This is the first workable prototype shape for a production pipeline:

1. Accept when a claimed-plan decode has a unique low-burden RS success and
   controls abstain.
2. Expand geometry hypotheses only through declared stages.
3. Abstain after bounded search exhaustion instead of widening indefinitely.

The result also clarifies the next limit. The current watermark/pilot settings
can produce clean watermarked audio that does not recover even after the bounded
declared-geometry search. That is not fixed by blind recovery policy; it points
to either an embed/signal-strength floor, a stronger quality preflight, or a
different transport operating point.

## Reproduce

```powershell
python -m stegosaurus.audio.experiments.blind_recovery.iteration_005_prototype_decision_audit.run
```

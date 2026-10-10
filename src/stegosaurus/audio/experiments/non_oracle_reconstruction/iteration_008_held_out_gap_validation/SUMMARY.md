# Iteration 008: Held-Out Gap-Policy Validation

## Goal

Validate one frozen non-oracle local-pilot threshold policy on fresh variants that were not used for score telemetry or policy selection.

## Method

- Calibration source: iteration 007's ten telemetry variants with seeds `6100-6109`.
- Exploratory replay grid: absolute pilot thresholds `0.00-0.40` and pilot gaps `0.08-1.00` under the declared selection rule of maximum exact recovery, then minimum median RS cost.
- Frozen policy: absolute expected-pilot threshold `0.00`; selected-minus-rival pilot-gap threshold `0.24`.
- Validation: ten fresh synthetic 30-second covers with seeds `6300-6309`, distinct from calibration variants.
- Encoder: iteration 005 contrastive calibration and the fixed 4-pilot / 12-payload pair allocation.
- Transport: 8-byte token, 12 Reed--Solomon parity symbols, four copies, `relative_difference=0.95`, and the `500-3800 Hz` carrier band.
- Decoder: blind non-oracle reconstruction using only received audio, the secret, and the frozen configuration. Oracle maps and known token bits are consulted only afterward for diagnostics.
- Controls: unwatermarked and wrong-secret decodes for every validation cover; a control counts only when it exactly returns the known token.

## Results

| Metric | Result |
| --- | ---: |
| Exact token recoveries | 8 / 10 |
| Median / maximum RS cost | 10.5 / 14, with a 12-symbol budget |
| Median known carrier-bit errors | 7.0 |
| Median carrier erasures | 1.0 |
| Median unknown byte errors | 5.0 |
| Median byte erasures | 1.0 |
| Median selected-map accuracy | 99.50% |
| Median map-erasure rate | 18.48% |
| Unwatermarked exact-token false accepts | 0 / 10 |
| Wrong-secret exact-token false accepts | 0 / 10 |

The eight recovered trials have RS costs `4`, `6`, `9`, `10`, `10`, `11`, `12`, and `12`. The two unrecovered trials have costs `13` and `14`, exceeding the correction budget by one and two units. This is a material held-out improvement over iteration 006's low threshold grid, but it remains limited to the declared synthetic fixture family and one frozen policy.

## Interpretation

- The iteration-007 pilot-gap telemetry was useful for selecting a decoder policy that generalizes to fresh synthetic variants from the same generator family.
- The policy deliberately converts enough ambiguous physical map choices into erasures to bring median Reed--Solomon damage within budget while retaining sufficient four-copy payload evidence.
- The policy is not production-ready: the validation covers are synthetic and related, the calibration process reused prior experimental knowledge, and ten variants cannot establish a reliable recovery rate or false-positive rate.
- The two misses sit close to the RS boundary, so further improvements should target reducing one or two remaining byte-level damage events rather than changing token size or parity immediately.

## Decision

Treat the frozen `absolute=0.00`, `gap=0.24` policy as the current **synthetic clean-fixture candidate**, not a general decoder default. Before named attacks, repeat held-out validation on a larger and more varied licensed corpus with pre-registered recovery and false-accept metrics. Separately, investigate selective extra local-pilot redundancy only for the marginal byte failures observed here.

## Reproduce

The complete machine-readable validation output is archived in `RESULTS.json` beside this summary.

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_008_held_out_gap_validation.run
```

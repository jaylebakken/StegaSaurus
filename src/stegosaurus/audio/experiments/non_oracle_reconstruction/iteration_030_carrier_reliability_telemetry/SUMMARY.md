# Iteration 030: Carrier Reliability Telemetry

## Goal

Identify whether a remaining non-oracle trailing-crop abstention is caused by weak payload evidence after correct carrier selection or by incorrect local candidate-frame selection itself.

## Method

- Replayed iteration 028's trailing seed `7600` abstention and seed `7601` recovery.
- Kept the 4-byte/16-parity codeword, duration-feasible coarse bank, carrier band, and local pilot thresholds unchanged.
- Measured every logical carrier post-hoc: selected-replica count, retained-map agreement, combined-score magnitude, erasure status, and expected-bit agreement.

## Results

| Case | Recovered | Retained-map agreement | Median `|combined score|` | Carrier erasures | Observed bit errors |
| --- | --- | ---: | ---: | ---: | ---: |
| Seed `7600`, trailing crop | No | `0.0%` | `0.1645` | `14` | `82 / 170` |
| Seed `7601`, trailing crop | Yes | `99.3%` | `0.3185` | `1` | `5 / 179` |

The failed case still selects a median of two replica frames per carrier, but none agree with the retained encoder frame map. The recovered case selects a median of three replicas and nearly all agree with that map.

## Decision

The current rare-failure mechanism is candidate-map reconstruction, not Reed--Solomon allocation, phase alignment alone, or payload-pair strength after correct selection. The next experiment should test a map-selection improvement such as a multi-candidate local pilot score, consistency voting across replicas, or an additional independent selection-pilot channel. It should preserve the fixed 16-parity transport and report the same map-correctness, RS-cost, and control telemetry.

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_030_carrier_reliability_telemetry.run
```

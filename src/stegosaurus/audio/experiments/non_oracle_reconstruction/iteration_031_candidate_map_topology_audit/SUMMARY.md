# Iteration 031: Candidate Map Topology Audit

## Goal

Classify whether the failed carrier map from iteration 030 is a pilot rank error, a missing true-frame candidate, or a systematic timeline displacement.

## Method

- Replayed trailing seeds `7600` (abstention) and `7601` (recovery) with the unchanged iteration 021 duration-feasible coarse bank.
- For each of the `736` replica/carrier decisions, compared the two generated blind candidate frames and the selected frame against the retained encoder frame map post-hoc.
- Checked the selected blind hypothesis for its coarse offset and deterministic residual phase.

## Results

| Case | Payload recovered | True-frame candidate coverage | Exact selected-frame rate | Modal selected displacement |
| --- | --- | ---: | ---: | ---: |
| Seed `7600`, trailing crop | No | `0.0%` (`0 / 736`) | `0.0%` (`0 / 406`) | `-15` frames (`175` selections) |
| Seed `7601`, trailing crop | Yes | `98.1%` (`722 / 736`) | `99.3%` (`587 / 591`) | `0` frames (`587` selections) |

The failed seed's only duration-feasible blind hypothesis uses coarse offset `+15` and residual phase `-160` samples. Its candidate generator therefore produces frames displaced by exactly `-15` relative to the encoder map; the true frame is absent from every two-candidate choice. The recovered case has no systematic displacement and only one wrong-rank decision where the true frame is available.

## Decision

The telemetry reclassifies the rare failure as a **coarse-offset hypothesis coverage** issue that manifests as a carrier-map failure. Improving the payload-pair modulation or local pilot rank discriminator cannot recover a frame that never enters the candidate set.

The next experiment should pre-register a small keyed coarse-neighbor bank around duration-feasible offsets (for example the selected coarse offset and bounded neighbors) before local candidate-map construction. It must report whether the true timing offset enters the bank post-hoc, the resulting map coverage, byte RS cost, and negative-control behavior. It must not use the retained map or known handle to choose an offset.

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_031_candidate_map_topology_audit.run
```

"""Run iteration 017: build the V3 release validation matrix.

Goal: make the V3 plan actionable. Iteration 016 defines the waterfall order;
this iteration records which capabilities are ready for V3, which stay
experimental, and which validations must run before any stronger claim.

Toy flow:
    capability -> current evidence -> missing evidence -> release gate

This is a planning artifact over measured synthetic experiments. It does not
expand the robustness claim surface.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json


@dataclass(frozen=True, slots=True)
class ValidationGate:
    """Record one V3 candidate capability and its release gate."""

    capability: str
    release_bucket: str
    current_evidence: tuple[str, ...]
    missing_validation: tuple[str, ...]
    go_gate: str
    no_go_gate: str


def _gates() -> tuple[ValidationGate, ...]:
    """Return the V3 validation matrix in release-decision order."""

    return (
        ValidationGate(
            "repeated_30s_block_schema",
            "V3 core",
            (
                "iteration_011: 2.5 min recovered 3/5 blocks; 5 min recovered 8/10 exact windows",
                "v2 application codec embeds repeated complete blocks with retained records",
            ),
            (
                "separately seeded clean fixture beyond the original synthetic song",
                "runtime budget for 2.5 min and 5 min encode/decode",
            ),
            "clean repeated blocks recover with at least two votes or pooled recovery and no controls",
            "clean repeated blocks cannot recover a retained claim within RS budget",
        ),
        ValidationGate(
            "pilot_window_prefilter",
            "V3 core",
            (
                "iteration_012: top five windows contained all five exact block starts",
                "iteration_014: top seven ranked exact starts before overlapping windows",
            ),
            (
                "held-out seeds with 2.5 min and 5 min songs",
                "bounded leading/trailing crops with unknown received offsets",
            ),
            "top-K ranking consistently contains enough true block starts for voting or pooling",
            "top-K ranking loses true starts often enough that geometry search must run first",
        ),
        ValidationGate(
            "fast_block_vote",
            "V3 core",
            (
                "iteration_014: top three produced two votes; top five produced three votes",
                "iteration_016: two-vote fast path is the lowest-cost accepted stage",
            ),
            (
                "wrong-secret and unwatermarked controls on the repeated-block fixture",
                "false-accept policy for one-vote versus two-vote modes",
            ),
            "two-vote acceptance remains clean under controls and held-out synthetic covers",
            "controls produce accepted block votes or two-vote recovery is unreliable",
        ),
        ValidationGate(
            "cross_block_carrier_pooling",
            "V3 core after controls",
            (
                "iteration_015: top-five pooled RS cost was 0 on the measured fixture",
                "iteration_016: zero-vote pooled recovery is classified as block distress",
            ),
            (
                "negative controls for wrong secret and unwatermarked audio",
                "ablation where overlapping non-block windows are included in the pool",
                "bounded crop cases where localization is plausible but block votes are weak",
            ),
            "pooled recovery accepts retained/watermarked claims and rejects controls within RS budget",
            "pooling accepts controls or becomes unstable when top-K includes non-block windows",
        ),
        ValidationGate(
            "geometry_fallback",
            "experimental V3 fallback",
            (
                "iteration_032 non-oracle: 10/10 leading and trailing 250 ms synthetic crop recovery",
                "blind iteration_006/007: bounded crop search gives a maximum-cost route",
            ),
            (
                "integration with block-window localization",
                "multiple crop lengths and dual-edge crops",
                "runtime cap for offline support mode",
            ),
            "geometry fallback rescues localization/timing distress without control acceptances",
            "geometry search is too slow, ambiguous, or accepts controls under broader fixtures",
        ),
        ValidationGate(
            "unknown_arbitrary_crop_length",
            "V3-later",
            (
                "iteration_006/007 explored bounded crop assumptions",
                "iteration_016 keeps this outside the core V3 claim",
            ),
            (
                "search bounds, stopping policy, and false-positive analysis",
                "large crop-length sweep with controls",
            ),
            "bounded crop search has measured limits, runtime, and abstention policy",
            "unknown crop search is ambiguous or too costly for release",
        ),
        ValidationGate(
            "codec_recorded_audio_claims",
            "out of scope for V3",
            (
                "current experiments are synthetic PCM-focused",
            ),
            (
                "codec sweeps",
                "recorded playback/capture fixtures",
                "perceptual and content-diversity studies",
            ),
            "future release has named evaluations for each transformation claim",
            "no measured evidence exists for the transformation class",
        ),
    )


def run() -> dict[str, object]:
    """Return the V3 validation matrix and release recommendation."""

    gates = _gates()
    return {
        "goal": "define V3 release gates for the optimized blind-recovery waterfall",
        "release_recommendation": {
            "V3_core": [
                gate.capability
                for gate in gates
                if gate.release_bucket in {"V3 core", "V3 core after controls"}
            ],
            "experimental": [
                gate.capability
                for gate in gates
                if gate.release_bucket == "experimental V3 fallback"
            ],
            "defer": [
                gate.capability
                for gate in gates
                if gate.release_bucket in {"V3-later", "out of scope for V3"}
            ],
        },
        "gates": [asdict(gate) for gate in gates],
    }


def main() -> None:
    """Print the V3 release validation matrix."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()


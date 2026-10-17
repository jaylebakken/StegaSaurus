"""Run iteration 023: synthesize robustness implementation launch points.

Goal: convert the attack robustness experiments into implementation guidance.
The plan separates features that can start from the current waterfall from
features that need a new recovery stage before product implementation.

Toy flow:
    attack matrix outcomes -> family disposition -> implementation next step

This is a planning artifact grounded in synthetic experiments. It does not
claim robustness beyond the named measured transformations.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json


@dataclass(frozen=True, slots=True)
class RobustnessFamily:
    """Describe one robustness family and its implementation disposition."""

    name: str
    disposition: str
    evidence: str
    launch_point: str
    required_gate: str


@dataclass(frozen=True, slots=True)
class ImplementationStage:
    """Describe one recommended implementation step."""

    order: int
    name: str
    scope: str
    done_when: str


def _families() -> tuple[RobustnessFamily, ...]:
    """Return the measured robustness disposition table."""

    return (
        RobustnessFamily(
            "codec_mp3_96k",
            "launch_candidate",
            "iteration 021 recovered MP3 96k with pooled RS cost 0; negative controls rejected at 32 and 32",
            "add named codec-transformed verification profile around the current waterfall",
            "held-out bitrate sweep with wrong-secret and unwatermarked controls",
        ),
        RobustnessFamily(
            "recorded_audio_proxy_light",
            "launch_candidate",
            "iteration 021 recovered the light recorded-audio proxy with pooled RS cost 2; controls rejected at 35 and 36",
            "add named recorded-proxy evaluation profile around the current waterfall",
            "held-out proxy sweep over noise, reverb, low-pass, and resampling parameters",
        ),
        RobustnessFamily(
            "arbitrary_off_grid_crop",
            "blocked_needs_new_stage",
            "iteration 021 failed at RS cost 36; iteration 022 phase bank still failed at RS cost 33 with no near starts in top five",
            "prototype synchronization and local boundary refinement before product implementation",
            "near-start candidates must appear in top windows and controls must reject before pooling can be trusted",
        ),
    )


def _stages() -> tuple[ImplementationStage, ...]:
    """Return a staged implementation path from safest to riskiest."""

    return (
        ImplementationStage(
            1,
            "robustness_diagnostics",
            "record attack/profile name, ranked windows, block votes, pooled RS cost, and control outcome",
            "every verification result explains which waterfall stage accepted or rejected",
        ),
        ImplementationStage(
            2,
            "codec_and_recorded_proxy_profiles",
            "implement named profiles that reuse the current prefilter/vote/pool waterfall",
            "MP3 and light recorded-proxy held-out sweeps recover while controls reject",
        ),
        ImplementationStage(
            3,
            "crop_sync_research_stage",
            "prototype crop-offset estimation before carrier extraction",
            "off-grid crops rank near block starts before pooling is attempted",
        ),
        ImplementationStage(
            4,
            "crop_product_gate",
            "only promote crop recovery after the sync stage clears controls",
            "arbitrary crop cases recover with RS headroom and negative controls remain outside budget",
        ),
    )


def run() -> dict[str, object]:
    """Return the robustness launch plan."""

    families = _families()
    return {
        "goal": "state launch points and blockers for robustness implementation",
        "families": [asdict(family) for family in families],
        "implementation_stages": [asdict(stage) for stage in _stages()],
        "launch_now": [family.name for family in families if family.disposition == "launch_candidate"],
        "blocked": [family.name for family in families if family.disposition == "blocked_needs_new_stage"],
        "claim_boundary": (
            "Start implementation with named codec and light recorded-audio proxy profiles. "
            "Do not implement arbitrary crop as a product claim until a new sync stage "
            "creates near-start windows and passes negative controls."
        ),
    }


def main() -> None:
    """Print the robustness launch plan."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

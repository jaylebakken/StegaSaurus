"""Run iteration 020: synthesize the V3 blind-recovery release plan.

Goal: turn the measured waterfall experiments into a concrete V3 release plan.
The plan separates what can be promoted into the early production path from
what should remain an explicit expensive fallback or research-only support
tool.

Toy flow:
    measured evidence -> release stages -> gates -> V3 scope decision

This is a planning artifact. It cites measured synthetic experiments and does
not turn bounded-crop or geometry results into broad robustness claims.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json


@dataclass(frozen=True, slots=True)
class ReleaseItem:
    """Describe one V3 feature candidate and its release disposition."""

    name: str
    disposition: str
    evidence: str
    gate: str
    reason: str


@dataclass(frozen=True, slots=True)
class WaterfallStep:
    """Describe the optimized V3 recovery order."""

    order: int
    name: str
    cost: str
    enter_when: str
    accept_when: str
    fallback_when: str


def _waterfall() -> tuple[WaterfallStep, ...]:
    """Return the recommended V3 waterfall from cheapest to most expensive."""

    return (
        WaterfallStep(
            1,
            "pilot_window_prefilter",
            "low",
            "always for blind recovery",
            "ranked windows exist for the expected block duration",
            "no sufficiently scored candidate windows are found",
        ),
        WaterfallStep(
            2,
            "fast_block_vote",
            "medium",
            "top ranked windows are available",
            "two independent block recoveries agree on the handle",
            "fewer than two valid block votes are returned",
        ),
        WaterfallStep(
            3,
            "cross_block_evidence_pool",
            "medium-high",
            "windows localize plausible blocks but votes are weak",
            "pooled recovery returns the claimed handle within RS budget and controls reject",
            "pooled result exceeds budget or controls are unavailable",
        ),
        WaterfallStep(
            4,
            "bounded_crop_support_fallback",
            "high",
            "operator requests expensive recovery or localization has edge-crop symptoms",
            "unique low-burden recovery is reproduced with control diagnostics",
            "crop length is arbitrary or confidence is boundary-only",
        ),
        WaterfallStep(
            5,
            "research_geometry_search",
            "maximum",
            "archived experimentation or offline investigation",
            "measured experiment-specific recovery with explicit assumptions",
            "any production-facing claim would be implied",
        ),
    )


def _release_items() -> tuple[ReleaseItem, ...]:
    """Return the V3 feature disposition matrix."""

    return (
        ReleaseItem(
            "repeated_30s_block_embedding",
            "promote",
            "iterations 011-013 establish repeated blocks and window ranking on synthetic songs",
            "application tests plus a small synthetic blind-recovery smoke gate",
            "it gives the decoder multiple aligned chances without requiring unknown-geometry search",
        ),
        ReleaseItem(
            "pilot_window_prefilter",
            "promote",
            "iteration 012 ranks exact block starts into the top candidates",
            "top windows must include plausible block starts before expensive stages run",
            "it is the cheapest tool for finding where the watermark likely lives",
        ),
        ReleaseItem(
            "fast_block_vote",
            "promote",
            "iterations 013-014 show early acceptance when independent blocks agree",
            "two matching block votes for online attribution; stricter modes may require more",
            "it avoids spending geometry search when direct block evidence is already enough",
        ),
        ReleaseItem(
            "cross_block_evidence_pooling",
            "promote with controls",
            "iterations 015, 018, and 019 recover pooled evidence while rejecting negative controls",
            "wrong-secret and unwatermarked controls must reject for the fixture class",
            "it handles block distress better than geometry search when localization still works",
        ),
        ReleaseItem(
            "bounded_dual_edge_crop_recovery",
            "support fallback",
            "iteration 019 recovers a 15s plus 15s crop exactly at the RS budget boundary",
            "only run after cheaper stages fail and report boundary confidence explicitly",
            "the result is feasible but too close to the acceptance limit for a broad V3 claim",
        ),
        ReleaseItem(
            "arbitrary_crop_or_codec_robustness",
            "defer",
            "current experiments do not validate arbitrary crop lengths, codec chains, or recorded audio",
            "requires a larger held-out matrix with attacks and negative controls",
            "shipping this as a claim would exceed measured evidence",
        ),
    )


def run() -> dict[str, object]:
    """Return the synthesized V3 waterfall and release disposition."""

    items = _release_items()
    return {
        "goal": "define the V3 blind-recovery waterfall and release boundary",
        "waterfall": [asdict(step) for step in _waterfall()],
        "release_items": [asdict(item) for item in items],
        "promote": [item.name for item in items if item.disposition.startswith("promote")],
        "support_fallback": [item.name for item in items if item.disposition == "support fallback"],
        "defer": [item.name for item in items if item.disposition == "defer"],
        "v3_claim": (
            "V3 can claim synthetic repeated-block blind attribution with pilot windowing, "
            "fast block voting, pooled evidence, and explicit negative controls; it should not "
            "claim arbitrary crop, codec, or recorded-audio robustness."
        ),
    }


def main() -> None:
    """Print the V3 release plan."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

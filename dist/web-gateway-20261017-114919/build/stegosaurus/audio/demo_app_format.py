"""Format Tkinter demo action results for display.

The Tkinter app should remain a control surface. This helper keeps nested
diagnostic formatting for block-waterfall and V4 known-song results out of the
layout module.
"""

from __future__ import annotations

from .attribution import BlockAttributionVerification, RepeatedBlockWaterfallDecision
from .attribution_workflow import KnownSongVerification


def describe_result(label: str, result: object) -> str:
    """Return a concise user-facing summary for one controller action."""

    verification = _last_block_verification(result)
    decision = _last_waterfall_decision(result)
    if isinstance(verification, BlockAttributionVerification):
        pooled = verification.pooled_verification
        if decision is not None:
            return (
                f"{label}: {'accepted' if decision.accepted else 'not accepted'} via {decision.stage.value}; "
                f"pooled RS cost {pooled.claim_rs_cost}/16; "
                f"block votes {verification.recovered_block_count}/{len(verification.block_verifications)}."
            )
        return (
            f"{label}: {verification.status.value}; pooled RS cost {pooled.claim_rs_cost}/16; "
            f"block votes {verification.recovered_block_count}/{len(verification.block_verifications)}."
        )
    if isinstance(result, KnownSongVerification):
        winner = result.matched_recipient_label or "none"
        top = result.ranked_exports[0] if result.ranked_exports else None
        cost = "n/a" if top is None else f"{top.pooled_rs_cost}/16"
        return f"{label}: {'accepted' if result.accepted else 'not accepted'}; match {winner}; top RS cost {cost}."
    return f"{label}."


def _last_block_verification(result: object) -> object:
    """Return the block verification nested inside one controller action result."""

    if isinstance(result, BlockAttributionVerification):
        return result
    if isinstance(result, tuple):
        for item in result:
            found = _last_block_verification(item)
            if isinstance(found, BlockAttributionVerification):
                return found
    return result


def _last_waterfall_decision(result: object) -> RepeatedBlockWaterfallDecision | None:
    """Return the block-waterfall decision nested inside one controller action result."""

    if isinstance(result, RepeatedBlockWaterfallDecision):
        return result
    if isinstance(result, tuple):
        for item in result:
            found = _last_waterfall_decision(item)
            if found is not None:
                return found
    return None

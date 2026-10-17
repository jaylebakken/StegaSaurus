"""Define records for the distressed block-redundancy sweep.

The sweep treats block duration as a configurable product profile. Shorter
blocks reduce per-block capacity margin but increase the number of complete
watermark opportunities inside an arbitrary crop.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BlockProfileResult:
    """Summarize one block-duration profile under light proxy distress."""

    block_seconds: float
    best_label: str
    best_rs_cost: int
    second_label: str
    second_rs_cost: int
    accepted_label: str | None
    false_accept_count: int
    status: str


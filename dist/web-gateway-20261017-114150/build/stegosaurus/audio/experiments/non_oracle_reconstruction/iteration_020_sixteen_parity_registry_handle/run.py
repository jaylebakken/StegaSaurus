"""Run iteration 020: test whether sixteen parity symbols improve blind crop recovery.

Experiment goal: compare the existing 6-byte opaque registry handle plus 14
Reed--Solomon parity symbols against a 4-byte versioned external registry
handle plus 16 parity symbols. Both configurations keep the protected codeword
at 20 bytes, including the schema's separate three framing/checksum bytes, and
therefore preserve 184 logical carrier bits and 736 four-replica placements.
The two additional parity symbols raise the errors-only correction radius from
seven to eight byte symbols. The 32-bit value is deliberately modeled as a
collision-checked and reissuable registry key; it is not a collision-resistant
digest and this is not a production registry implementation.

Pipeline state: the center-only combiner remains frozen after iteration 018.
This study reuses iteration 019's blind keyed coarse scan, deterministic
one-edge crop center phase, frozen contrastive carrier selection, fresh cover
seeds 7100-7109, unchanged 250 ms leading/trailing crops, and independent
unwatermarked/wrong-secret controls. It isolates the codeword allocation so
that recovery differences are not due to carrier capacity, alignment policy,
cover, or attack changes.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict
import json

from ...transport_optimization.iteration_006_duration_stability_bounds.run import (
    _cover_variant,
    _trial_offset_seconds,
)
from ..iteration_011_blind_attack_validation.run import AttackDefinition
from ..iteration_019_registry_handle_parity_tradeoff.run import (
    HandleAllocation,
    RegistryParityTrial,
    _allocation_trials,
    _crop_attacks,
    _summary,
)


def _handle_allocations() -> tuple[HandleAllocation, ...]:
    """Return the fourteen-parity baseline and sixteen-parity short registry allocation."""

    return (
        HandleAllocation(
            "opaque_token_6_parity_14",
            6,
            14,
            "48-bit opaque registry handle retained from the current transport candidate.",
            "0123456789ab",
        ),
        HandleAllocation(
            "versioned_registry_handle_4_parity_16",
            4,
            16,
            "32-bit versioned external registry handle with unique issuance, collision detection, reissue, and authenticated retained provenance.",
            "01234567",
        ),
    )


def evaluate_variant(trial_index: int, attacks: Iterable[AttackDefinition]) -> tuple[RegistryParityTrial, ...]:
    """Create one fresh shared cover and evaluate both fixed-codeword allocations under each crop attack."""

    cover_seed = 7100 + trial_index
    timeline_offset = _trial_offset_seconds(900 + trial_index)
    source = _cover_variant(30, cover_seed, timeline_offset)
    attack_values = tuple(attacks)
    return tuple(
        record
        for allocation in _handle_allocations()
        for record in _allocation_trials(allocation, source, cover_seed, timeline_offset, trial_index, attack_values)
    )


def run() -> dict[str, object]:
    """Run the fresh fixed-codeword fourteen-versus-sixteen-parity comparison without changing the carrier plan."""

    allocations = _handle_allocations()
    attacks = _crop_attacks()
    trials = tuple(record for trial_index in range(10) for record in evaluate_variant(trial_index, attacks))
    return {
        "fixture": "ten fresh seeded 30-second synthetic music-like covers and unchanged 250 ms crop attacks",
        "mapping_mode": "blind_non_oracle_fixed_codeword_sixteen_parity_registry_handle",
        "decoder_received_oracle_map": False,
        "alignment_policy": "blind_coarse_scan_plus_deterministic_center_phase",
        "registry_model": "32-bit compact handles require unique external issuance, collision checks, reissue, retained authenticated provenance, and namespace capacity analysis.",
        "allocations": [asdict(allocation) for allocation in allocations],
        "framing_overhead_bytes": 3,
        "carrier_band_hz": [500.0, 3800.0],
        "relative_difference": 0.95,
        "validation_cover_seeds": list(range(7100, 7110)),
        "summaries": [
            _summary(
                allocation,
                attack,
                tuple(
                    trial
                    for trial in trials
                    if trial.allocation_name == allocation.name and trial.attack_name == attack.name
                ),
            )
            for allocation in allocations
            for attack in attacks
        ],
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the complete reproducible sixteen-parity registry-handle comparison as formatted JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

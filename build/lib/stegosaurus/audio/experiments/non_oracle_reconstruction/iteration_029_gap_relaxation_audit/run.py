"""Run iteration 029: map bounded pilot-gap relaxations for one trailing abstention.

Goal: determine whether iteration 028 seed 7600's trailing abstention is
caused by conservative local carrier erasures rather than residual phase. The
audit keeps the same duration-feasible coarse bank and center phase, then
reconstructs with predeclared rival-pilot gaps from 0.24 down to 0.14.

This is calibration only. The expected handle and byte RS cost are post-hoc
labels, not decoder inputs. A later fresh-cover fallback study is required
before promoting any relaxed threshold.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json

from ....pilot import SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig
from ...transport_optimization.iteration_006_duration_stability_bounds.run import _cover_variant, _trial_offset_seconds
from ..iteration_005_contrastive_pilot_calibration.run import ContrastivePilotCalibratedExperiment
from ..iteration_006_pilot_threshold_sweep.run import PilotThresholds
from ..iteration_019_registry_handle_parity_tradeoff.run import _crop_attacks, _profile
from ..iteration_021_coarse_hypothesis_bank.run import _allocation, _measurement, CoarseHypothesisBankDecoder


GAPS = (0.24, 0.22, 0.20, 0.18, 0.16, 0.14)


@dataclass(frozen=True, slots=True)
class GapAuditRow:
    """Record one blind gap policy outcome and its post-hoc transport damage measurement."""

    pilot_gap_threshold: float
    hypothesis_count: int
    measurement: dict[str, object] | None


def run() -> dict[str, object]:
    """Evaluate the fixed gap grid against seed 7600's trailing crop without modifying the primary decoder."""

    allocation = _allocation()
    handle = allocation.handle()
    source = _cover_variant(30, 7600, _trial_offset_seconds(1500))
    configuration = SpectralPilotConfig(minimum_frequency_hz=500.0, maximum_frequency_hz=3800.0, relative_difference=0.95)
    watermark = AudioWatermarkConfig(attribution_token_bytes=4, parity_symbols=16)
    pilot = SpectralAudioPilot(b"audio-pilot-test-key", configuration, watermark)
    encoder = ContrastivePilotCalibratedExperiment(pilot, 0.01, _profile())
    embedding = encoder.embed(source, handle)
    attack = next(item for item in _crop_attacks() if item.name == "trailing_crop_025s")
    attacked = attack.transform(embedding.audio, 8000)
    rows: list[GapAuditRow] = []
    for gap in GAPS:
        decoder = CoarseHypothesisBankDecoder(encoder)
        decoder._coarse_decoder._payload_thresholds = PilotThresholds(0.0, gap)
        decision = decoder.reconstruct(attacked, embedding.carrier_plan)
        rows.append(GapAuditRow(
            gap, len(decision.hypotheses),
            _measurement(encoder, embedding, decision.selected.reconstruction, handle) if decision.selected else None,
        ))
    return {
        "goal": "post-hoc bounded local-pilot gap calibration for one prior trailing abstention",
        "decoder_received_oracle_map": False,
        "cover_seed": 7600,
        "attack": attack.name,
        "gaps": list(GAPS),
        "rows": [asdict(row) for row in rows],
    }


def main() -> None:
    """Print the machine-readable gap audit for archival redirection to ``RESULTS.json``."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

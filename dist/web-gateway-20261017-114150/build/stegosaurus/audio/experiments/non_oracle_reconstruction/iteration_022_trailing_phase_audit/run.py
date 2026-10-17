"""Run iteration 022: audit residual phases for iteration 021's sole trailing abstention.

Goal: determine whether a bounded sample-origin neighborhood could repair the
single trailing-crop seed that the duration-feasible coarse beam did not
decode. This is post-hoc calibration only: it uses the failed validation seed
and reports exact-handle equality solely as a measurement label. No output is
used by a blind decoder and no new robustness claim follows from one case.

Pipeline state: iteration 021 selected duration-feasible keyed coarse offsets
before local-map reconstruction, producing nine of ten trailing and all ten
leading recoveries within the 16-symbol RS budget. This audit retains its
4-byte/16-parity transport and local selection thresholds, then tests fixed
analysis-origin deltas around each eligible coarse offset.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json

from ....pilot import SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig
from ...transport_optimization.iteration_006_duration_stability_bounds.run import _cover_variant, _trial_offset_seconds
from ..iteration_005_contrastive_pilot_calibration.run import ContrastivePilotCalibratedExperiment
from ..iteration_019_registry_handle_parity_tradeoff.run import _crop_attacks, _profile
from ..iteration_021_coarse_hypothesis_bank.run import _allocation, _measurement, CoarseHypothesisBankDecoder


@dataclass(frozen=True, slots=True)
class PhaseAuditRow:
    """Record one blind offset/phase reconstruction and post-hoc byte damage for calibration."""

    offset_frames: int
    offset_rank: int
    pilot_evidence: float
    center_phase_samples: int
    phase_delta_samples: int
    phase_samples: int
    measurement: dict[str, object]


def run() -> dict[str, object]:
    """Map all bounded phase deltas around duration-feasible coarse offsets for trailing seed 7205."""

    allocation = _allocation()
    handle = allocation.handle()
    source = _cover_variant(30, 7205, _trial_offset_seconds(1105))
    configuration = SpectralPilotConfig(minimum_frequency_hz=500.0, maximum_frequency_hz=3800.0, relative_difference=0.95)
    watermark = AudioWatermarkConfig(attribution_token_bytes=4, parity_symbols=16)
    pilot = SpectralAudioPilot(b"audio-pilot-test-key", configuration, watermark)
    encoder = ContrastivePilotCalibratedExperiment(pilot, 0.01, _profile())
    decoder = CoarseHypothesisBankDecoder(encoder, bank_size=65)
    embedding = encoder.embed(source, handle)
    attack = next(item for item in _crop_attacks() if item.name == "trailing_crop_025s")
    attacked = attack.transform(embedding.audio, 7605)
    frequencies, spectrum = decoder._pilot._stft(attacked)
    lower_bin, upper_bin = decoder._pilot._frequency_bin_range(frequencies)
    nominal_frames = decoder._coarse_decoder._nominal_frame_count(attacked.sample_rate)
    coarse = decoder._coarse_decoder._select_offset(spectrum, embedding.carrier_plan, lower_bin, upper_bin, nominal_frames)
    offsets = decoder._banked_offsets(attacked, coarse)
    rows: list[PhaseAuditRow] = []
    for offset_rank, (offset, evidence, center) in enumerate(offsets, start=1):
        for delta in range(-16, 17, 4):
            phase = center + delta
            if not -decoder._pilot._config.hop_size < phase < decoder._pilot._config.hop_size:
                continue
            reframed = decoder._phase_helper._reframe_audio(attacked, phase)
            frequencies, reframed_spectrum = decoder._pilot._stft(reframed)
            lower_bin, upper_bin = decoder._pilot._frequency_bin_range(frequencies)
            reconstruction = decoder._coarse_decoder._reconstruct_at_offset(
                reframed_spectrum, embedding.carrier_plan, lower_bin, upper_bin, nominal_frames, offset
            )
            rows.append(PhaseAuditRow(offset, offset_rank, evidence, center, delta, phase, _measurement(encoder, embedding, reconstruction, handle)))
    return {
        "goal": "post-hoc calibration of residual phase choices for one prior trailing failure",
        "decoder_received_oracle_map": False,
        "cover_seed": 7205,
        "attack": attack.name,
        "phase_deltas": list(range(-16, 17, 4)),
        "duration_feasible_offset_count": len(offsets),
        "rows": [asdict(row) for row in rows],
    }


def main() -> None:
    """Print the machine-readable phase audit for archival redirection to ``RESULTS.json``."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

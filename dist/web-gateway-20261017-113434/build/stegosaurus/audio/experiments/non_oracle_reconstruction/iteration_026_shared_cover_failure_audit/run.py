"""Run iteration 026: audit the shared seed-7404 failure under both crop directions.

Goal: decide whether iteration 025's one shared-cover failure has any bounded
duration-feasible offset and residual phase whose post-hoc Reed--Solomon cost
falls within 16. The audit does not change a decoder or use a carrier map. It
only labels the generated blind reconstructions after the fact so the next
experiment can target synchronization or carrier reliability deliberately.

Pipeline state: iteration 025 retained the 4-byte/16-parity allocation and
duration-feasible top-three coarse beam, but seed 7404 emitted no RS-successful
candidate for either 250 ms crop. This script scans each feasible coarse offset
with `-32..+32` sample phase deltas in four-sample steps.
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
class AuditRow:
    """Record one blind offset/phase candidate and post-hoc byte-symbol transport damage."""

    attack_name: str
    offset_frames: int
    offset_rank: int
    pilot_evidence: float
    center_phase_samples: int
    phase_delta_samples: int
    measurement: dict[str, object]


def run() -> dict[str, object]:
    """Map all bounded residual phases around duration-feasible offsets for both seed-7404 crop transforms."""

    allocation = _allocation()
    handle = allocation.handle()
    source = _cover_variant(30, 7404, _trial_offset_seconds(1304))
    configuration = SpectralPilotConfig(minimum_frequency_hz=500.0, maximum_frequency_hz=3800.0, relative_difference=0.95)
    watermark = AudioWatermarkConfig(attribution_token_bytes=4, parity_symbols=16)
    pilot = SpectralAudioPilot(b"audio-pilot-test-key", configuration, watermark)
    encoder = ContrastivePilotCalibratedExperiment(pilot, 0.01, _profile())
    decoder = CoarseHypothesisBankDecoder(encoder, bank_size=65)
    embedding = encoder.embed(source, handle)
    rows: list[AuditRow] = []
    for attack in _crop_attacks():
        attacked = attack.transform(embedding.audio, 7804)
        frequencies, spectrum = decoder._pilot._stft(attacked)
        lower_bin, upper_bin = decoder._pilot._frequency_bin_range(frequencies)
        nominal_frames = decoder._coarse_decoder._nominal_frame_count(attacked.sample_rate)
        coarse = decoder._coarse_decoder._select_offset(spectrum, embedding.carrier_plan, lower_bin, upper_bin, nominal_frames)
        for offset_rank, (offset, evidence, center) in enumerate(decoder._banked_offsets(attacked, coarse), start=1):
            for delta in range(-32, 33, 4):
                phase = center + delta
                if not -decoder._pilot._config.hop_size < phase < decoder._pilot._config.hop_size:
                    continue
                reframed = decoder._phase_helper._reframe_audio(attacked, phase)
                frequencies, reframed_spectrum = decoder._pilot._stft(reframed)
                lower_bin, upper_bin = decoder._pilot._frequency_bin_range(frequencies)
                reconstruction = decoder._coarse_decoder._reconstruct_at_offset(
                    reframed_spectrum, embedding.carrier_plan, lower_bin, upper_bin, nominal_frames, offset
                )
                rows.append(AuditRow(attack.name, offset, offset_rank, evidence, center, delta, _measurement(encoder, embedding, reconstruction, handle)))
    return {
        "goal": "post-hoc bounded phase audit of iteration 025's shared-cover failure",
        "decoder_received_oracle_map": False,
        "cover_seed": 7404,
        "phase_deltas": list(range(-32, 33, 4)),
        "rows": [asdict(row) for row in rows],
    }


def main() -> None:
    """Print the complete machine-readable audit for archival redirection to ``RESULTS.json``."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

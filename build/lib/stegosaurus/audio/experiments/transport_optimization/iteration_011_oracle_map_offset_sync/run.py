"""Run iteration 011: sync-only oracle-map offset recovery for leading crops.

Experiment goal: recover the source-frame offset caused by a bounded leading
crop without using protected token data as the alignment signal. The scanner
tests candidate offsets against only the fixed framing sync bits, then decodes
all carrier bits at the winning frame offset.

Pipeline state: iteration 010 recovered the calibrated transport under several
mapping-preserving transformations but failed a 250 ms leading crop because it
used an unrealigned source map. This experiment retains source maps as oracle
side information and solves only a constant whole-frame offset; it does not
solve insertions, deletions, time scaling, or independent map reconstruction.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
import json
from statistics import median

import numpy as np

from ....attacks import trim_audio
from ....pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioAttributionResult, AudioWatermarkConfig
from ....transport import CarrierBit, CarrierPlan, BitFramer
from ..iteration_004_four_frame_soft_combine.run import (
    FourFrameEmbedding,
    FourFrameExtraction,
    FourFrameSoftCombineExperiment,
    _extraction_record,
)
from ..iteration_006_duration_stability_bounds.run import (
    _cover_variant,
    _trial_offset_seconds,
)
from ..iteration_009_calibrated_margin_selection.run import CalibratedMarginExperiment


@dataclass(frozen=True, slots=True)
class FrameOffsetAlignment:
    """Record the sync-only frame offset selected before token-bit extraction."""

    frame_offset: int
    observed_sync_bits: int
    matching_sync_bits: int
    signed_sync_margin: float
    sample_offset: int | None = None


@dataclass(frozen=True, slots=True)
class OffsetAlignedExtraction:
    """Pair a selected frame offset with full carrier and token recovery diagnostics."""

    alignment: FrameOffsetAlignment
    extraction: FourFrameExtraction

    @property
    def recovered(self) -> bool:
        """Return whether the decoded token exactly matches the known embedded token."""

        return self.extraction.recovered


class OffsetAlignedCalibratedMarginExperiment(CalibratedMarginExperiment):
    """Decode calibrated frame maps after a positive leading-crop offset scan over sync bits."""

    def extract_with_offset_scan(
        self,
        audio: PcmAudio,
        embedding: FourFrameEmbedding,
        maximum_offset_frames: int,
    ) -> OffsetAlignedExtraction:
        """Find a source-to-observed frame offset from sync evidence and recover all carrier bits."""

        if maximum_offset_frames < 0:
            raise ValueError("maximum_offset_frames must not be negative")
        frequencies, spectrum = self._pilot._stft(audio)
        lower_bin, upper_bin = self._pilot._frequency_bin_range(frequencies)
        coarse_alignment = self._select_offset(
            spectrum,
            embedding.carrier_plan,
            embedding.replica_frame_indices,
            lower_bin,
            upper_bin,
            maximum_offset_frames,
        )
        alignment, aligned_spectrum, lower_bin, upper_bin = self._select_sample_offset(
            audio,
            embedding.carrier_plan,
            embedding.replica_frame_indices,
            coarse_alignment,
        )
        extraction = self._extract_at_offset(
            aligned_spectrum,
            embedding,
            lower_bin,
            upper_bin,
            0,
        )
        return OffsetAlignedExtraction(alignment, extraction)

    def _select_offset(
        self,
        spectrum: np.ndarray,
        carrier_plan: CarrierPlan,
        replica_frame_indices: tuple[tuple[int, ...], ...],
        lower_bin: int,
        upper_bin: int,
        maximum_offset_frames: int,
    ) -> FrameOffsetAlignment:
        """Select the positive source-frame shift with the strongest known sync-bit agreement."""

        sync_positions = self._sync_positions(carrier_plan)
        candidates = tuple(
            self._alignment_for_offset(
                spectrum,
                carrier_plan.carrier_bits,
                replica_frame_indices,
                sync_positions,
                lower_bin,
                upper_bin,
                frame_offset,
            )
            for frame_offset in range(maximum_offset_frames + 1)
        )
        return max(
            candidates,
            key=lambda candidate: (
                candidate.matching_sync_bits,
                candidate.signed_sync_margin,
                candidate.observed_sync_bits,
                -candidate.frame_offset,
            ),
        )

    def _alignment_for_offset(
        self,
        spectrum: np.ndarray,
        carrier_bits: tuple[int, ...],
        replica_frame_indices: tuple[tuple[int, ...], ...],
        sync_positions: tuple[int, ...],
        lower_bin: int,
        upper_bin: int,
        frame_offset: int,
    ) -> FrameOffsetAlignment:
        """Score one candidate offset using only fixed synchronization carrier positions."""

        observed_sync_bits = 0
        matching_sync_bits = 0
        signed_sync_margin = 0.0
        for carrier_index in sync_positions:
            score = self._combined_score_at_offset(
                spectrum,
                replica_frame_indices,
                carrier_index,
                lower_bin,
                upper_bin,
                frame_offset,
            )
            if score is None:
                continue
            observed_sync_bits += 1
            expected_sign = 1.0 if carrier_bits[carrier_index] else -1.0
            signed_margin = expected_sign * score
            signed_sync_margin += signed_margin
            matching_sync_bits += int(signed_margin >= 0)
        return FrameOffsetAlignment(
            frame_offset,
            observed_sync_bits,
            matching_sync_bits,
            signed_sync_margin,
        )

    def _select_sample_offset(
        self,
        audio: PcmAudio,
        carrier_plan: CarrierPlan,
        replica_frame_indices: tuple[tuple[int, ...], ...],
        coarse_alignment: FrameOffsetAlignment,
    ) -> tuple[FrameOffsetAlignment, np.ndarray, int, int]:
        """Refine a whole-frame shift through a bounded sub-hop zero-prefix alignment scan."""

        hop_size = self._pilot._config.hop_size
        start_offset = max(0, (coarse_alignment.frame_offset - 1) * hop_size)
        stop_offset = (coarse_alignment.frame_offset + 1) * hop_size
        candidates: list[tuple[FrameOffsetAlignment, np.ndarray, int, int]] = []
        for sample_offset in range(start_offset, stop_offset + 1, 16):
            padded_audio = PcmAudio(
                np.pad(audio.samples, (sample_offset, 0)),
                audio.sample_rate,
            )
            frequencies, spectrum = self._pilot._stft(padded_audio)
            lower_bin, upper_bin = self._pilot._frequency_bin_range(frequencies)
            probe_alignment = self._alignment_for_offset(
                spectrum,
                carrier_plan.carrier_bits,
                replica_frame_indices,
                self._sync_positions(carrier_plan),
                lower_bin,
                upper_bin,
                0,
            )
            candidates.append(
                (
                    FrameOffsetAlignment(
                        coarse_alignment.frame_offset,
                        probe_alignment.observed_sync_bits,
                        probe_alignment.matching_sync_bits,
                        probe_alignment.signed_sync_margin,
                        sample_offset,
                    ),
                    spectrum,
                    lower_bin,
                    upper_bin,
                )
            )
        return max(
            candidates,
            key=lambda candidate: (
                candidate[0].matching_sync_bits,
                candidate[0].signed_sync_margin,
                candidate[0].observed_sync_bits,
                -int(candidate[0].sample_offset or 0),
            ),
        )

    def _extract_at_offset(
        self,
        spectrum: np.ndarray,
        embedding: FourFrameEmbedding,
        lower_bin: int,
        upper_bin: int,
        frame_offset: int,
    ) -> FourFrameExtraction:
        """Decode every carrier bit from observed frame indices shifted by one selected offset."""

        replica_scores = tuple(
            tuple(
                self._score_at_shifted_frame(
                    spectrum,
                    lower_bin,
                    upper_bin,
                    frame_index,
                    frame_offset,
                )
                for frame_index in frame_map
            )
            for frame_map in embedding.replica_frame_indices
        )
        combined_scores = tuple(
            self._combine_scores(copy_scores[carrier_index] for copy_scores in replica_scores)
            for carrier_index in range(len(embedding.carrier_plan.carrier_bits))
        )
        observed_bits = tuple(
            None if score is None or abs(score) < self._minimum_combined_confidence else int(score >= 0)
            for score in combined_scores
        )
        recovery = self._pilot.schema.recover_attribution(observed_bits)
        known_bit_errors = sum(
            observed_bit is not None and observed_bit != target_bit
            for target_bit, observed_bit in zip(embedding.carrier_plan.carrier_bits, observed_bits)
        )
        return FourFrameExtraction(
            replica_scores,
            combined_scores,
            observed_bits,
            known_bit_errors,
            sum(observed_bit is None for observed_bit in observed_bits),
            recovery,
            recovery.token == embedding.token,
        )

    def _combined_score_at_offset(
        self,
        spectrum: np.ndarray,
        replica_frame_indices: tuple[tuple[int, ...], ...],
        carrier_index: int,
        lower_bin: int,
        upper_bin: int,
        frame_offset: int,
    ) -> float | None:
        """Combine four shifted replica scores for one carrier index during synchronization scan."""

        return self._combine_scores(
            self._score_at_shifted_frame(
                spectrum,
                lower_bin,
                upper_bin,
                frame_map[carrier_index],
                frame_offset,
            )
            for frame_map in replica_frame_indices
        )

    def _score_at_shifted_frame(
        self,
        spectrum: np.ndarray,
        lower_bin: int,
        upper_bin: int,
        source_frame_index: int,
        frame_offset: int,
    ) -> float | None:
        """Read one score after translating a source map frame into its observed cropped index."""

        observed_frame_index = source_frame_index - frame_offset
        if observed_frame_index < 0 or observed_frame_index >= spectrum.shape[1]:
            return None
        score, _ = self._pilot._extract_frame_score(
            spectrum[:, observed_frame_index],
            lower_bin,
            upper_bin,
            source_frame_index,
        )
        return score

    @staticmethod
    def _sync_positions(carrier_plan: CarrierPlan) -> tuple[int, ...]:
        """Return framed carrier positions occupied by known synchronization bits only."""

        framer = BitFramer()
        data_bit_count = carrier_plan.codeword_length * 8
        positions: list[int] = []
        carrier_position = 0
        remaining_data_bits = data_bit_count
        while remaining_data_bits:
            positions.extend(range(carrier_position, carrier_position + len(framer.sync_pattern)))
            carrier_position += len(framer.sync_pattern) + min(
                framer.data_bits_per_frame,
                remaining_data_bits,
            )
            remaining_data_bits -= min(framer.data_bits_per_frame, remaining_data_bits)
        return tuple(positions)


@dataclass(frozen=True, slots=True)
class CropTrialRecord:
    """Record offset selection and exact token recovery for one leading-crop cover variant."""

    trial_index: int
    selected_offset_frames: int | None
    selected_sample_offset: int | None
    sync_matches: int | None
    observed_sync_bits: int | None
    embedding_snr_db: float | None
    measurement: Mapping[str, object] | None
    error: str | None


def evaluate_trial(trial_index: int) -> CropTrialRecord:
    """Embed one 30-second cover, apply a 250 ms leading crop, then synchronize and recover."""

    seed = 6100 + trial_index
    source = _cover_variant(30, seed, _trial_offset_seconds(trial_index))
    pilot = SpectralAudioPilot(
        b"audio-pilot-test-key",
        SpectralPilotConfig(relative_difference=0.95),
        AudioWatermarkConfig(parity_symbols=12),
    )
    experiment = OffsetAlignedCalibratedMarginExperiment(pilot, 0.01)
    try:
        embedding = experiment.embed(source, bytes.fromhex("0123456789abcdef"))
        cropped = trim_audio(embedding.audio, 0.25, embedding.audio.duration_seconds)
        aligned = experiment.extract_with_offset_scan(cropped, embedding, maximum_offset_frames=32)
        measurement = _extraction_record(experiment, embedding, aligned.extraction)
    except Exception as error:
        detail = str(error) or "no message"
        return CropTrialRecord(trial_index, None, None, None, None, None, None, f"{type(error).__name__}: {detail}")
    return CropTrialRecord(
        trial_index,
        aligned.alignment.frame_offset,
        aligned.alignment.sample_offset,
        aligned.alignment.matching_sync_bits,
        aligned.alignment.observed_sync_bits,
        embedding.signal_to_noise_db,
        measurement,
        None,
    )


def run() -> dict[str, object]:
    """Execute the bounded 250 ms leading-crop offset-recovery study over ten variants."""

    trials = tuple(evaluate_trial(trial_index) for trial_index in range(10))
    measurements = tuple(trial.measurement for trial in trials if trial.measurement is not None)
    offsets = tuple(trial.selected_offset_frames for trial in trials if trial.selected_offset_frames is not None)
    sample_offsets = tuple(trial.selected_sample_offset for trial in trials if trial.selected_sample_offset is not None)
    sync_matches = tuple(trial.sync_matches for trial in trials if trial.sync_matches is not None)
    return {
        "fixture": "ten seeded 30-second music-like cover variants and virtual timeline offsets",
        "attack": "leading_crop_025s",
        "mapping_mode": "sync_only_oracle_map_offset_scan",
        "maximum_offset_frames": 32,
        "trial_count": len(trials),
        "exact_recoveries": sum(measurement["token_matches_input"] for measurement in measurements),
        "median_rs_cost": median(int(measurement["rs_error_cost"]) for measurement in measurements) if measurements else None,
        "maximum_rs_cost": max(int(measurement["rs_error_cost"]) for measurement in measurements) if measurements else None,
        "selected_offsets": offsets,
        "selected_sample_offsets": sample_offsets,
        "median_sync_matches": median(sync_matches) if sync_matches else None,
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the complete reproducible leading-crop synchronization experiment as JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

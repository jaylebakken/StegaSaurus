"""Evaluate the detector pilot under named, reproducible audio transformations.

Pseudocode:
    source PCM -> embed once -> clean extraction
    each named attack -> transformed PCM or captured failure -> extraction record

``AudioPilotBenchmark`` deliberately preserves individual evidence rather than
collapsing it into a marketing-style robustness score. For stochastic studies,
``EntropicAttackProfile`` emits a fully recorded recipe so the same source,
parameters, child seeds, and codec environment can be replayed. Corpus design,
controls, and aggregate claims remain the caller's responsibility.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime

from .attacks import EntropicAttackProfile, EntropicAttackRecipe
from .pilot import PcmAudio, SpectralAudioPilot, SpectralPilotEmbedding, SpectralPilotExtraction


AudioAttack = Callable[[PcmAudio], PcmAudio]


@dataclass(frozen=True, slots=True)
class AudioAttackEvaluation:
    """Represent one transformed waveform, extraction result, or captured attack failure."""

    name: str
    duration_seconds: float | None
    extraction: SpectralPilotExtraction | None
    error: str | None
    recipe: EntropicAttackRecipe | None = None

    def __post_init__(self) -> None:
        """Require a non-empty name and exactly one extraction outcome or failure message."""

        if not self.name.strip():
            raise ValueError("attack names must not be empty")
        if (self.extraction is None) == (self.error is None):
            raise ValueError("an attack evaluation must contain exactly one outcome or error")

    @property
    def succeeded(self) -> bool:
        """Return whether this attack produced audio and a detector extraction result."""

        return self.extraction is not None


@dataclass(frozen=True, slots=True)
class AudioPilotBenchmarkResult:
    """Represent an embedding, clean baseline, and all named attack evaluations."""

    embedding: SpectralPilotEmbedding
    clean_extraction: SpectralPilotExtraction
    attacks: tuple[AudioAttackEvaluation, ...]

    @property
    def failures(self) -> tuple[AudioAttackEvaluation, ...]:
        """Return attack evaluations that failed without aborting the benchmark run."""

        return tuple(evaluation for evaluation in self.attacks if not evaluation.succeeded)


class AudioPilotBenchmark:
    """Run one spectral pilot embedding through a caller-defined set of audio attacks."""

    def __init__(self, pilot: SpectralAudioPilot) -> None:
        """Initialize the benchmark with the exact pilot configuration under evaluation."""

        self._pilot = pilot

    def evaluate(
        self,
        audio: PcmAudio,
        epoch: date | datetime | str,
        attacks: Mapping[str, AudioAttack],
    ) -> AudioPilotBenchmarkResult:
        """Embed audio once and retain an extraction or failure record for every named attack."""

        self._validate_attacks(attacks)
        embedding = self._pilot.embed(audio, epoch)
        clean_extraction = self._pilot.extract(embedding.audio, epoch)
        evaluations = tuple(
            self._evaluate_attack(name, attack, embedding.audio, epoch)
            for name, attack in attacks.items()
        )
        return AudioPilotBenchmarkResult(embedding, clean_extraction, evaluations)

    def evaluate_entropic(
        self,
        audio: PcmAudio,
        epoch: date | datetime | str,
        profile: EntropicAttackProfile,
        trial_count: int,
        seed: int,
    ) -> AudioPilotBenchmarkResult:
        """Evaluate replayable stochastic attack recipes sampled from one root seed."""

        if not isinstance(profile, EntropicAttackProfile):
            raise TypeError("profile must be an EntropicAttackProfile")
        recipes = profile.sample_many(audio.sample_rate, trial_count, seed)
        embedding = self._pilot.embed(audio, epoch)
        clean_extraction = self._pilot.extract(embedding.audio, epoch)
        evaluations = tuple(
            self._evaluate_attack(
                recipe.name,
                lambda attacked_audio, current_recipe=recipe: profile.apply(
                    attacked_audio,
                    current_recipe,
                ),
                embedding.audio,
                epoch,
                recipe,
            )
            for recipe in recipes
        )
        return AudioPilotBenchmarkResult(embedding, clean_extraction, evaluations)

    def _evaluate_attack(
        self,
        name: str,
        attack: AudioAttack,
        embedded_audio: PcmAudio,
        epoch: date | datetime | str,
        recipe: EntropicAttackRecipe | None = None,
    ) -> AudioAttackEvaluation:
        """Apply one validated attack and preserve a concise failure result if it cannot run."""

        try:
            attacked_audio = attack(embedded_audio)
            if not isinstance(attacked_audio, PcmAudio):
                raise TypeError("audio attacks must return PcmAudio")
            extraction = self._pilot.extract(attacked_audio, epoch)
        except Exception as error:
            detail = str(error) or "no message"
            return AudioAttackEvaluation(
                name,
                None,
                None,
                f"{type(error).__name__}: {detail}",
                recipe,
            )
        return AudioAttackEvaluation(name, attacked_audio.duration_seconds, extraction, None, recipe)

    @staticmethod
    def _validate_attacks(attacks: Mapping[str, AudioAttack]) -> None:
        """Reject malformed benchmark definitions before embedding audio or running attacks."""

        for name, attack in attacks.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("attack names must be non-empty strings")
            if not callable(attack):
                raise TypeError(f"attack {name!r} must be callable")

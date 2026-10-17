"""Encode and decode Saurus files with a small local registry sidecar.

This module keeps the new desktop app deliberately simple.  It wraps the
existing repeated-block attribution codec and serializes the retained private
record to JSON:

    source.wav + user registry fields
      -> encode handle across complete blocks
      -> write encoded.wav and encoded.saurus.json

    suspicious.wav + encoded.saurus.json
      -> restore retained block records
      -> verify the claimed handle
      -> return accepted / abstained diagnostics

The JSON sidecar is required because the current attribution design verifies a
claimed retained record.  It is not blind handle discovery and it is not a
production registry, key store, or robustness guarantee.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from stegosaurus.audio.attribution import BlockAttributionCodec, RepeatedBlockWaterfallPolicy
from stegosaurus.audio.pilot import PcmAudio, read_pcm16_wav, write_pcm16_wav

from .backend import LocalSidecarRegistryBackend, RegistryBackend, RegistryClaim, RegistryFields, RegistryReservation


LOCAL_DEMO_WATERMARK_SECRET = b"saurus-guided-desktop-app-local-demo-v1"
WATERMARK_SECRET_SCOPE = "local-demo-only"


@dataclass(frozen=True, slots=True)
class EncodeResult:
    """Summarize one guided encode job."""

    output_wav: Path
    registry_json: Path
    handle_hex: str
    block_count: int
    minimum_snr_db: float


@dataclass(frozen=True, slots=True)
class DecodeResult:
    """Summarize one guided decode job."""

    accepted: bool
    stage: str
    reason: str
    handle_hex: str
    recipient: str
    project: str
    block_votes: int
    block_count: int
    pooled_rs_cost: int


@dataclass(frozen=True, slots=True)
class FanoutDecodeResult:
    """Summarize a bounded local known-song fanout verification batch."""

    results: tuple[DecodeResult, ...]
    checked_claims: int
    elapsed_ms: float
    exceeded_time_budget: bool


@dataclass(frozen=True, slots=True)
class AttributionSummary:
    """Summarize retained registry attribution context for display."""

    project: str
    recipient: str
    notes: str
    handle_hex: str
    block_count: int


def encode_file(
    source_wav: Path,
    output_wav: Path,
    registry_json: Path,
    fields: RegistryFields,
    maximum_attempts: int = 32,
    backend: RegistryBackend | None = None,
) -> EncodeResult:
    """Encode one PCM16 WAV and write its private local registry JSON."""

    _validate_text(fields.project, "project")
    _validate_text(fields.recipient, "recipient")
    if isinstance(maximum_attempts, bool) or maximum_attempts < 1:
        raise ValueError("maximum_attempts must be a positive integer")
    source = read_pcm16_wav(source_wav)
    codec = BlockAttributionCodec(LOCAL_DEMO_WATERMARK_SECRET)
    policy = RepeatedBlockWaterfallPolicy()
    active_backend = backend or LocalSidecarRegistryBackend()
    active_backend.begin_encode(source_wav, output_wav, registry_json, fields)
    for attempt in range(maximum_attempts):
        reservation = active_backend.reserve(source_wav, source, fields, attempt)
        embedding = codec.embed(source, reservation.handle)
        if policy.decide(codec.verify(embedding.audio, embedding.record)).accepted:
            break
        active_backend.fail(reservation, "clean self-verification rejected embedded handle")
    else:
        raise RuntimeError("could not issue a cleanly verifiable registry handle")
    try:
        write_pcm16_wav(output_wav, embedding.audio)
        active_backend.finalize(source_wav, output_wav, registry_json, fields, embedding.record, reservation)
    except Exception:
        _fail_quietly(active_backend, reservation, "encode failed before registry finalization")
        raise
    return EncodeResult(
        output_wav,
        registry_json,
        reservation.handle.hex().upper(),
        len(embedding.record.block_records),
        min(embedding.block_signal_to_noise_db),
    )


def decode_file(received_wav: Path, registry_json: Path, backend: RegistryBackend | None = None) -> DecodeResult:
    """Verify one received WAV against the retained registry sidecar."""

    claim = (backend or LocalSidecarRegistryBackend()).load_claim(registry_json)
    return decode_claims(received_wav, (claim,))[0]


def inspect_registry_file(registry_json: Path, backend: RegistryBackend | None = None) -> AttributionSummary:
    """Load retained registry context without verifying a received audio file."""

    claim = (backend or LocalSidecarRegistryBackend()).load_claim(registry_json)
    return AttributionSummary(
        claim.fields.project,
        claim.fields.recipient,
        claim.fields.notes,
        claim.record.handle.hex().upper(),
        len(claim.record.block_records),
    )


def decode_claims(
    received_wav: Path,
    claims: tuple[RegistryClaim, ...],
    maximum_claims: int | None = None,
) -> tuple[DecodeResult, ...]:
    """Verify one received WAV against a bounded set of retained claims."""

    return decode_claims_measured(received_wav, claims, maximum_claims).results


def decode_claims_measured(
    received_wav: Path,
    claims: tuple[RegistryClaim, ...],
    maximum_claims: int | None = None,
    warning_threshold_ms: float | None = None,
    clock: Callable[[], float] = perf_counter,
) -> FanoutDecodeResult:
    """Verify retained claims and record local fanout timing diagnostics."""

    if not claims:
        raise ValueError("claims must not be empty")
    if maximum_claims is not None:
        if isinstance(maximum_claims, bool) or maximum_claims < 1:
            raise ValueError("maximum_claims must be a positive integer")
        claims = claims[:maximum_claims]
    if warning_threshold_ms is not None and (isinstance(warning_threshold_ms, bool) or warning_threshold_ms < 0):
        raise ValueError("warning_threshold_ms must be a non-negative number")
    started = clock()
    audio = read_pcm16_wav(received_wav)
    results = tuple(_decode_claim(audio, claim) for claim in claims)
    elapsed_ms = max(0.0, (clock() - started) * 1000)
    exceeded = warning_threshold_ms is not None and elapsed_ms > warning_threshold_ms
    return FanoutDecodeResult(results, len(claims), elapsed_ms, exceeded)


def _decode_claim(audio: PcmAudio, claim: RegistryClaim) -> DecodeResult:
    """Verify loaded PCM audio against one retained claim."""

    record = claim.record
    verification = BlockAttributionCodec(LOCAL_DEMO_WATERMARK_SECRET).verify(audio, record)
    decision = RepeatedBlockWaterfallPolicy().decide(verification)
    return DecodeResult(
        decision.accepted,
        decision.stage.value,
        decision.reason,
        record.handle.hex().upper(),
        claim.fields.recipient,
        claim.fields.project,
        decision.block_votes,
        decision.block_count,
        decision.pooled_rs_cost,
    )


def default_output_paths(source_wav: Path) -> tuple[Path, Path]:
    """Return friendly default output paths beside the selected source WAV."""

    output_wav = source_wav.with_name(f"{source_wav.stem}-saurus.wav")
    return output_wav, output_wav.with_suffix(".saurus.json")


def _validate_text(value: str, name: str) -> None:
    """Require visible registry text for fields the user must understand."""

    if not value.strip():
        raise ValueError(f"{name} must not be empty")


def _fail_quietly(backend: RegistryBackend, reservation: RegistryReservation, reason: str) -> None:
    """Best-effort cleanup that never hides the original encode failure."""

    try:
        backend.fail(reservation, reason)
    except Exception:
        return

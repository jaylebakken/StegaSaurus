"""Verify localized suspicious-excerpt windows against export records.

The fanout stage receives candidate windows from the shared song prefilter and
checks each recipient/export record using a small fine phase bank. Carrier
evidence is pooled per export and exports are ranked by acceptance and
Reed--Solomon cost.

This is the clean known-song V4 path. It intentionally uses retained export
records and does not discover unknown songs or unknown handles.
"""

from __future__ import annotations

from time import perf_counter

import numpy as np

from .fingerprints import _window
from .models import ExportAttributionResult, ExportRecord, LocalizationCandidate
from ..attribution import BlockAttributionCodec
from ..attribution_core.models import AttributionVerification
from ..pilot import PcmAudio


def verify_export_fanout(
    codec: BlockAttributionCodec,
    excerpt: PcmAudio,
    exports: tuple[ExportRecord, ...],
    candidates: tuple[LocalizationCandidate, ...],
    phase_radius_seconds: float = 0.30,
    phase_stride_seconds: float = 0.025,
    maximum_rs_cost: int = 16,
) -> tuple[tuple[ExportAttributionResult, ...], float]:
    """Verify all export records against localized candidates."""

    if not exports:
        raise ValueError("exports must not be empty")
    if not candidates:
        raise ValueError("candidates must not be empty")
    started = perf_counter()
    raw = tuple(
        _verify_export(codec, excerpt, export, candidates, phase_radius_seconds, phase_stride_seconds, maximum_rs_cost)
        for export in exports
    )
    ranked = _rank(raw)
    return ranked, (perf_counter() - started) * 1000.0


def _verify_export(
    codec: BlockAttributionCodec,
    excerpt: PcmAudio,
    export: ExportRecord,
    candidates: tuple[LocalizationCandidate, ...],
    phase_radius_seconds: float,
    phase_stride_seconds: float,
    maximum_rs_cost: int,
) -> ExportAttributionResult:
    """Pool candidate-window evidence for one export record."""

    verifications = []
    for candidate in candidates:
        block_index = candidate.registry_block_index
        if block_index >= len(export.attribution_record.block_records):
            continue
        phases = tuple(
            _verify_phase(codec, excerpt, export, block_index, candidate.crop_window_start_seconds + offset)
            for offset in np.arange(-phase_radius_seconds, phase_radius_seconds + 0.0001, phase_stride_seconds)
        )
        verifications.append(min(phases, key=lambda item: (item.claim_rs_cost, item.carrier_erasures, item.known_bit_errors)))
    pooled = _best_claim(codec, export.handle, tuple(verifications))
    accepted = pooled.claim_rs_cost <= maximum_rs_cost
    return ExportAttributionResult(export.export_id, export.recipient_label, accepted, pooled.claim_rs_cost, sum(item.recovered for item in verifications), 0)


def _verify_phase(
    codec: BlockAttributionCodec,
    excerpt: PcmAudio,
    export: ExportRecord,
    block_index: int,
    start_seconds: float,
) -> object:
    """Verify one fine phase candidate or return all-erasure evidence."""

    block_seconds = export.attribution_record.block_sample_count / export.attribution_record.sample_rate
    if start_seconds < 0 or start_seconds + block_seconds > excerpt.duration_seconds:
        return codec._unrecoverable(export.handle, "phase candidate outside excerpt")
    window = _window(excerpt, start_seconds, block_seconds)
    return codec._codec.verify(window, export.attribution_record.block_records[block_index])


def _best_claim(
    codec: BlockAttributionCodec,
    handle: bytes,
    verifications: tuple[AttributionVerification, ...],
) -> AttributionVerification:
    """Return the strongest pooled-or-single claim evidence."""

    pooled = codec._pool(handle, list(verifications))
    return min((pooled, *verifications), key=lambda item: (item.claim_rs_cost, item.carrier_erasures, item.known_bit_errors))


def _rank(results: tuple[ExportAttributionResult, ...]) -> tuple[ExportAttributionResult, ...]:
    """Rank export results by acceptance, RS cost, and label."""

    ordered = sorted(results, key=lambda item: (not item.accepted, item.pooled_rs_cost, item.recipient_label))
    return tuple(
        ExportAttributionResult(
            item.export_id,
            item.recipient_label,
            item.accepted,
            item.pooled_rs_cost,
            item.recovered_windows,
            rank,
        )
        for rank, item in enumerate(ordered, start=1)
    )

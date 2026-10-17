"""Run iteration 037: registry-only chain updates.

The experiment tests a safer custody-chain update policy after independent
audio stacking failed. Each event is encoded from the same clean source instead
of being encoded on top of its parent export.

Toy flow:
    create registry events with parent-child links
        -> encode each event from the clean master
        -> verify every retained event against each visible export
        -> require exactly one accepted visible event

This is a retained-record experiment. It does not claim arbitrary-crop recovery;
the cropped control is included to show where this policy still needs the V4
localization workflow.
"""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from ....attacks import add_reverberation, add_white_noise, low_pass_filter, normalize_peak, resample_audio, trim_audio
from ....attribution import BlockAttributionCodec
from ....pilot import PcmAudio, read_pcm16_wav
from .models import EventClaimEvidence, RegistryOnlyEvent, ScenarioOutcome


SAMPLES_DIR = Path("samples")
OUTPUT_PATH = Path(__file__).with_name("results.json")
TARGET_FILE = "10. Lovers Rock.wav"
BLOCK_SECONDS = 30.0
ACCEPT_RS_COST = 16


def _handle(index: int) -> bytes:
    """Return one deterministic registry-event handle."""

    return (0xF1000000 + index).to_bytes(4, "big")


def _events() -> tuple[RegistryOnlyEvent, ...]:
    """Return a small custody graph with a branch and unrelated control."""

    return (
        RegistryOnlyEvent("event_00_parent", None, _handle(0).hex(), "system", "initial private export", "registered from clean master"),
        RegistryOnlyEvent("event_01_child_a", "event_00_parent", _handle(1).hex(), "system", "downstream collaborator A", "derived in registry only"),
        RegistryOnlyEvent("event_02_child_b", "event_00_parent", _handle(2).hex(), "system", "downstream collaborator B", "derived in registry only"),
        RegistryOnlyEvent("event_03_grandchild", "event_01_child_a", _handle(3).hex(), "system", "second-hop collaborator", "derived in registry only"),
        RegistryOnlyEvent("event_99_unrelated", None, _handle(99).hex(), "control", "unrelated control", "not part of the custody chain"),
    )


def _light_proxy(audio: PcmAudio) -> PcmAudio:
    """Apply the light recorded-proxy transform used by recent suites."""

    transformed = resample_audio(resample_audio(audio, 12000), audio.sample_rate)
    transformed = low_pass_filter(transformed, 3800.0)
    transformed = add_reverberation(transformed, 0.080, 0.10, seed=20261011)
    transformed = add_white_noise(transformed, 35.0, seed=20261011)
    return normalize_peak(transformed, 0.85)


def _encoded_records(codec: BlockAttributionCodec, source: PcmAudio, events: tuple[RegistryOnlyEvent, ...]) -> dict[str, object]:
    """Encode every event independently from the clean source."""

    records = {}
    for event in events:
        embedding = codec.embed(source, bytes.fromhex(event.handle_hex), block_seconds=BLOCK_SECONDS)
        records[event.event_id] = embedding.record
    return records


def _visible_audio(codec: BlockAttributionCodec, source: PcmAudio, event: RegistryOnlyEvent | None, transform: str) -> PcmAudio:
    """Build the visible audio for one scenario."""

    audio = source if event is None else codec.embed(source, bytes.fromhex(event.handle_hex), block_seconds=BLOCK_SECONDS).audio
    if transform == "clean":
        return audio
    if transform == "peak_normalized":
        return normalize_peak(audio, 0.85)
    if transform == "light_recorded_proxy":
        return _light_proxy(audio)
    if transform == "leading_crop_30s":
        return trim_audio(audio, 30.0, audio.duration_seconds)
    raise ValueError(f"unsupported transform: {transform}")


def _evidence(codec: BlockAttributionCodec, audio: PcmAudio, events: tuple[RegistryOnlyEvent, ...], records: dict[str, object]) -> tuple[EventClaimEvidence, ...]:
    """Verify all retained event records against one visible audio sample."""

    evidence = []
    for event in events:
        verification = codec.verify(audio, records[event.event_id])
        pooled = verification.pooled_verification
        recovered = verification.recovered and pooled.claim_rs_cost <= ACCEPT_RS_COST
        evidence.append(
            EventClaimEvidence(
                event.event_id,
                event.parent_event_id,
                recovered,
                pooled.claim_rs_cost,
                verification.recovered_block_count,
                0,
            )
        )
    ordered = sorted(evidence, key=lambda item: (not item.recovered, item.pooled_rs_cost, item.event_id))
    return tuple(
        EventClaimEvidence(item.event_id, item.parent_event_id, item.recovered, item.pooled_rs_cost, item.block_votes, index + 1)
        for index, item in enumerate(ordered)
    )


def _outcome(scenario: str, visible_event_id: str | None, expected_event_id: str | None, evidence: tuple[EventClaimEvidence, ...]) -> ScenarioOutcome:
    """Classify one scenario from retained-event evidence."""

    accepted = tuple(item.event_id for item in evidence if item.recovered)
    unrelated_recovered = "event_99_unrelated" in accepted
    expected = () if expected_event_id is None else (expected_event_id,)
    sibling_or_parent = any(event_id not in expected and event_id != "event_99_unrelated" for event_id in accepted)
    if accepted == expected:
        status = "single_visible_event_recovered" if expected_event_id is not None else "no_event_recovered"
    elif unrelated_recovered:
        status = "misattribution_risk"
    elif len(accepted) > 1 or sibling_or_parent:
        status = "ambiguous_chain_visibility"
    elif not accepted and scenario.endswith("leading_crop_30s"):
        status = "geometry_failure"
    else:
        status = "visible_event_not_recovered"
    best = evidence[0] if evidence else None
    return ScenarioOutcome(
        scenario,
        visible_event_id,
        expected_event_id,
        accepted,
        sibling_or_parent,
        unrelated_recovered,
        None if best is None else best.event_id,
        None if best is None else best.pooled_rs_cost,
        status,
    )


def run(samples_dir: Path = SAMPLES_DIR) -> dict[str, object]:
    """Run the registry-only chain-update experiment."""

    source = read_pcm16_wav(samples_dir / TARGET_FILE)
    codec = BlockAttributionCodec(b"registry-only-chain-update")
    events = _events()
    event_map = {event.event_id: event for event in events}
    records = _encoded_records(codec, source, events)
    scenarios = (
        ("clean_source", None, None, "clean"),
        ("parent_visible_clean", "event_00_parent", "event_00_parent", "clean"),
        ("child_a_visible_clean", "event_01_child_a", "event_01_child_a", "clean"),
        ("grandchild_visible_clean", "event_03_grandchild", "event_03_grandchild", "clean"),
        ("child_a_peak_normalized", "event_01_child_a", "event_01_child_a", "peak_normalized"),
        ("child_a_light_recorded_proxy", "event_01_child_a", "event_01_child_a", "light_recorded_proxy"),
        ("child_a_leading_crop_30s", "event_01_child_a", "event_01_child_a", "leading_crop_30s"),
    )
    outcomes = []
    details = {}
    for scenario, visible_event_id, expected_event_id, transform in scenarios:
        event = None if visible_event_id is None else event_map[visible_event_id]
        audio = _visible_audio(codec, source, event, transform)
        scenario_evidence = _evidence(codec, audio, events, records)
        outcomes.append(_outcome(scenario, visible_event_id, expected_event_id, scenario_evidence))
        details[scenario] = [asdict(item) for item in scenario_evidence]
    manifest = {
        "goal": "validate one visible watermark with parent-child history maintained in registry only",
        "source_file": TARGET_FILE,
        "accept_rs_cost": ACCEPT_RS_COST,
        "block_seconds": BLOCK_SECONDS,
        "events": [asdict(event) for event in events],
        "outcomes": [asdict(outcome) for outcome in outcomes],
        "evidence": details,
        "recommendation": _recommendation(tuple(outcomes)),
    }
    OUTPUT_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def _recommendation(outcomes: tuple[ScenarioOutcome, ...]) -> str:
    """Return the design recommendation implied by the outcomes."""

    clean_outcomes = tuple(outcome for outcome in outcomes if "crop" not in outcome.scenario)
    if all(outcome.status in {"single_visible_event_recovered", "no_event_recovered"} for outcome in clean_outcomes):
        return "use registry-only chain updates: regenerate child exports from the clean master and store ancestry in the registry"
    return "do not promote registry-only chain updates until ambiguous visibility is resolved"


def main() -> None:
    """Print the registry-only chain-update manifest."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()


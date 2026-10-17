"""Run a scripted Saurus desktop smoke workflow.

This module exercises the product-shaped local registry path without opening
Tk: create a tiny WAV fixture, reserve and finalize through the local SQLite
registry, verify the selected recovery receipt, and inspect the attribution
summary. It is a release-check helper for the desktop workflow, not a robustness
benchmark, hosted deployment test, or public-web discovery claim.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from saurus_registry import HmacBearerAuthenticator, InMemoryRegistryRepository, RegistryApi, RegistryService
from stegosaurus.audio.demo_samples import music_like_sample
from stegosaurus.audio.pilot import write_pcm16_wav

from .backend import RegistryFields
from .credentials import DesktopCredentialManager, DeviceCredential, MemoryCredentialStore
from .local_registry import LocalRegistryConfig, local_registry_backend
from .remote_registry import ApiRegistryBackend
from .registry import decode_file, default_output_paths, encode_file, inspect_registry_file

__all__ = ["DesktopSmokeResult", "main", "run_alpha_contract_smoke", "run_local_registry_smoke"]


@dataclass(frozen=True, slots=True)
class DesktopSmokeResult:
    """Summarize one scripted local-registry desktop workflow."""

    workspace: Path
    source_wav: Path
    encoded_wav: Path
    registry_receipt: Path
    registry_database: Path
    handle_hex: str
    project: str
    recipient: str
    verification_event_id: str


def run_local_registry_smoke(workspace: Path) -> DesktopSmokeResult:
    """Run encode, decode, and attribution inspection against local SQLite."""

    root = workspace.expanduser()
    root.mkdir(parents=True, exist_ok=True)
    source_wav = root / "smoke-source.wav"
    registry_database = root / "smoke-registry.sqlite"
    write_pcm16_wav(source_wav, music_like_sample(30))
    encoded_wav, registry_receipt = default_output_paths(source_wav)
    backend = local_registry_backend(LocalRegistryConfig(registry_database))
    fields = RegistryFields("desktop smoke release", "alpha smoke recipient", "scripted release check")

    encoded = encode_file(source_wav, encoded_wav, registry_receipt, fields, backend=backend)
    restarted_backend = local_registry_backend(LocalRegistryConfig(registry_database))
    decoded = decode_file(encoded.output_wav, encoded.registry_json, backend=restarted_backend)
    if not decoded.accepted:
        raise RuntimeError(f"desktop smoke decode was not accepted: {decoded.reason}")
    event_id = restarted_backend.report_verification_result(encoded.registry_json, decoded)
    summary = inspect_registry_file(encoded.registry_json, backend=restarted_backend)
    if summary.handle_hex != encoded.handle_hex:
        raise RuntimeError("desktop smoke attribution handle does not match encoded handle")
    return DesktopSmokeResult(
        root,
        source_wav,
        encoded.output_wav,
        encoded.registry_json,
        registry_database,
        encoded.handle_hex,
        summary.project,
        summary.recipient,
        event_id,
    )


def run_alpha_contract_smoke(workspace: Path) -> DesktopSmokeResult:
    """Run the alpha device-credential registry contract without AWS."""

    root = workspace.expanduser()
    root.mkdir(parents=True, exist_ok=True)
    source_wav = root / "alpha-smoke-source.wav"
    write_pcm16_wav(source_wav, music_like_sample(30))
    encoded_wav, registry_receipt = default_output_paths(source_wav)
    repository = InMemoryRegistryRepository()
    service = RegistryService(repository, handle_factory=lambda: b"\x01\x02\x03\x04")
    tenant = service.register_tenant("Alpha Smoke Tenant", "ops-owner", "tenant-bootstrap")
    authenticator = HmacBearerAuthenticator(b"alpha-smoke-signing-secret")
    token = authenticator.issue_token(tenant.tenant_id, "alpha-device", ("registry.write", "registry.read", "registry.verify"))
    manager = DesktopCredentialManager(MemoryCredentialStore())
    credential = manager.enroll(DeviceCredential("local-alpha-contract", tenant.tenant_id, "alpha-device", token))
    backend = ApiRegistryBackend(
        RegistryApi(service, repository, authenticator=authenticator),
        credential.tenant_id,
        credential.actor_id,
        registry_url=credential.registry_url,
        authorization_token=credential.bearer_token,
    )
    fields = RegistryFields("alpha contract smoke", "alpha credential recipient", "token must not appear in output")

    encoded = encode_file(source_wav, encoded_wav, registry_receipt, fields, backend=backend)
    decoded = decode_file(encoded.output_wav, encoded.registry_json, backend=backend)
    if not decoded.accepted:
        raise RuntimeError(f"alpha smoke decode was not accepted: {decoded.reason}")
    event_id = backend.report_verification_result(encoded.registry_json, decoded)
    summary = inspect_registry_file(encoded.registry_json, backend=backend)
    if token in registry_receipt.read_text(encoding="utf-8"):
        raise RuntimeError("alpha smoke receipt contains bearer token")
    return DesktopSmokeResult(
        root,
        source_wav,
        encoded.output_wav,
        encoded.registry_json,
        root / "in-memory-registry",
        encoded.handle_hex,
        summary.project,
        summary.recipient,
        event_id,
    )


def main(argv: list[str] | None = None) -> int:
    """Run the smoke workflow and print a concise JSON result."""

    parser = argparse.ArgumentParser(description="Run the Saurus desktop local-registry smoke workflow.")
    parser.add_argument("--workspace", type=Path, help="Directory for smoke WAV, receipt, and registry files.")
    parser.add_argument("--mode", choices=("local-registry", "alpha-contract"), default="local-registry")
    args = parser.parse_args(argv)
    runner = run_alpha_contract_smoke if args.mode == "alpha-contract" else run_local_registry_smoke
    if args.workspace is None:
        with TemporaryDirectory(prefix="saurus-smoke-") as temporary:
            result = runner(Path(temporary))
            print(_result_json(result))
    else:
        result = runner(args.workspace)
        print(_result_json(result))
    return 0


def _result_json(result: DesktopSmokeResult) -> str:
    """Serialize one smoke result without private retained-record bytes."""

    return json.dumps(
        {
            "workspace": str(result.workspace),
            "source_wav": str(result.source_wav),
            "encoded_wav": str(result.encoded_wav),
            "registry_receipt": str(result.registry_receipt),
            "registry_database": str(result.registry_database),
            "handle_hex": result.handle_hex,
            "project": result.project,
            "recipient": result.recipient,
            "verification_event_id": result.verification_event_id,
        },
        indent=2,
        sort_keys=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())

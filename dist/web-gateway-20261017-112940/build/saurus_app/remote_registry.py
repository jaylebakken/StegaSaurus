"""Connect the desktop encode/decode workflow to a Saurus registry API.

The desktop still performs audio encoding and verification locally. This backend
uses the registry API only to reserve the handle, finalize the retained private
record, and later fetch one selected verification claim from a recovery receipt.
The receipt written beside the WAV contains server identities and digests, not
carrier maps or private block records.
"""

from __future__ import annotations

from base64 import b64decode, b64encode
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from saurus_registry import ApiRequest, RegistryApi
from saurus_registry.serialization import deserialize_block_record, serialize_block_record
from stegosaurus.audio.pilot import PcmAudio

from .backend import LocalSidecarRegistryBackend, RegistryClaim, RegistryFields, RegistryReservation
from .operation import desktop_operation_id
from .receipts import read_remote_receipt, write_remote_receipt
from .registry import DecodeResult


@dataclass(slots=True)
class ApiRegistryBackend:
    """Use a registry API router as the desktop registry backend."""

    api: RegistryApi
    tenant_id: str
    actor_id: str
    registry_url: str = "local-router"
    authorization_token: str | None = None
    song_id: str | None = None
    fingerprint_version: str = "desktop-clean-local-v1"
    operation_id: str | None = None
    request_counter: int = 0

    def begin_encode(
        self,
        source_wav: Path,
        output_wav: Path,
        registry_json: Path,
        fields: RegistryFields,
    ) -> None:
        """Name this encode so restarted retries reuse server idempotency keys."""

        self.operation_id = desktop_operation_id(self.tenant_id, source_wav, output_wav, registry_json, fields)

    def reserve(
        self,
        source_wav: Path,
        source_audio: PcmAudio,
        fields: RegistryFields,
        attempt: int,
    ) -> RegistryReservation:
        """Register or reuse the source song, then reserve a server handle."""

        song_id = self._ensure_song(source_wav, source_audio, fields)
        response = self._request(
            "POST",
            f"/v1/songs/{song_id}/exports:reserve",
            self._headers(f"reserve-{attempt}", mutating=True),
            {"recipient_label": fields.recipient.strip()},
        )
        export = response["export"]
        return RegistryReservation(bytes.fromhex(export["handle_hex"]), {"song_id": song_id, "export_id": export["export_id"]})

    def finalize(
        self,
        source_wav: Path,
        output_wav: Path,
        registry_json: Path,
        fields: RegistryFields,
        record,
        reservation: RegistryReservation,
    ) -> None:
        """Finalize the server export and write a private-record-free receipt."""

        payload = serialize_block_record(record)
        export_id = str(reservation.token["export_id"])
        response = self._request(
            "POST",
            f"/v1/exports/{export_id}:finalize",
            self._headers(f"finalize-{export_id}", mutating=True),
            {"payload_b64": b64encode(payload).decode("ascii")},
        )
        write_remote_receipt(
            registry_json,
            registry_url=self.registry_url,
            tenant_id=self.tenant_id,
            song_id=reservation.token["song_id"],
            export_id=export_id,
            record_digest=str(response["export"].get("record_digest", hashlib.sha256(payload).hexdigest())),
            output_wav=output_wav,
        )

    def fail(self, reservation: RegistryReservation, reason: str) -> None:
        """Mark one server reservation failed before it becomes active."""

        export_id = str(reservation.token["export_id"])
        self._request(
            "POST",
            f"/v1/exports/{export_id}:fail",
            self._headers(f"fail-{export_id}", mutating=True),
            {"reason": reason},
        )

    def load_claim(self, registry_json: Path) -> RegistryClaim:
        """Load one selected remote export claim from its recovery receipt."""

        receipt = read_remote_receipt(registry_json)
        export_id = str(receipt["export_id"])
        song_id = str(receipt["song_id"])
        export = self._request("GET", f"/v1/exports/{export_id}", self._headers("export", mutating=False), None)["export"]
        song = self._request("GET", f"/v1/songs/{song_id}", self._headers("song", mutating=False), None)["song"]
        stored = self._request(
            "GET",
            f"/v1/exports/{export_id}/verification-record",
            self._headers("record", mutating=False),
            None,
        )["record"]
        payload = b64decode(stored["payload_b64"], validate=True)
        fields = RegistryFields(str(song["title"]), str(export["recipient_label"]), "")
        return RegistryClaim(fields, deserialize_block_record(payload))

    def load_song_claims(self, song_id: str, limit: int = 10) -> tuple[RegistryClaim, ...]:
        """Load a bounded known-song verification bundle for local fanout checks."""

        response = self._request(
            "GET",
            f"/v1/songs/{song_id}/verification-bundle?limit={limit}",
            self._headers("song-bundle", mutating=False),
            None,
        )
        title = str(response["song"]["title"])
        records = {str(record["export_id"]): record for record in response["records"]}
        claims = []
        for export in response["exports"]:
            export_id = str(export["export_id"])
            payload = b64decode(str(records[export_id]["payload_b64"]), validate=True)
            claims.append(RegistryClaim(RegistryFields(title, str(export["recipient_label"]), ""), deserialize_block_record(payload)))
        return tuple(claims)

    def import_local_sidecar(
        self,
        source_wav: Path,
        output_wav: Path,
        local_registry_json: Path,
        receipt_json: Path,
        source_audio: PcmAudio,
    ) -> str:
        """Import one private local sidecar into the remote registry."""

        claim = LocalSidecarRegistryBackend().load_claim(local_registry_json)
        song_id = self._ensure_song(source_wav, source_audio, claim.fields)
        export = self._request(
            "POST",
            f"/v1/songs/{song_id}/exports:reserve",
            self._headers("import-reserve", mutating=True),
            {"recipient_label": claim.fields.recipient.strip(), "requested_handle_hex": claim.record.handle.hex()},
        )["export"]
        reservation = RegistryReservation(claim.record.handle, {"song_id": song_id, "export_id": export["export_id"]})
        self.finalize(source_wav, output_wav, receipt_json, claim.fields, claim.record, reservation)
        return str(export["export_id"])

    def export_local_sidecar(
        self,
        source_wav: Path,
        receipt_json: Path,
        local_registry_json: Path,
        output_wav: Path | None = None,
    ) -> None:
        """Export one remote recovery receipt into a private local sidecar."""

        receipt = read_remote_receipt(receipt_json)
        encoded_wav = output_wav or Path(str(receipt["encoded_wav"]))
        claim = self.load_claim(receipt_json)
        reservation = RegistryReservation(claim.record.handle, {})
        LocalSidecarRegistryBackend().finalize(source_wav, encoded_wav, local_registry_json, claim.fields, claim.record, reservation)

    def report_verification_result(self, receipt_json: Path, result: DecodeResult) -> str:
        """Post local verification diagnostics without uploading audio."""

        receipt = read_remote_receipt(receipt_json)
        response = self._request(
            "POST",
            f"/v1/exports/{receipt['export_id']}:verification-result",
            self._headers(f"verify-{receipt['export_id']}", mutating=True),
            {
                "accepted": result.accepted,
                "stage": result.stage,
                "reason": result.reason,
                "block_votes": result.block_votes,
                "block_count": result.block_count,
                "pooled_rs_cost": result.pooled_rs_cost,
            },
        )
        return str(response["event_id"])

    def _ensure_song(self, source_wav: Path, source_audio: PcmAudio, fields: RegistryFields) -> str:
        """Create the source song once for this backend instance."""

        if self.song_id is not None:
            return self.song_id
        response = self._request(
            "POST",
            "/v1/songs",
            self._headers("song", mutating=True),
            {
                "title": fields.project.strip(),
                "source_digest": f"sha256:{hashlib.sha256(source_wav.read_bytes()).hexdigest()}",
                "sample_rate": source_audio.sample_rate,
                "sample_count": len(source_audio.samples),
                "fingerprint_version": self.fingerprint_version,
            },
        )
        self.song_id = response["song"]["song_id"]
        return self.song_id

    def _headers(self, request_suffix: str, *, mutating: bool) -> dict[str, str]:
        """Build registry API identity headers for one desktop request."""

        headers = {"Authorization": self.authorization_token} if self.authorization_token else {"X-Saurus-Tenant": self.tenant_id, "X-Saurus-Actor": self.actor_id}
        if mutating:
            if self.operation_id is None:
                self.request_counter += 1
                headers["Idempotency-Key"] = f"desktop-{request_suffix}-{self.request_counter}"
            else:
                headers["Idempotency-Key"] = f"desktop-{self.operation_id}-{request_suffix}"
        else:
            headers["X-Request-ID"] = f"desktop-{request_suffix}"
        return headers

    def _request(self, method: str, path: str, headers: dict[str, str], body: dict[str, object] | None) -> dict[str, object]:
        """Send one HTTP-shaped request to the registry API router."""

        payload = b"" if body is None else json.dumps(body, sort_keys=True).encode("utf-8")
        response = self.api.handle(ApiRequest(method, path, headers, payload))
        document = json.loads(response.body.decode("utf-8"))
        if response.status >= 400:
            raise RuntimeError(document["error"]["message"])
        return document

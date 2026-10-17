"""Route versioned registry API requests into application services.

The router keeps HTTP concerns outside the audio and registry domain packages.
It requires tenant, actor, and idempotency headers for local development or a
signed bearer token when an authenticator is configured. Responses are
schema-versioned envelopes with stable JSON errors. Successful mutating
responses are stored for idempotent retry replay.
"""

from __future__ import annotations

from base64 import b64decode
from binascii import Error as Base64Error
from collections.abc import Callable
from datetime import datetime, timezone
import json
from typing import Any
from urllib.parse import parse_qs, urlsplit

from ..application import RegistryService
from ..repository import HandleConflictError, RegistryRepository
from .auth import RegistryAuthenticator, RequestContext, header_value, request_context
from .bundle import song_verification_bundle
from .contracts import ApiRequest, ApiResponse
from .idempotency import IdempotencyConflictError, InFlightIdempotencyGuard, replay_response, store_response
from .json_codec import export_document, record_document, song_document, time_text
from .verification import record_verification_event


API_SCHEMA_VERSION = 1


class RegistryApi:
    """Handle the concise `/v1` registry API surface."""

    def __init__(
        self,
        service: RegistryService,
        repository: RegistryRepository,
        *,
        authenticator: RegistryAuthenticator | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Bind the API adapter to application services and a response clock."""

        self._service = service
        self._repository = repository
        self._authenticator = authenticator
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._inflight = InFlightIdempotencyGuard()

    def handle(self, request: ApiRequest) -> ApiResponse:
        """Return one structured response for an HTTP-shaped request."""

        request_id = header_value(request.headers, "Idempotency-Key") or header_value(request.headers, "X-Request-ID") or ""
        try:
            return self._dispatch(request)
        except IdempotencyConflictError as error:
            return self._error(409, "conflict", str(error), request_id)
        except PermissionError as error:
            return self._error(403, "authorization", str(error), request_id)
        except HandleConflictError as error:
            return self._error(409, "conflict", str(error), request_id)
        except ValueError as error:
            status = 404 if "not registered" in str(error) else 400
            return self._error(status, "validation", str(error), request_id)
        except Base64Error as error:
            return self._error(400, "validation", f"invalid base64 payload: {error}", request_id)
        except KeyError as error:
            return self._error(400, "validation", f"missing field: {error.args[0]}", request_id)
        except json.JSONDecodeError as error:
            return self._error(400, "validation", f"invalid JSON: {error.msg}", request_id)

    def _dispatch(self, request: ApiRequest) -> ApiResponse:
        """Route one validated request by method and path segments."""

        segments = [part for part in urlsplit(request.path).path.split("/") if part]
        if len(segments) < 2 or segments[0] != "v1":
            return self._error(404, "not_found", "route is not registered", "")
        method = request.method.upper()
        if method == "POST" and segments == ["v1", "songs"]:
            return self._post_song(request)
        if method == "GET" and len(segments) == 3 and segments[1] == "songs":
            return self._get_song(request, segments[2])
        if method == "GET" and len(segments) == 4 and segments[1] == "songs" and segments[3] == "verification-bundle":
            return self._song_verification_bundle(request, segments[2])
        if method == "POST" and len(segments) == 4 and segments[1] == "songs" and segments[3] == "exports:reserve":
            return self._reserve_export(request, segments[2])
        if method == "GET" and len(segments) == 3 and segments[1] == "exports":
            return self._get_export(request, segments[2])
        if method == "GET" and len(segments) == 4 and segments[1] == "exports" and segments[3] == "verification-record":
            return self._verification_record(request, segments[2])
        if method == "GET" and len(segments) == 4 and segments[1] == "exports" and segments[3] == "lineage":
            return self._lineage(request, segments[2])
        if method == "POST" and len(segments) == 3 and segments[1] == "exports":
            return self._export_action(request, segments[2])
        return self._error(404, "not_found", "route is not registered", header_value(request.headers, "X-Request-ID") or "")

    def _post_song(self, request: ApiRequest) -> ApiResponse:
        """Create one source song record."""

        context = request_context(request, mutating=True, authenticator=self._authenticator, required_role="registry.write")
        return self._mutating(request, context, lambda: self._post_song_once(request, context))

    def _get_song(self, request: ApiRequest, song_id: str) -> ApiResponse:
        """Return one tenant-owned song record."""

        context = request_context(request, mutating=False, authenticator=self._authenticator, required_role="registry.read")
        song = self._repository.song(context.tenant_id, song_id)
        if song is None:
            raise ValueError("song_id is not registered for tenant")
        return self._ok(200, context.request_id, {"song": song_document(song)})

    def _song_verification_bundle(self, request: ApiRequest, song_id: str) -> ApiResponse:
        """Return a bounded verification bundle for one known song."""

        context = request_context(request, mutating=False, authenticator=self._authenticator, required_role="registry.verify")
        query = parse_qs(urlsplit(request.path).query)
        limit = int(query.get("limit", ["10"])[0])
        return self._ok(200, context.request_id, song_verification_bundle(self._service, self._repository, context, song_id, limit))

    def _reserve_export(self, request: ApiRequest, song_id: str) -> ApiResponse:
        """Reserve a random handle for one recipient export."""

        context = request_context(request, mutating=True, authenticator=self._authenticator, required_role="registry.write")
        return self._mutating(request, context, lambda: self._reserve_export_once(request, context, song_id))

    def _get_export(self, request: ApiRequest, export_id: str) -> ApiResponse:
        """Return one tenant-owned export record."""

        context = request_context(request, mutating=False, authenticator=self._authenticator, required_role="registry.read")
        return self._ok(200, context.request_id, {"export": export_document(self._service.resolve_export(context.tenant_id, export_id))})

    def _verification_record(self, request: ApiRequest, export_id: str) -> ApiResponse:
        """Return one retained private verification record."""

        context = request_context(request, mutating=False, authenticator=self._authenticator, required_role="registry.verify")
        record = self._service.verification_record(context.tenant_id, export_id)
        return self._ok(200, context.request_id, {"record": record_document(record)})

    def _lineage(self, request: ApiRequest, export_id: str) -> ApiResponse:
        """Return registry ancestry for one export."""

        context = request_context(request, mutating=False, authenticator=self._authenticator, required_role="registry.read")
        lineage = [export_document(export) for export in self._service.lineage(context.tenant_id, export_id)]
        return self._ok(200, context.request_id, {"lineage": lineage})

    def _export_action(self, request: ApiRequest, action_segment: str) -> ApiResponse:
        """Handle finalize, fail, and revoke export actions."""

        export_id, _, action = action_segment.partition(":")
        required_role = "registry.verify" if action == "verification-result" else "registry.write"
        context = request_context(request, mutating=True, authenticator=self._authenticator, required_role=required_role)
        return self._mutating(request, context, lambda: self._export_action_once(request, context, export_id, action))

    def _post_song_once(self, request: ApiRequest, context: RequestContext) -> ApiResponse:
        """Create one source song after idempotency guards are held."""

        body = _json_body(request)
        song = self._service.register_song(
            context.tenant_id,
            body["title"],
            body["source_digest"],
            int(body["sample_rate"]),
            int(body["sample_count"]),
            body["fingerprint_version"],
            context.actor_id,
            context.request_id,
        )
        return self._ok(201, context.request_id, {"song": song_document(song)})

    def _reserve_export_once(self, request: ApiRequest, context: RequestContext, song_id: str) -> ApiResponse:
        """Reserve one export after idempotency guards are held."""

        body = _json_body(request)
        export = self._service.reserve_export(
            context.tenant_id,
            song_id,
            body["recipient_label"],
            context.actor_id,
            context.request_id,
            body.get("parent_export_id"),
            bytes.fromhex(body["requested_handle_hex"]) if "requested_handle_hex" in body else None,
        )
        return self._ok(201, context.request_id, {"export": export_document(export)})

    def _export_action_once(self, request: ApiRequest, context: RequestContext, export_id: str, action: str) -> ApiResponse:
        """Apply one export action after idempotency guards are held."""

        body = _json_body(request)
        if action == "finalize":
            payload = b64decode(body["payload_b64"], validate=True)
            export = self._service.finalize_export(context.tenant_id, export_id, payload, context.actor_id, context.request_id)
        elif action == "fail":
            export = self._service.fail_export(context.tenant_id, export_id, body["reason"], context.actor_id, context.request_id)
        elif action == "revoke":
            export = self._service.revoke_export(context.tenant_id, export_id, context.actor_id, context.request_id)
        elif action == "verification-result":
            event = record_verification_event(self._service, self._repository, context, export_id, body, self._clock)
            return self._ok(202, context.request_id, {"event_id": event.event_id})
        else:
            return self._error(404, "not_found", "route is not registered", context.request_id)
        return self._ok(200, context.request_id, {"export": export_document(export)})

    def _mutating(self, request: ApiRequest, context: RequestContext, handler: Callable[[], ApiResponse]) -> ApiResponse:
        """Replay, guard, dispatch, and store one mutating response."""
        if (replay := replay_response(self._repository, context, request)) is not None:
            return replay
        with self._inflight.track(context, request):
            if (replay := replay_response(self._repository, context, request)) is not None:
                return replay
            response = handler()
        store_response(self._repository, context, request, response, self._clock)
        return response

    def _ok(self, status: int, request_id: str, data: dict[str, Any]) -> ApiResponse:
        """Build one schema-versioned JSON success response."""

        body = {"schema_version": API_SCHEMA_VERSION, "request_id": request_id, "server_utc": time_text(self._clock())}
        body.update(data)
        return _response(status, body)

    def _error(self, status: int, code: str, message: str, request_id: str) -> ApiResponse:
        """Build one schema-versioned JSON error response."""

        return _response(
            status,
            {
                "schema_version": API_SCHEMA_VERSION,
                "request_id": request_id,
                "server_utc": time_text(self._clock()),
                "error": {"code": code, "message": message},
            },
        )


def _json_body(request: ApiRequest) -> dict[str, Any]:
    """Decode one JSON object request body."""

    value = json.loads(request.body.decode("utf-8") or "{}")
    if not isinstance(value, dict):
        raise ValueError("request body must be a JSON object")
    return value


def _response(status: int, body: dict[str, Any]) -> ApiResponse:
    """Encode a JSON API response."""

    return ApiResponse(status, {"Content-Type": "application/json"}, json.dumps(body, sort_keys=True).encode("utf-8"))

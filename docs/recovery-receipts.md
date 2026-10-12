# Saurus Recovery Receipt and Audit Field Contract

This note fixes the first server-backed desktop recovery contract. A recovery
receipt is the small JSON file written beside an encoded WAV when the desktop
uses a remote registry backend. It helps a user or support operator find the
server-side export later, but it must not become a second private sidecar.

## Recovery Receipt Fields

Remote desktop receipts must contain only operational routing and integrity
fields:

- `version`: receipt schema version.
- `backend`: backend family, currently `saurus-registry-api-v1`.
- `created_utc`: desktop receipt creation time.
- `registry_url`: user-visible registry route or service identity.
- `tenant_id`: tenant boundary for the export.
- `song_id`: registered source song identity.
- `export_id`: recipient export identity.
- `record_digest`: digest of the retained private attribution record stored by
  the registry.
- `encoded_wav`: local path recorded for operator convenience.

Receipts must not contain recipient notes, private block records, carrier maps,
watermark secrets, access tokens, or arbitrary registry search material. The
desktop may expand a remote receipt into a private local sidecar only through an
explicit disaster-recovery export action.

## Audit Event Fields

Registry audit events must keep enough context to reconstruct system actions
without storing private payloads directly:

- `event_id`: immutable event identity.
- `tenant_id`: authorization boundary.
- `actor_id`: authenticated user, device, service, or system actor.
- `action`: event verb such as `export.finalized`.
- `object_id`: primary object affected by the event.
- `request_id`: API request or idempotency key that caused the event.
- `occurred_utc`: server event time.
- `detail_digest`: digest of canonical detail fields.

Audit detail digests are not evidence reports by themselves. They prove a
registry event recorded a stable detail document, while authorized reads of the
underlying records remain controlled by the registry service.

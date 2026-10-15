# Distributed Idempotency And Locking Design

**Status:** Production hosting design baseline  
**Reviewed:** 2026-10-12  
**Scope:** Multi-instance registry API deployments. Local desktop sidecar mode
and single-process local registry mode are out of scope.

The current registry API already stores successful mutating responses and has
an in-process duplicate-request guard. A hosted alpha with more than one
container also needs a database-backed claim on each mutating request so two
instances cannot reserve or finalize the same idempotency key concurrently.

## Goals

- Preserve desktop retry safety across process restarts and multiple registry
  containers.
- Replay successful mutating responses for the same tenant and idempotency key.
- Reject idempotency-key reuse with different request content.
- Return a retryable conflict while the original mutation is still in flight.
- Keep tenant isolation at the storage boundary.

## Request Identity

Every mutating request must have:

- tenant ID from signed auth context
- actor/device ID from signed auth context
- idempotency key
- canonical method, path, and request-body digest
- request start timestamp

The durable key is `(tenant_id, idempotency_key)`. The request digest prevents a
client from reusing a key for different content.

## Table Shape

```text
registry_idempotency_locks
  tenant_id text not null
  request_id text not null
  request_digest text not null
  status text not null  -- in_flight | completed | failed
  response_status integer
  response_headers json/text
  response_body bytes/text
  actor_id text not null
  claimed_at timestamp not null
  expires_at timestamp not null
  completed_at timestamp
  primary key (tenant_id, request_id)
```

Use the same database transaction boundary as the mutation whenever possible.
If the claim row exists:

- matching digest + completed: replay stored response
- matching digest + in_flight and not expired: return conflict/retry later
- matching digest + in_flight and expired: allow a recovery path only after
  reconciliation confirms no durable mutation completed
- different digest: reject as idempotency conflict

## Mutation Flow

1. Authenticate request and compute canonical request digest.
2. Open transaction.
3. Insert `in_flight` claim row for `(tenant_id, idempotency_key)`.
4. If insert conflicts, apply the existing replay/conflict rules.
5. Execute the registry mutation.
6. Store successful response in the claim row as `completed`.
7. Commit transaction.
8. Return stored response.

If the process dies after mutation but before response storage, reconciliation
must inspect domain state by operation identity before retrying or failing the
reservation. Desktop stable operation IDs reduce the chance of duplicate active
exports, but production should not rely on the desktop alone.

## Expiry And Reconciliation

- In-flight claim expiry should be longer than the maximum expected mutation
  duration.
- Expired in-flight claims are not automatically safe to delete.
- A scheduled reconciliation job should inspect stale claims, related export
  reservations, and audit events, then mark the claim failed or completed with
  explicit evidence.
- Reconciliation events must be audit-only and must not copy retained records,
  bearer tokens, source audio, carrier maps, or notes.

## Alpha Acceptance Checks

- Two concurrent requests with the same tenant/key/body produce one mutation and
  one conflict/replay path.
- Reusing the same key with a different body is rejected.
- A completed response replays across process restart.
- Cross-tenant reuse of the same key is isolated.
- Stale in-flight claims are visible to operator health or launch-gate review.

## Open Implementation Work

- Add PostgreSQL-backed lock/replay repository methods.
- Decide exact in-flight expiry.
- Add migration for lock table.
- Add multi-process or database-level concurrency tests.
- Add stale lock reconciliation job and launch metric.

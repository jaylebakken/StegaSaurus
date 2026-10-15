# Saurus Operations Runbooks

**Status:** Alpha operations draft  
**Reviewed:** 2026-10-12  
**Scope:** Registry-backed desktop alpha, local registry rehearsal, and future
hosted registry/discovery operations.

These runbooks are intentionally conservative. They preserve source audio
locality, avoid accusation language, and keep discovery separate from private
registry data. They are not a replacement for external security review,
counsel-approved retention policy, or production cloud incident tooling.
Executable production-readiness drill records live in
`src/saurus_pilot/incident_response.py`; they require contain, assess, recover,
communicate, and review phases before a drill can count as complete.

## Severity Guide

| Severity | Use when | Response target |
| --- | --- | --- |
| S1 | Key material, bearer tokens, retained records, or tenant data may be exposed | Immediate containment |
| S2 | Registry mutations, verification events, or discovery alerts may be wrong | Same business day |
| S3 | Local alpha workflow is degraded but private data is not exposed | Next working session |

## Registry Credential Exposure

Trigger this runbook if a bearer token, signing key, desktop credential, KMS
grant path, database credential, or registry admin credential is exposed or
suspected to be exposed.

### Contain

- [ ] Stop issuing new encode grants for affected tenant, actor, or device.
- [ ] Disable or rotate affected bearer/signing/database credentials.
- [ ] Disable affected desktop device enrollment if device identity is known.
- [ ] Preserve audit logs, registry database, recovery receipts, and deployment
  configuration before cleanup.
- [ ] Confirm no source audio was uploaded or copied as part of response.

### Assess

- [ ] Identify affected tenant IDs, actor IDs, device IDs, request IDs, and time
  window.
- [ ] Review registry events for `song.registered`, `export.reserved`,
  `export.finalized`, `export.failed`, `export.revoked`, and
  `verification.reported`.
- [ ] Check for cross-tenant access attempts, unusual verification-record reads,
  unusual grant issuance, and unusually high reserve/finalize volume.
- [ ] Classify exposed material: bearer token, desktop device secret, signing
  key, database credential, retained record, KMS grant, or root key.

### Recover

- [ ] Rotate affected credentials or keys.
- [ ] Rehearse retained-record key rotation if record-encryption material may
  be affected.
- [ ] Revoke or fail suspicious reserved exports; do not delete audit history.
- [ ] Restore from backup only if registry integrity is suspect, then reconcile
  reservations before allowing encode work.
- [ ] Re-enable encode grants only after a second reviewer verifies containment.

### Communicate

- [ ] Use evidence language from `docs/evidence-language.md`.
- [ ] State affected systems and time window without speculating about recipient
  fault.
- [ ] Do not claim source-audio exposure unless logs or artifacts prove it.
- [ ] Record owner, reviewer, timestamps, affected IDs, actions, and residual
  risk.

## Mistaken Discovery Alert Or External Notice

Trigger this runbook if a discovery candidate, client alert, attribution
handoff, or external notice may have been wrong, premature, or worded too
strongly.

### Contain

- [ ] Pause client notifications and external notices for the affected tenant.
- [ ] Disable the affected connector or source if the issue may repeat.
- [ ] Preserve candidate records, review actions, source metrics, evidence
  class, and notification text.
- [ ] Do not run new attribution handoffs from the same candidate set until the
  review is complete.

### Assess

- [ ] Determine whether the issue is song recognition, watermark verification,
  review workflow, language, source policy, duplicate handling, or retention.
- [ ] Confirm whether the candidate was `song match only` or attribution
  eligible.
- [ ] Re-check the evidence against the current approved wording.
- [ ] Verify that no recipient label was copied into discovery as evidence.
- [ ] Identify every client, reviewer, counsel reviewer, and external party who
  saw the alert or notice.

### Recover

- [ ] Correct or withdraw the alert using neutral wording.
- [ ] Suppress or relabel affected candidates.
- [ ] Update connector policy, thresholds, evidence-class handling, or review
  gates before resuming notifications.
- [ ] Add the case to the pilot corpus as a negative, duplicate, unusable, or
  wording-failure example.

### Communicate

- [ ] Separate system facts, user labels, song candidates, watermark matches,
  rejected claims, and abstentions.
- [ ] Avoid phrases that imply certainty, recipient fault, or legal conclusion.
- [ ] Record the correction, reviewer, counsel reviewer, client approval, and
  follow-up control.

## Local Registry Health Check

Use the desktop `Health` action or the local registry health helper before an
alpha demo, after a failed encode, and before copying a local registry database.

- [ ] Confirm tenant readiness.
- [ ] Confirm schema version is present.
- [ ] Confirm active, reserved, failed, and revoked export counts look expected.
- [ ] Confirm audit-event count increases after encode and verification.
- [ ] Confirm database path and size are expected for the environment.
- [ ] If reserved exports remain after interruption, run reconciliation before
  relying on the registry for a demo.

## Encode Grant Disablement

Use this runbook when one tenant, device, actor, grant path, or KMS key version
should stop issuing new desktop encode grants. This disables future encode
capability without deleting audit history or changing the meaning of already
finalized registry records.

### Contain

- [ ] Identify affected tenant IDs, device IDs, actor IDs, song IDs, export IDs,
  request IDs, grant IDs, root key IDs, and time window.
- [ ] Disable new grant issuance for the narrowest safe scope first: device,
  actor, tenant, then global grant path.
- [ ] Disable affected device enrollment or bearer credential if device or actor
  identity is known.
- [ ] Preserve grant audit records, registry events, deployment configuration,
  and recovery receipts before cleanup.
- [ ] Confirm source audio stays local and is not requested for incident review.

### Assess

- [ ] Review grant audit records for unusual request IDs, expiry windows,
  devices, actors, root key IDs, and encode volume.
- [ ] Compare grant issuance against `export.reserved`, `export.finalized`,
  `export.failed`, and `export.revoked` events.
- [ ] Identify active reserved exports that may have received a grant but never
  finalized.
- [ ] Decide whether affected reserved exports should be failed, expired, or
  left pending for user retry after re-enrollment.

### Recover

- [ ] Rotate affected desktop device secret or bearer credential before
  re-enabling that device.
- [ ] Issue a new root key alias or key version if grant wrapping material may
  be affected.
- [ ] Re-enable grant issuance only after a second reviewer confirms the scope,
  audit preservation, and retry policy.
- [ ] Run a reserve, grant, encode, finalize, selected-claim decode, and
  verification-report smoke workflow after re-enable.

### Communicate

- [ ] Say grant issuance was paused, disabled, or rotated; do not imply source
  audio exposure unless there is direct evidence.
- [ ] Record operator, reviewer, affected IDs, start/end times, re-enable
  decision, and residual risk.

## Key Rotation And Old Export Verification

Use this runbook for retained-record key rotation or encode-grant key hierarchy
changes. The goal is to prove new work uses the new key path while old exports
remain verifiable under their recorded key metadata.
Production-shaped drill evidence is recorded with
`src/saurus_pilot/recovery_drills.py`; a local SQLite rehearsal alone does not
pass the production launch gate.

### Prepare

- [ ] Identify current key IDs, aliases, versions, cipher metadata, and affected
  tenants.
- [ ] Back up the registry database and record backup ID before rotation.
- [ ] Freeze or narrow new grant issuance while key metadata is changing.
- [ ] Record expected sample exports that must verify before and after rotation.

### Rotate

- [ ] Add the new key version or alias before disabling the old one.
- [ ] Re-envelope retained registry records when rotating record-encryption
  material; keep old verification metadata available.
- [ ] Route new encode grants to the new key path and preserve grant audit
  records for both old and new root key IDs.
- [ ] Keep old key versions decrypt-only or verify-only until historical export
  verification has passed.

### Verify

- [ ] Verify selected old exports still decode to the expected retained claims.
- [ ] Verify a new export receives a new grant/root key ID and finalizes
  successfully.
- [ ] Run registry launch-gate metrics, access-review probes, and backup/restore
  rehearsal after rotation.
- [ ] Record old key ID, new key ID, sample export IDs, smoke-test result,
  operator, reviewer, and rollback decision.

### Roll Back Or Close

- [ ] If old exports fail verification, stop new grants and restore from the
  pre-rotation backup or re-enable the previous key path.
- [ ] If checks pass, keep old key material only for the approved retention
  window and update the key inventory.

## Production Database Migration Workflow

Use this workflow for the managed PostgreSQL alpha and later production-shaped
registry databases. The schema SQL is rendered by
`saurus_registry.render_postgres_migration_plan`; applying it still requires an
approved deployment window and a fresh backup.

- [ ] Back up the database before migration.
- [ ] Record schema version before migration:
  `psql "$SAURUS_DATABASE_URL" -v ON_ERROR_STOP=1 -c "SELECT COALESCE(MAX(version), 0) FROM schema_migrations;"`
- [ ] Apply migrations in a staging or restored copy first.
- [ ] Render the reviewed SQL artifact:
  `python -c "from saurus_registry import render_postgres_migration_plan; print(render_postgres_migration_plan())" > registry-postgres-migrations.sql`
- [ ] Apply the reviewed SQL to staging first:
  `psql "$SAURUS_STAGING_DATABASE_URL" -v ON_ERROR_STOP=1 -f registry-postgres-migrations.sql`
- [ ] Apply the same reviewed SQL to alpha only after staging smoke passes:
  `psql "$SAURUS_DATABASE_URL" -v ON_ERROR_STOP=1 -f registry-postgres-migrations.sql`
- [ ] Run reserve/finalize/decode/report smoke workflow after migration.
- [ ] Run tenant-isolation and access-review probes after migration.
- [ ] Record schema version after migration:
  `psql "$SAURUS_DATABASE_URL" -v ON_ERROR_STOP=1 -c "SELECT MAX(version) FROM schema_migrations;"`
- [ ] Record schema version, backup ID, operator, reviewer, start time, end
  time, and rollback decision.
- [ ] Keep rollback path available until smoke and access checks pass.
- [ ] Roll back by restoring the pre-migration backup into a fresh database and
  pointing the service at the restored endpoint; do not run destructive
  down-migrations against the only live registry copy.

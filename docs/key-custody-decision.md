# Saurus Key Custody Decision

**Status:** Provider and hierarchy selected for AWS alpha and first production
shape  
**Reviewed:** 2026-10-12  
**Scope:** Registry-backed desktop encoding, retained registry records, signed
reports, and operational secrets. This document does not implement the managed
KMS grant provider.

## Decision

Use **AWS KMS customer-managed symmetric keys** as the first managed key custody
provider. Keep source audio local by default: the registry service owns tenant
and root watermark material, then issues short-lived, export-scoped desktop
working key grants. The local HMAC grant code remains a development contract,
not production cryptography.

AWS CloudHSM is deferred unless a paying pilot or security review requires
single-tenant HSM custody, custom key stores, or customer-held key ceremonies.

## Key Hierarchy

| Key path | Purpose | Alias pattern | Rotation posture |
| --- | --- | --- | --- |
| Registry record key | Envelope encryption for retained attribution payloads and recovery-support artifacts | `alias/saurus/{env}/registry-records` | Rotate on schedule and after exposure; old versions remain decrypt-only until historical export verification is proven. |
| Encode grant root key | Wrap or derive export-scoped desktop working grants | `alias/saurus/{env}/encode-grants` | Rotate with grant disablement runbook; new grants move to the new key path while old grants expire. |
| Report signing key | Sign verification reports and copy-review-safe evidence summaries | `alias/saurus/{env}/reports` | Rotate with signature key IDs preserved so old reports remain verifiable. |
| Backup/support key | Encrypt database backup exports, restore artifacts, and digest-only support bundles | `alias/saurus/{env}/backups` | Rotate independently from encode grants so recovery does not change active encoding behavior. |

Alpha can deploy one physical KMS key while exposing these alias paths only if
cost or operational simplicity demands it. Production should split the key paths
before external customers rely on the service.

## Grant Flow

1. Desktop authenticates with an enrolled device credential.
2. Registry reserves a tenant-scoped export and records request identity.
3. Registry service asks the managed grant provider for a short-lived working
   grant scoped by tenant, song, export, device, actor, profile, request, and
   expiry.
4. Desktop unwraps only the export-scoped working material needed for local
   encoding.
5. Registry records a grant audit projection without plaintext working keys,
   source audio, carrier maps, bearer tokens, or recipient notes.
6. Grant expiry, disablement, and key rotation preserve historical verification
   metadata without issuing new work on disabled paths.

## Access Boundaries

- Desktop builds never contain tenant/root watermark material.
- Registry task role can call only the KMS aliases required by its environment.
- Discovery workers receive no KMS permissions for private registry records,
  encode grants, or report signing.
- Database and backup stores retain ciphertext, key IDs, digests, and audit
  metadata, not plaintext retained records or key material.
- Break-glass administrative use must be recorded as an audit event and reviewed
  during access review.

## Open Implementation Gates

- Wire `AwsKmsEncodeGrantProvider` to the deployed AWS KMS client and task-role
  IAM policy. Live grant evidence is recorded with
  `src/saurus_pilot/kms_live.py`; production readiness requires the
  encode-grants alias path, AWS KMS data-key grant algorithm, scoped context
  digest, IAM policy reference, CloudTrail evidence, grant audit reference, and
  smoke-test reference.
- Persist production grant audit records with tenant, song, export, device,
  actor, profile, request, expiry, root key ID, and context digest.
- Rehearse backup restore and retained-record key rotation against the intended
  alpha database. Production-shaped drill evidence is recorded by
  `src/saurus_pilot/recovery_drills.py`, including old-export verification
  after retained-record rotation.
- Validate IAM, alias coverage, key policies, and CloudTrail/KMS audit evidence
  before production launch.
- Commission external key-management review before customer production use.

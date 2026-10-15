# Registry Threat Model

**Status:** Initial architecture baseline  
**Reviewed:** 2026-10-12  
**Scope:** Registry service, Saurus desktop client, and the boundary to public-web discovery

## Protected Assets

- Watermark derivation material and key metadata.
- Private retained carrier maps and attribution records.
- Recipient labels, project notes, song identity, and export lineage.
- Registry integrity, state transitions, and audit history.
- Tenant isolation and the ability to abstain when evidence is insufficient.

## Trust Boundaries

1. **Authorized desktop:** trusted to encode during the first server-backed
   release, but assumed recoverable by a motivated local administrator. It must
   receive only short-lived, export-scoped working key grants and store
   credentials in the OS credential store. Tenant/root watermark material must
   not live in the desktop binary or profile.
2. **Registry service:** trusted with business context and encrypted retained
   records. Authorization is enforced in application services as well as HTTP.
3. **Database and backups:** not trusted with plaintext attribution payloads or
   key material. Restore operations must preserve auditability.
4. **Discovery service:** untrusted relative to private registry data. It sees a
   narrow monitoring projection containing song IDs and public matching
   material, never recipients, notes, carrier maps, or watermark keys.
5. **Crawler media worker:** hostile-input boundary with no registry network
   access, bounded resources, and disposable storage.

## Principal Threats

| Threat | Effect | Required control |
| --- | --- | --- |
| Cross-tenant object reference | Private labels or records exposed | Tenant-scoped repository calls and negative authorization tests |
| Extracted desktop secret | Forged or decoded tenant exports | No global embedded secret; short-lived export-scoped grants, tenant/device scope, rotation, and revocation |
| Handle collision or reuse | Ambiguous export claim | Tenant-wide atomic uniqueness, retry, UUID primary identity, collision telemetry |
| Partial reserve/finalize | Active record without valid audio, or orphan | Explicit states, idempotency, expiry, and reconciliation |
| Record tampering or downgrade | False verification behavior | Canonical versioned bytes, digest, encryption, and allowed-version policy |
| Insider record access | Recipient privacy loss | Least privilege, reasoned access, audit event, alerting, and periodic review |
| Audit deletion or rewriting | Investigation history lost | Append-only events, restricted writer, backup, and integrity checks |
| Crawler SSRF or parser exploit | Internal compromise | Network allow/deny policy, sandboxed decoding, strict byte/time/resource limits |
| Discovery-to-registry pivot | Bulk recipient data exposure | Separate credentials, databases, roles, and no private registry route access |
| Weak evidence presented as fact | Harmful accusation | Evidence vocabulary, explicit uncertainty, and human review |

## Initial Architecture Decisions

- **Encoding model:** trusted-local with server-owned key custody for the first
  registry-backed release. The authorized desktop performs audio work so source
  audio stays local, but the server owns issuance, durable registry state, and
  tenant/root watermark material. The desktop receives only short-lived,
  export-scoped working key grants bound to tenant, song, export, device,
  actor, profile, and expiry. Server-side encoding remains an option for
  customers willing to upload source audio, but it is not the default custody
  model.
- **Key custody:** the first managed provider is AWS KMS customer-managed
  symmetric keys, with separate alias paths for retained records, encode grants,
  reports, and backups. Local encode grants are working-key capabilities, not
  standing tenant secrets. Key versions must remain available for verification
  after rotation, and every grant issuance must be auditable by actor, device,
  export, and request. See `docs/key-custody-decision.md`.
- **Handle scope:** four-byte handles are unique within a tenant, checked
  atomically at reservation time. Database identity remains a UUID. Verification
  still requires song/export context; the handle is not a public lookup key.
- **Service separation:** discovery can submit a song candidate identifier only
  through an explicit review handoff. It cannot resolve recipients or retrieve
  retained records.
- **Lineage:** parent-child history is registry metadata. Each child audio export
  is encoded from the clean registered master and carries one active event.

## Capacity Note

A four-byte space contains 4,294,967,296 values. At one million active or
historical tenant handles, a fresh random draw has roughly a 0.023 percent
chance of colliding with an existing value; retrying after an atomic conflict is
therefore practical at that scale. The probability that some collision attempt
has occurred is much higher, so collisions must be expected and measured rather
than treated as impossible. Capacity must be reviewed before very large tenant
volumes or any blind/global lookup feature. The executable review lives in
`src/saurus_registry/capacity.py`; it preserves the current four-byte codec
compatibility decision, reports both fresh-draw and any-collision probabilities,
and marks wider handles as requiring a codec version and migration evidence
before use.

## Residual Risks And Required Review

- A trusted-local encoder exposes scoped working key material to an authorized
  endpoint for the grant lifetime.
- Four bytes limit namespace capacity and do not authenticate registry context.
- Local clean self-verification does not prove platform or recorded-audio
  robustness.
- Legal and policy review is still required before any public-web connector.
- External security review is required before production registry launch.

## Security Gates

- Two-tenant tests demonstrate no cross-tenant read, mutation, or lineage path.
- Production tenant-isolation readiness requires passing evidence for registry
  API authorization, registry repository scope, KMS grant scope, backup/export
  scope, discovery projection, and crawler network separation. The executable
  launch gate lives in `src/saurus_pilot/tenant_isolation.py`.
- Interrupted reserve/finalize operations reconcile without duplicate active exports.
- Key rotation and backup restore are rehearsed against versioned records.
- Encode grants are scoped, expiring, auditable, and unwrap only for the
  intended device.
- Crawler workers cannot address registry networks or private IP ranges.
- User-visible results follow `docs/evidence-language.md`.

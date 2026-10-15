# Saurus Retention And Deletion Policy Draft

**Status:** Draft for counsel review  
**Scope:** Registry retained records, registry audit events, recovery receipts,
discovery candidate records, and support artifacts.

This draft is an approval packet, not an approved policy. Production deletion
must remain disabled until counsel and the accountable owner approve a policy
version and retention schedule.
The production legal/policy gate in `src/saurus_pilot/legal_policy.py` treats
retention/deletion as one required review area; this draft alone does not pass
that gate without counsel approval.
Production readiness is recorded in `src/saurus_pilot/retention.py`; it also
requires a retention review reference, backup or approved export prerequisite,
deletion audit reference, implementation status, and reviewer before the
production gate can pass.

## Proposed Boundaries

- Source audio stays local by default and is not part of registry retention.
- Registry retained records, export state, verification events, and grant audit
  records are evidence-bearing records.
- Audit events are append-only; deletion work may redact or remove eligible
  retained payloads only after preserving an audited deletion request.
- Discovery candidates are song-level review records and must stay separate
  from private registry recipient context.
- Legal hold overrides retention thresholds and deletion requests.

## Approval Gates

- Counsel reviewer, accountable owner, policy ID, and approval timestamp must be
  recorded before destructive deletion tooling can run.
- A retention review must mark an export as due for `review`; records marked
  `keep` or `hold` are not eligible.
- A backup or approved export must exist before deleting retained registry
  payloads.
- Deletion events must preserve tenant, export, actor, request, policy ID,
  reason digest, and timestamp without copying retained payload bytes.

## Open Counsel Questions

- Minimum retention windows for active, revoked, failed, and abandoned exports.
- Whether retained private carrier maps are legal evidence, operational support
  data, or both.
- Regional deletion obligations for discovery candidates and opt-out requests.
- Required backup retention after an approved deletion.
- Whether customers may request tenant export before deletion.

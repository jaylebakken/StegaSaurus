# External Security Review Scope

**Status:** Production-readiness packet draft  
**Reviewed:** 2026-10-12  
**Scope:** Registry-backed desktop alpha, hosted registry API, KMS-backed encode
grants, discovery crawler boundary, and deployment operations.

This packet is the handoff for an independent security reviewer before any
production launch. It does not approve production by itself; it defines what the
review must cover and what evidence Saurus should prepare.

## Required Review Areas

| Area | Reviewer should inspect | Production blocker examples |
| --- | --- | --- |
| API authorization | Authentication, roles, request IDs, idempotency, state transitions, verification events, and mutation replay behavior | Cross-tenant access, route missing auth, replay creates duplicate active export |
| Tenant isolation | Repository calls, launch-gate probes, selected-claim verification, bundles, exports, and audit views | Tenant can enumerate, mutate, verify, or export another tenant's records |
| Key management | AWS KMS alias hierarchy, grant issuance, ciphertext grants, expiry, revocation, rotation, and audit events | Shared production secret in desktop, unscoped data key, unaudited grant issuance |
| Desktop credentials | Enrollment, OS-backed credential storage, sign-out, pending queue, local registry fallback, and release package | Bearer token visible in logs/UI, token persists after sign-out, package embeds production secret |
| Infrastructure | CloudFormation/IaC, IAM policies, secrets, logs, backups, budget guardrails, network boundaries, and teardown | Broad IAM policy, public database, long-lived sensitive logs, no restore evidence |
| Discovery crawler | Source approval, URL policy, SSRF guards, media byte/time limits, connector isolation, opt-out, and no-notification gate | Crawler can reach private networks, notices can send without human/counsel approval |
| Privacy and retention | Retained-record fields, deletion request gate, audit retention, exports, reports, and evidence wording | Destructive deletion without approved policy, report assigns blame or overstates proof |

## Inputs To Prepare

- Current `TODO.md` and `10-12-plan.md`.
- `docs/registry-threat-model.md`, `docs/key-custody-decision.md`,
  `docs/operations-runbooks.md`, `docs/retention-deletion-policy.md`, and
  `docs/evidence-language.md`.
- Alpha IaC from `infra/aws-alpha`.
- Local launch-gate, smoke-test, privacy-scan, and no-notification rehearsal
  outputs.
- KMS grant audit samples that contain request/tenant/device/export digests but
  no wrapped key material.
- A test tenant pair for cross-tenant negative probes.

## Deliverables

- Written report reference suitable for release records.
- List of reviewed areas mapped to the required review areas above.
- Findings with severity, affected system, reproduction notes, and fix owner.
- Explicit count of open critical, high, and medium findings.
- Reviewer statement on whether production launch is blocked.
- Follow-up review requirement if any critical or high finding is fixed after
  the report date.

## Exit Criteria

Production remains blocked until all required review areas are covered and zero
critical or high findings remain open. Medium findings can remain open only when
the release owner accepts them in writing and adds follow-up dates to `TODO.md`.
The executable gate for recording this status is
`src/saurus_pilot/security_review.py`.

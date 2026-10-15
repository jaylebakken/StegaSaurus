# Slim AWS Alpha Architecture

**Status:** Deployment target decision  
**Reviewed:** 2026-10-12  
**Scope:** Registry-backed desktop alpha only. Public-web discovery, production
SLA, high availability, and live customer notification workflows are excluded.

## Decision

Use a small containerized registry service with a managed PostgreSQL database
for the AWS alpha.

| Area | Alpha choice | Rationale |
| --- | --- | --- |
| Compute | One containerized registry task behind HTTPS | Closest to the existing long-lived router/service shape and easiest to keep framework decisions out of `stegosaurus.audio`. |
| Database | Managed PostgreSQL | Exercises production-like migrations, backups, transactions, and multi-connection behavior better than hosted SQLite. |
| Registry API | Existing `RegistryApi` contract wrapped by the deployed service | Keeps desktop behavior aligned with the local SQLite registry path. |
| Key custody | AWS KMS customer-managed symmetric keys behind the existing key-custody contract | Preserves the source-audio-local desktop model while replacing local HMAC test grants. See `docs/key-custody-decision.md`. |
| Secrets | Managed secrets for database credentials, API signing material, bootstrap admin, and future device enrollment secrets | Avoids checked-in environment files and desktop-embedded shared secrets. |
| Object storage | Encrypted bucket for database backup exports, restore artifacts, and digest-only support bundles | No source audio or private retained-record sidecars by default. |
| Discovery | Not deployed in first alpha | Live crawling adds source policy, media retention, network isolation, and cost uncertainty. |

## Network Shape

```text
Saurus desktop
  -> public HTTPS endpoint
  -> registry container task
  -> private PostgreSQL database
  -> KMS and managed secrets through service role
  -> encrypted backup/support object storage
  -> logs, metrics, budget alarms
```

No crawler worker, NAT gateway, retained media store, or source-audio upload is
part of this alpha shape.

## Required Infrastructure Work

- [~] Infrastructure-as-code module for registry service, database, KMS keys,
  secrets, logs, alarms, and object storage. Draft CloudFormation exists with a
  local preflight review plus HTTPS load balancer, ECS service networking, and
  database subnet/security wiring; packaged container validation and deployed
  validation remain open.
- [~] Environment tags: `project=saurus`, `env=alpha`, `owner`. The local
  preflight rejects missing tag coverage in the draft template; deployed tag
  audit remains open.
- [~] Budget alerts before any always-on resource is deployed. The draft budget
  alert is locally checked for an 80 percent threshold; the live budget
  subscription remains unverified until deployment.
- [~] Production monitoring, alerting, paging, and budget readiness. The
  production gate in `src/saurus_pilot/monitoring.py` requires live evidence
  for registry metrics, registry health, KMS grant alerts, backup/restore
  alerts, discovery dashboard, log privacy validation, budget alert, and pager
  route before production readiness can pass.
- [x] Short log retention with no bearer tokens, plaintext retained records,
  carrier maps, source audio, or recipient notes. The draft template sets
  14-day retention; local privacy scans cover generated text artifacts and
  hosted log validation remains open.
- [ ] Smoke-test command that runs from a developer machine against the alpha
  endpoint.
- [ ] Teardown script or documented destroy procedure.

## Alpha Acceptance Checks

- [ ] Desktop can enroll or use a test device credential.
- [ ] Desktop can register one song, reserve an export, encode locally,
  finalize remotely, verify a selected claim, and post a verification event.
- [ ] KMS-backed encode grants are scoped by tenant, song, export, device,
  actor, profile, request, and expiry.
- [~] Backup and restore rehearsal succeeds. The production-shaped drill record
  now defines required evidence for the intended PostgreSQL alpha database;
  actual deployed rehearsal remains open.
- [ ] Tenant-isolation probes fail closed.
- [ ] Operator can disable the grant path before further encode work.
- [x] Checked-in template passes the local IaC preflight. Evidence:
  `review_aws_alpha_template("infra/aws-alpha/template.yaml")`.

## Explicit Non-Goals

- Multi-region failover.
- Customer uptime commitment.
- Live public-web crawling.
- Server-side source audio upload.
- Automatic external notices or legal conclusions.
- Blind/global handle lookup.

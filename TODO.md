# Saurus Deployment Readiness TODO

**Date:** 2026-10-12  
**Purpose:** Track the practical work required to move from local desktop and
registry plumbing to a safe alpha, controlled pilot, and eventual production
deployment.

Checklist markers:

- `[ ]` not started
- `[~]` in progress
- `[x]` complete
- `[!]` blocked
- `[-]` intentionally deferred

## Current Posture

- [x] Desktop local sidecar mode works as the default path.
- [x] Desktop can opt into a local SQLite registry-backed flow.
- [x] Registry API supports reserve, finalize, fail, revoke, selected-claim
  verification, bounded known-song bundles, verification events, and audit
  records.
- [x] Local KMS-shaped encode-grant contract exists for tests and planning.
- [x] Local backup, restore, key-rotation rehearsal, retention review, tenant
  export, metrics, launch-gate, and access-review primitives exist.
- [~] AWS alpha registry service is live in `us-east-2` for restricted internal
  smoke testing at `https://registry-alpha.saurus-audio.com`; ingress is limited
  to `73.135.7.209/32`, the image is pinned to `alpha-20261014-003`, and
  `/health` plus synthetic live registry workflow smokes passed. Pilot/customer
  data remains blocked by the internal-alpha-only image risk decision and
  production-readiness gates. Evidence:
  `docs/aws-alpha-image-risk-decision.md`.
- [~] Discovery planning and local safety primitives exist, but live crawling is
  intentionally not launched.

## Alpha Deployment

- [x] Choose the AWS alpha compute shape: container task or Lambda/API adapter.
  Decision: one containerized registry service behind HTTPS. Evidence:
  `docs/aws-alpha-architecture.md`.
- [x] Choose alpha persistence: managed PostgreSQL preferred; SQLite hosting
  only if explicitly marked disposable. Decision: managed PostgreSQL. Evidence:
  `docs/aws-alpha-architecture.md`.
- [~] Add infrastructure-as-code for the alpha stack. Draft CloudFormation
  skeleton exists in `infra/aws-alpha` with PostgreSQL, managed secrets,
  encrypted backup storage, short logs, budget alert, ECS task placeholder, and
  the selected KMS alias hierarchy; scoped ECS task policies now cover managed
  secrets, encode-grant data keys, and encrypted backup artifacts; a local
  IaC preflight now checks tag coverage, required KMS aliases, budget alert,
  short logs, private encrypted database, encrypted backups, and no
  crawler/NAT marker before deployment; the draft now includes an HTTPS load
  balancer, ECS cluster/service, service/database security groups, and database
  subnet wiring; a packaged registry container entrypoint and Dockerfile now
  exist for launch checks; CloudWatch alarms now cover ALB 5xx responses,
  unhealthy targets, ECS CPU, and low database storage; the draft now includes
  a hardened ECR repository for alpha registry images with immutable tags,
  scan-on-push, KMS encryption, lifecycle cleanup, repository URI output, and
  an ECS image parameter constrained to alpha-tagged ECR images; the registry
  container now selects a psycopg-backed PostgreSQL repository when ECS injects
  database endpoint and secret values, while keeping SQLite for local launch
  checks; live endpoint smoke execution, deployed PostgreSQL smoke, and
  deployed policy validation remain open; the template now supports a
  two-phase bootstrap where ECR/database/guardrails deploy first and the ECS
  service is enabled only after an immutable alpha image and ACM certificate are
  ready; a local deployed-endpoint smoke command now exists for the first HTTPS
  health check after deployment; phase one has been deployed in `us-east-2`
  with stack `saurus-alpha`, budget guardrails, managed PostgreSQL, KMS aliases,
  managed secrets, backup bucket, ECR repository, ALB shell, and alarms active;
  immutable image tag `alpha-20261014-003` has been built, launch-checked, and
  pushed to ECR with digest
  `sha256:e07ae0f8a075b57b644fdadb9795ba5aee87bfca231757e2e51b731dc387a398`;
  ECR basic scanning reports 3 high base-image findings in Debian `glibc` and
  `zlib`; a conditional internal-alpha-only risk decision is recorded in
  `docs/aws-alpha-image-risk-decision.md`; service phase two is deployed with
  ALB ingress restricted to `73.135.7.209/32`; `/health` smoke, synthetic live
  registry workflow smoke, local desktop smokes, local readiness checks, and the
  full application suite passed, while pilot/customer data remains blocked until
  a clean rebuild or fresh signoff plus production-readiness gates.
- [~] Tag all alpha resources with `project=saurus`, `env=alpha`, and `owner`.
  Draft template applies these tags to locally detected taggable resources, and
  the IaC preflight rejects missing tag coverage; final deployed resource tag
  audit remains open.
- [~] Create AWS budget alerts before deploying always-on resources. Draft
  template includes an 80 percent monthly budget email alert, and the local IaC
  preflight rejects missing or higher-threshold budget alerts.
- [x] Configure short log retention for alpha. Evidence: draft template sets
  the registry log group retention to 14 days.
- [x] Avoid NAT gateways, live crawler workers, and retained media stores in
  alpha unless explicitly approved. Evidence: `docs/aws-alpha-architecture.md`
  excludes these from the first alpha shape.
- [x] Add a documented teardown/rebuild path. Evidence:
  `infra/aws-alpha/README.md`.
- [x] Add an alpha smoke test: enroll device, register song, reserve export,
  encode locally, finalize remotely, verify selected claim, post verification
  event. Evidence: `python -m saurus_app.smoke --mode alpha-contract`.

## Web Alpha

- [~] Define the three-part web alpha product shape: public page, account
  lifecycle, and application shell. Evidence: `docs/web-alpha-plan.md`.
- [x] Keep the existing public Saurus page intact and add an alpha entry point.
  Evidence: `src/saurus_site/index.html`.
- [x] Add a static web alpha shell for product walkthroughs and design review.
  Evidence: `src/saurus_site/alpha.html`.
- [~] Add AWS Cognito managed login for alpha sign-up, sign-in, email
  verification, password reset, and sign-out. CloudFormation resources now
  exist in the alpha template; deployment and callback smoke remain open.
- [~] Add a registry gateway that validates Cognito JWTs and signs internal
  registry API requests server-side. Local gateway core and contract tests now
  exist; deployed HTTPS integration remains open.
- [x] Add a Lambda/API Gateway adapter for the gateway so HTTP API events with
  Cognito JWT authorizer claims can become browser-safe registry gateway
  requests.
- [x] Add CloudFormation wiring for the staged web gateway: HTTP API, Cognito
  JWT authorizer, Lambda proxy integration, gateway role, tenant-mapping secret,
  and database security-group access.
- [ ] Package and upload the web gateway Lambda artifact.
- [ ] Populate the tenant-mapping secret with approved alpha users.
- [ ] Deploy `DeployWebGateway=true` and smoke test Cognito-authenticated song
  creation through the gateway.
- [ ] Keep browser writes disabled until the gateway replaces direct HMAC
  registry access.
- [ ] Add a web UI smoke check for navigation, file selection, and package
  staging.
- [ ] Decide whether web alpha source audio remains local, is uploaded
  temporarily, or is stored under an explicit retention policy.

## Registry Service

- [x] Keep sidecar mode available for demos and fallback.
- [x] Connect desktop to the existing local registry path before AWS.
- [x] Add visible desktop sign-in or device enrollment UI. Evidence: desktop
  registry strip exposes `Enroll...`, `Sign out`, and credential status controls
  with token-masked input and no token text in status messages.
- [x] Move desktop credentials into OS-backed secure storage. Evidence:
  desktop enrollment now uses a protected credential-store adapter by default;
  Windows builds use DPAPI-bound encrypted credential blobs, while tests inject
  memory or deterministic protectors.
- [x] Add visible retry/offline state for pending registry-backed encodes.
  Evidence: registry-backed encodes update a local pending log, and the desktop
  `Pending` action shows retryable interrupted work without private records.
- [x] Add operator-visible registry health summary. Evidence: desktop local
  registry strip has a `Health` action reporting schema, tenant readiness,
  song/export state counts, audit-event count, database size, and path.
- [x] Add production database migration/runbook workflow. Evidence:
  `docs/operations-runbooks.md` now names managed PostgreSQL, includes concrete
  `psql` staging/alpha migration commands, and references
  `saurus_registry.render_postgres_migration_plan` for reviewed schema SQL.
- [x] Add distributed idempotency or locking design for multi-instance hosting.
  Evidence: `docs/distributed-idempotency.md`.
- [~] Add production thresholds for launch-gate metrics after pilot data exists.
  Production threshold records now require concrete `RegistryLaunchThresholds`
  tied to a real pilot data reference and reviewer; actual pilot measurements
  remain open.
- [~] Rehearse backup restore against the intended alpha database. Production-
  shaped drill records now require managed PostgreSQL or equivalent database
  shape, backup/restore references, measured elapsed time, and reviewer; actual
  alpha database rehearsal remains open.
- [~] Rehearse retained-record key rotation against the intended alpha database.
  Production-shaped rotation drill records now require managed PostgreSQL or
  equivalent database shape, old/new key references, rotated retained records,
  old-export verification, and reviewer; actual alpha database rehearsal
  remains open.

## Key Custody

- [x] Decide product direction: server-owned key custody with local
  export-scoped desktop grants.
- [x] Keep source audio local by default.
- [x] Select production KMS/HSM provider and key hierarchy. Decision: AWS KMS
  customer-managed symmetric keys with separate alias paths for registry
  records, encode grants, reports, and backups. Evidence:
  `docs/key-custody-decision.md`.
- [~] Replace local KMS-shaped grants with a managed KMS-backed provider.
  AWS-KMS-shaped provider contract now issues scoped data-key grants through an
  injected KMS client and records ciphertext grants plus audit metadata; a
  boto3 KMS adapter now wires that contract to a live AWS SDK client without
  making local tests depend on AWS; IAM policy and deployed alpha validation
  remain open.
- [~] Audit every grant issuance by tenant, song, export, device, actor,
  profile, request, and expiry. Grant audit records now persist as digest-only
  append-only registry events without wrapped key material; deployed
  CloudTrail/KMS evidence validation remains open.
- [x] Add grant revocation/disable runbook. Evidence:
  `docs/operations-runbooks.md`.
- [x] Add key rotation runbook with verification of old exports. Evidence:
  `docs/operations-runbooks.md`.
- [x] Ensure no shared production watermark secret ships in the desktop binary.
  Desktop secret posture now labels the remaining shared watermark secret as
  `local-demo-only` and not production-ready; desktop packaging now blocks the
  `production` release channel until KMS-backed watermark grants replace the
  local demo secret.
- [~] Store API signing secrets, bootstrap credentials, and database credentials
  in managed secrets. Draft CloudFormation now splits API signing, bootstrap
  admin, device enrollment, and database credentials into managed secrets and
  grants the registry task scoped read access; ECS task secret injection now
  supplies API signing, database, bootstrap admin, and device enrollment secret
  values from Secrets Manager instead of plain secret ARN environment values;
  the registry container launch check validates injected secret shapes without
  printing secret values, and the ECS task now passes PostgreSQL host, port,
  and database name for adapter wiring; the container privately builds
  PostgreSQL connection settings from those values for live alpha mode; final
  production secret issuance, deployed connection validation, and rotation
  remain open.

## Desktop App

- [x] Encode mode guides source, registry details, and output paths.
- [x] Decode mode verifies one selected retained claim.
- [x] Attribution view summarizes retained registry context without assigning
  blame.
- [x] Local registry mode is opt-in and sidecar mode remains default.
- [x] Make registry mode copy clearer for alpha users. Evidence: desktop
  registry strip now labels local registry as alpha and shows the active mode.
- [x] Add a visible pending/retry queue for interrupted registry workflows.
  Evidence: desktop registry strip has a `Pending` action backed by
  `PendingEncodeLog` and tested retryable encode interruption handling.
- [x] Add user-facing credential enrollment and sign-out controls. Evidence:
  desktop credential controls enroll a session credential, show
  `DEVICE ENROLLED`, and clear it on sign-out.
- [x] Add a compact registry status indicator. Evidence: desktop registry strip
  now shows `SIDECAR MODE` or `LOCAL REGISTRY ON`.
- [x] Add smoke-test fixtures or scripted desktop workflow for release checks.
  Evidence: `python -m saurus_app.smoke` runs a local-registry encode, decode,
  verification-report, and attribution-inspection workflow.
- [x] Package and launch-test the desktop app on the target OS. Evidence:
  `python -m saurus_app.packaging --output dist/saurus-desktop.pyz` produced a
  lightweight `.pyz` alpha artifact on Windows and passed its hidden Tk launch
  check.

## Security And Privacy

- [x] Document registry threat model.
- [x] Document evidence language boundaries.
- [x] Document recovery receipt field contract.
- [~] Commission external API, tenant-isolation, key-management, and crawler
  security review before production launch. Scope packet and executable signoff
  gate exist in `docs/security-review-scope.md` and
  `src/saurus_pilot/security_review.py`; external reviewer and final report
  remain open.
- [~] Verify logs never include bearer tokens, plaintext retained records,
  carrier maps, source audio, or recipient notes. Local text-artifact privacy
  scanner, alpha smoke receipt checks, and privacy-safe registry request-log
  projection are in place; hosted CloudWatch log validation remains open until
  deployment exists.
- [x] Add incident response runbook for registry credential exposure. Evidence:
  `docs/operations-runbooks.md`.
- [x] Add incident response runbook for mistaken discovery alert or external
  notice. Evidence: `docs/operations-runbooks.md`.
- [~] Define retention and deletion policy with counsel. Draft approval packet
  exists in `docs/retention-deletion-policy.md`; counsel approval remains open.
- [~] Add audited deletion tooling only after policy approval. Registry deletion
  requests now require a counsel-approved policy record and append a digest-only
  audit event without deleting retained records; destructive deletion remains
  disabled until policy approval.

## Discovery Service

- [x] Keep discovery separate from private registry data.
- [x] Discovery candidates remain song-level, not recipient-attribution verdicts.
- [x] Reviewed-feed snapshot connector exists without live crawling.
- [x] URL policy, media bounds, source controls, dashboard alerts, opt-out, and
  incident drill primitives exist locally.
- [~] Select first real public source with clear permitted access path. Public
  source selection records now require source ID, permitted-access reference,
  owner, and timestamp; real source selection remains open.
- [~] Obtain legal/policy review for sources, retention, notices, and opt-out.
  Discovery legal/policy review records now require source policy, retention,
  notice, opt-out, counsel reviewer, and approval evidence; actual review
  remains open.
- [~] Select or license a song-recognition engine. Recognition engine selection
  records now require engine name/version and license reference; actual engine
  selection or license remains open.
- [~] Build representative positive, negative, edited, excerpted, and codec
  corpus. Corpus summary records now require positive, negative, edited,
  excerpted, and codec-variant counts plus corpus reference; actual corpus
  remains open.
- [~] Run no-notification baseline over approved tracks and sources. Local
  rehearsal exists and passes with zero client notifications; real approved
  tracks and sources remain open.
- [~] Set thresholds from measured false-positive and miss rates. Threshold
  calibration records now bind measured fingerprint evaluation to false-positive
  and miss-rate bounds; real corpus measurements remain open.
- [x] Keep live crawling disabled until approved sources and corpus exist.
  Evidence: executable live-crawl gate defaults to disabled until approved
  target/source enrollment, no-notification baseline, representative corpus,
  legal/source-policy approval, and a selected song-recognition engine exist.

## Evidence And Product Claims

- [x] Preserve distinction between audio encoding, statistical detection, and
  future attribution decoding.
- [x] Use registry-only lineage; do not stack child watermarks.
- [x] Avoid claims beyond named measured evaluations.
- [x] Review all app copy, README copy, reports, and sales language for evidence
  wording. Evidence: executable evidence-copy review scans README, marketing,
  desktop app copy, and generated report wording for certainty, blame,
  absence, and unsupported robustness phrases.
- [x] Ensure attribution reports say what matched, what did not match, and when
  the system abstained. Evidence: verification report summaries render accepted
  match, rejected selected-claim, and abstention lanes separately.
- [x] Require human review before client alerts, attribution handoffs, external
  notices, or legal workflows. Evidence: discovery external-action approvals
  require accepted review, reviewer, counsel reviewer, client policy reference,
  neutral language, and attribution-eligible evidence for attribution handoffs,
  external notices, and legal workflows.

## Pilot Gates

- [~] Assign owners for registry, desktop, discovery, security, and policy.
  Pilot go/no-go records now require all five owner roles; real pilot assignees
  remain open.
- [~] Choose pilot tracks that are licensed or owned. Pilot scope records now
  require each track to include an ownership or licensing reference; real
  client-approved pilot tracks remain open.
- [~] Choose approved public sources. Pilot scope records now require each
  source to include a permitted-access reference and policy reviewer; real
  approved public sources remain open.
- [~] Define numeric pilot thresholds. Pilot scope records now require
  `DiscoveryPilotThresholds` before the scope can be ready; real pilot
  threshold values remain open.
- [x] Run alpha smoke test successfully. Evidence:
  `python -m saurus_app.smoke --mode alpha-contract` passed on 2026-10-12 with
  deterministic handle `01020304`, including credential enrollment, encode,
  decode, verification-event posting, and receipt token-leak check.
- [x] Run registry launch-gate review successfully. Evidence:
  `python -m saurus_registry.readiness` passed a local alpha registry launch
  rehearsal with `go: true`, 100 percent finalize rate, 100 percent access-probe
  pass rate, zero API errors, and a successful backup/restore rehearsal.
- [x] Run discovery no-notification baseline successfully. Evidence:
  `python -m saurus_discovery.readiness` passed a reviewed-feed rehearsal with
  zero client notifications, adjudicated local candidates, policy-denial
  accounting, and live crawling still disabled.
- [~] Review pilot results with client and counsel. Draft go/no-go template
  exists in `docs/pilot-go-no-go.md`; actual client/counsel review remains
  open.
- [~] Write go/no-go decision before sending any client notifications. Pilot
  decision records now require registry and discovery go decisions, owner
  assignments, counsel reviewer, client review reference, and block client
  notifications unless all gates pass; actual pilot decision remains open.

## Production Gates

- [~] External security review complete. Review scope and production-blocking
  signoff record exist, but the independent review report remains open.
- [~] Production KMS-backed grants live and tested. Live KMS grant test records
  now require the Saurus encode-grants alias path, AWS KMS data-key grant
  algorithm, scoped context digest, IAM policy reference, CloudTrail evidence,
  grant audit reference, smoke-test reference, and reviewer; deployed AWS
  evidence remains open.
- [~] Backups and restore drills pass on production-shaped infrastructure.
  Backup/restore drill records now define required evidence for
  production-shaped database rehearsals; live drill evidence remains open.
- [~] Key rotation drill passes without breaking old verification. Key-rotation
  drill records now require old-export verification after retained-record
  rotation; live drill evidence remains open.
- [~] Retention/deletion policy approved and implemented. Production readiness
  records now require counsel-approved policy, retention review reference,
  backup/export prerequisite, deletion audit reference, destructive deletion
  implementation status, and reviewer; actual counsel approval and destructive
  implementation remain open.
- [~] Monitoring, alerting, paging, and budget controls live. Production
  monitoring readiness records now require registry API metrics, registry
  health, KMS grant alerts, backup/restore alerts, discovery dashboard, log
  privacy validation, budget alert, and pager route evidence with paging
  owners; the AWS alpha draft now includes an operations alert topic and
  minimum CloudWatch alarms for registry availability/resource pressure, while
  live deployed subscriptions and hosted log validation remain open.
- [~] Tenant isolation probes pass. Production tenant-isolation readiness
  records now require passing evidence for registry API authorization,
  registry repository scope, KMS grant scope, backup/export scope, discovery
  projection, and crawler network separation; live deployed probes remain
  open.
- [~] Incident response drills complete. Cross-system drill records now require
  registry credential exposure and mistaken discovery alert rehearsals to cover
  contain, assess, recover, communicate, and review phases; real production
  staffing, paging, and completed live-environment drills remain open.
- [~] Legal/policy review complete for discovery and evidence language.
  Legal/policy review records now require counsel and policy-owner review of
  evidence language, discovery source policy, client alerts/notices, opt-out
  and corrections, and retention/deletion before production readiness; actual
  counsel-approved policy remains open.
- [~] Production launch decision signed off by owner, security, and policy.
  Executable launch decision records now require every production gate plus
  owner, security, and policy signoff before approval; actual production
  evidence and signoff remain open.

# Saurus AWS Alpha Crash Course

**Date:** 2026-10-14  
**Region:** `us-east-2`  
**Stack:** `saurus-alpha`  
**Status:** alpha registry service enabled for restricted internal smoke;
`/health` and synthetic registry workflow smokes passed; pilot/customer data is
still blocked.

This document explains the AWS alpha in plain English. It is not a production
runbook. It is the map for what we created, why it exists, what is still off,
and how the pieces will fit together once the registry container is running.

## One-Screen Summary

The alpha is a small hosted registry environment. Its job is to prove that the
desktop app can talk to a real cloud registry without uploading source audio by
default.

```text
Saurus desktop
  -> HTTPS load balancer
  -> ECS Fargate registry container
  -> PostgreSQL registry database
  -> KMS keys and Secrets Manager
  -> CloudWatch alarms, budget, and backup bucket
```

Right now, the cloud foundation and first registry container are live for a
restricted internal smoke window. We intentionally deployed in two phases:

1. **Foundation phase:** create ECR, PostgreSQL, KMS, secrets, backup storage,
   ALB shell, alarms, and budget controls.
2. **Service phase:** build and push the container image, supply an ACM
   certificate, restrict ingress to the operator IP, enable the ECS service,
   then smoke test `/health`.

## What Is Live Now

The live CloudFormation stack is `saurus-alpha` in `us-east-2`.

Important outputs:

| Output | Value |
| --- | --- |
| ECR repository | `753695657434.dkr.ecr.us-east-2.amazonaws.com/saurus-alpha-registry` |
| Load balancer DNS | `saurus-Regis-yQOydaIIlRjd-770371155.us-east-2.elb.amazonaws.com` |
| Alpha hostname | `registry-alpha.saurus-audio.com` |
| Hosted zone | `saurus-audio.com` / `Z0473553HH2GBFCD61DC` |
| ACM certificate | `arn:aws:acm:us-east-2:753695657434:certificate/454af841-34e4-464b-85ad-38758b29d021` |
| Backup bucket | `saurus-alpha-backupbucket-wzfbiqnyoyvc` |
| Registry records key | `alias/saurus/alpha/registry-records` |
| Encode grants key | `alias/saurus/alpha/encode-grants` |
| Reports key | `alias/saurus/alpha/reports` |
| Backups key | `alias/saurus/alpha/backups` |

The ECS task definition and ECS service are enabled with desired count `1`.
Ingress is restricted to `73.135.7.209/32` for the internal smoke window.

## Service Roles

### CloudFormation

CloudFormation is the deployment engine. The template in
`infra/aws-alpha/template.yaml` is the source of truth for the stack. When we
deploy, CloudFormation creates, updates, or deletes resources to match the
template.

Think of CloudFormation as the contractor reading the blueprint. The blueprint
is versioned in this repo; the contractor is AWS.

### ECR

ECR is the container image registry. It will store the packaged Saurus registry
container image.

Current guardrails:

- Repository name: `saurus-alpha-registry`
- Tags are immutable.
- Images are scanned on push.
- Repository is KMS encrypted.
- Lifecycle policy keeps the ten newest alpha images.

The next image tag should look like:

```text
alpha-YYYYMMDD-NNN
```

### ECS Fargate

ECS Fargate will run the registry container without us managing servers.

The service is enabled with immutable image tag `alpha-20261014-003`. Fargate
runs one task by default.

The container receives:

- Plain environment values for non-secret metadata, such as database host, port,
  database name, backup bucket, and KMS alias.
- ECS secret injection for API signing, database credentials, bootstrap admin,
  and device enrollment secrets.

### Application Load Balancer

The ALB is the public HTTPS edge. When the service is enabled, desktop clients
will talk to the ALB, and the ALB will forward requests to the registry
container on port `8080`.

The ALB has an HTTPS listener using the issued ACM certificate for
`registry-alpha.saurus-audio.com`.
For internal alpha smoke, the ALB ingress should be limited to the operator's
current public IPv4 address with `/32`. The template defaults to
`127.0.0.1/32` so the public edge stays closed until an explicit smoke-window
CIDR is supplied.

### Route 53 And ACM

The public hosted zone for `saurus-audio.com` is created in Route 53. The alpha
hostname `registry-alpha.saurus-audio.com` already has an alias record pointing
to the alpha ALB, and ACM has a DNS validation CNAME in the hosted zone.

Update the domain registrar to use these Route 53 nameservers:

```text
ns-1547.awsdns-01.co.uk
ns-528.awsdns-02.net
ns-1111.awsdns-10.org
ns-463.awsdns-57.com
```

Delegation and the ACM validation CNAME are visible in public DNS as of
2026-10-14. ACM issued the certificate, and the alpha hostname routes to the
ALB.

### RDS PostgreSQL

RDS PostgreSQL is the durable registry database.

It stores:

- Tenants.
- Songs.
- Exports.
- Retained attribution records.
- Registry audit events.
- Idempotency records for safe desktop retries.

Current alpha shape:

- Engine: PostgreSQL.
- Instance class: `db.t4g.micro`.
- Encrypted storage.
- Private database access from the registry service security group.
- One-day backup retention for the fresh/free-tier account.

Source audio is not stored in PostgreSQL.

### KMS

KMS owns the key hierarchy. We split keys by job so one compromised path does
not automatically become every path.

Current aliases:

- `alias/saurus/alpha/registry-records`: retained registry/private-record
  encryption.
- `alias/saurus/alpha/encode-grants`: export-scoped encode grants.
- `alias/saurus/alpha/reports`: API signing and report-adjacent secret custody.
- `alias/saurus/alpha/backups`: backup bucket and ECR encryption.

This is the backbone of the “server-owned key custody, local desktop working
grant” model.

### Secrets Manager

Secrets Manager stores runtime secrets instead of checking them into the repo or
shipping them inside the desktop binary.

Current managed secrets:

- API signing secret.
- Database username/password JSON.
- Bootstrap admin secret.
- Device enrollment secret.

The ECS task reads these through secret injection, not plain environment values.

### S3 Backup Bucket

The backup bucket is for encrypted backup and support artifacts. It is not a
source-audio bucket.

Current guardrails:

- Public access blocked.
- KMS encryption enabled.
- Tagged `project=saurus`, `env=alpha`, and `owner`.

### CloudWatch And SNS

CloudWatch watches basic health signals. SNS is supposed to email operations
alerts.

Current alarms:

- ALB 5xx count.
- Unhealthy ALB targets.
- ECS CPU, once the service is enabled.
- Low RDS free storage.

The SNS email subscription for `jay@lebakken.com` is still pending. Until that
is confirmed, CloudWatch alarms can publish to the topic, but the email inbox
will not receive those alarm messages.

### Budgets

AWS Budgets is configured with a `$25` monthly budget and an 80 percent alert.
That means the warning threshold is about `$20`.

This is a guardrail, not a hard stop. AWS Budgets warns; it does not
automatically shut services down.

## Request Flow After Phase Two

Once the service is enabled:

1. Desktop sends HTTPS requests to the ALB.
2. ALB forwards registry API requests to the ECS Fargate task.
3. The container validates request auth and route shape.
4. Registry service reads/writes PostgreSQL.
5. Sensitive records and grants use KMS-backed custody paths.
6. Logs and metrics go to CloudWatch.
7. Alarms publish to SNS.

The desktop still encodes locally. The alpha registry coordinates identity,
reservation, finalization, verification records, and audit events.

## What Is Intentionally Not Live Yet

- No public-web crawler.
- No source-audio upload path.
- No production customer data.
- No broad public ingress.
- No pilot/customer data.
- No live KMS grant smoke with CloudTrail evidence.
- No restore drill against the live RDS database.

## Why The Stack Uses Two Phases

The service needs a container image. The container image needs an ECR repository
to push into. The ECR repository is created by the stack.

So phase one creates the place to push the image. Phase two uses that pushed
image to create the running service.

The same logic applies to HTTPS: phase one can create the ALB shell, but phase
two needs an ACM certificate before it can create the HTTPS listener.

## Next Steps

1. Confirm the SNS email subscription or re-send it.
2. Install Docker Desktop or use another image builder.
3. Build the registry image from `infra/aws-alpha/Dockerfile`.
4. Push the image to ECR.
5. Done: set the registrar nameservers for `saurus-audio.com` to the Route 53 values.
6. Done: wait for the ACM certificate to become `ISSUED`.
7. Done: update the stack with `DeployRegistryService=true`.
8. Done: run `python -m saurus_infra.endpoint_smoke https://registry-alpha.saurus-audio.com`.
9. Done: run the first deployed PostgreSQL registry workflow smoke with
   synthetic tenant `tenant-live-smoke-20261014`.

## Live Smoke Evidence

The public health smoke passed:

```powershell
python -m saurus_infra.endpoint_smoke https://registry-alpha.saurus-audio.com
```

The synthetic live registry workflow smoke passed:

```powershell
$env:SAURUS_API_SIGNING_SECRET = "<from Secrets Manager>"
python -m saurus_infra.live_registry_smoke https://registry-alpha.saurus-audio.com `
  --tenant-id tenant-live-smoke-20261014 `
  --actor-id alpha-live-smoke
Remove-Item Env:SAURUS_API_SIGNING_SECRET
```

Covered routes and behaviors: anonymous denial, role denial, song create,
idempotent replay, export reserve, export finalize, song/export/record reads,
verification bundle, lineage, verification event, revoke with retained
verification still available, failed reservation handling, and cross-tenant
selected-export denial.

## Cost Watch

The main always-on costs are likely:

- RDS PostgreSQL.
- ALB.
- KMS keys.
- Secrets Manager secrets.
- CloudWatch logs and alarms.

The budget is set low on purpose. If this alpha is idle for more than a short
development window, either tear it down or accept the small monthly burn as the
price of having a real hosted rehearsal environment.

## Tear Down

The safest teardown path is CloudFormation stack deletion:

```powershell
& 'C:\Program Files\Amazon\AWSCLIV2\aws.exe' cloudformation delete-stack `
  --profile saurus-alpha-admin `
  --region us-east-2 `
  --stack-name saurus-alpha
```

Before deleting a stack that contains any meaningful registry data, export or
back up approved artifacts first. For the current phase-one foundation, there
should be no pilot data yet.

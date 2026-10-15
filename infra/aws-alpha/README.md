# Saurus AWS Alpha Infrastructure

This folder holds the first reviewable infrastructure-as-code skeleton for the
slim AWS alpha. It is intentionally a starting point, not a production stack.

## Shape

- One containerized registry service entrypoint that defaults to local SQLite
  and switches to managed PostgreSQL when alpha endpoint and credential env are
  present.
- ECR repository for alpha registry images with immutable tags, scan-on-push,
  KMS encryption, lifecycle cleanup, and repository URI output.
- HTTPS application load balancer, target group, ECS cluster/service, and
  service/database security groups.
- Managed PostgreSQL database.
- KMS customer-managed key aliases for retained registry records, encode grants,
  signed reports, and backup/support artifacts.
- Managed secret placeholders for database and API signing material.
- ECS secret injection for API signing, database, bootstrap admin, and device
  enrollment runtime credentials.
- Runtime PostgreSQL endpoint env for host, port, and database name.
- Cognito user pool, no-secret web app client, managed login v2 domain, and
  default managed-login branding for the first web alpha account lifecycle.
- Optional web gateway path behind `DeployWebGateway`: API Gateway HTTP API,
  Cognito JWT authorizer, Lambda proxy integration, browser CORS, gateway
  execution role, tenant-mapping secret, short logs, and database security-group
  access for the gateway Lambda.
- Encrypted object storage for backup/support artifacts.
- Short-retention log group.
- Budget notification plus operations alert topic.
- CloudWatch alarms for ALB 5xx responses, unhealthy targets, ECS CPU, and low
  database storage.
- Scoped registry task role access for managed secrets, encode-grant KMS data
  keys, and encrypted backup artifacts.
- Required tags: `project=saurus`, `env=alpha`, and `owner`.
- Local preflight review for required tags, KMS aliases, budget threshold, log
  retention, HTTPS listener, ECS service networking, database subnet wiring,
  private encrypted database, encrypted backups, ECS API-signing secret
  injection for all alpha runtime credentials, minimum operational alarms, and
  no crawler/NAT marker.

## Local Preflight

Run the application suite or import `saurus_infra.review_aws_alpha_template`
before deployment. The preflight is local evidence only; AWS validation,
CloudTrail/KMS evidence, and deployed smoke tests are still required.

The container image draft can be launch-checked locally after package install:

```powershell
python -m saurus_registry.container --launch-check
```

Deploy happens in two phases. First bootstrap the stack with the registry
service disabled so CloudFormation can create the ECR repository, database,
keys, secrets, load balancer, alarms, and budget guardrails. In this phase,
`ContainerImage`, `CertificateArn`, and gateway Lambda artifact parameters may
stay empty.

The helper script uses profile `saurus-alpha`, region `us-east-2`, owner `jay`,
alert email `jay@lebakken.com`, and a `$25` monthly budget by default. It
discovers the default VPC and public subnets before deploying phase one:

```powershell
.\infra\aws-alpha\bootstrap.ps1
```

```powershell
aws cloudformation deploy `
  --template-file infra/aws-alpha/template.yaml `
  --stack-name saurus-alpha `
  --capabilities CAPABILITY_NAMED_IAM `
  --parameter-overrides Owner=your-name AlertEmail=you@example.com DeployRegistryService=false VpcId=vpc-000000 PublicSubnetIds=subnet-000000,subnet-111111
```

Then build and push after the stack creates `RegistryImageRepositoryUri`; use a
unique immutable alpha tag for each build. The Dockerfile installs the
`audio` and `aws-alpha` optional dependency sets so the container has the
registry serialization dependencies plus the PostgreSQL driver.

```powershell
$repo = "<RegistryImageRepositoryUri output>"
$tag = "alpha-20261012-001"
docker build -f infra/aws-alpha/Dockerfile -t "$repo`:$tag" .
docker push "$repo`:$tag"
```

Current pushed alpha image:

```text
753695657434.dkr.ecr.us-east-2.amazonaws.com/saurus-alpha-registry:alpha-20261014-003
sha256:e07ae0f8a075b57b644fdadb9795ba5aee87bfca231757e2e51b731dc387a398
```

ECR basic scanning is complete for this tag and currently reports `HIGH: 3`,
`MEDIUM: 9`, and `LOW: 3`. The high findings are inherited from the Python
slim Debian base image packages `glibc` and `zlib`; the current decision in
`docs/aws-alpha-image-risk-decision.md` allows only short-lived internal alpha
smoke testing, not pilot/customer data.

The current entrypoint is a stdlib HTTP harness for the existing registry API.
It uses the reviewed PostgreSQL migration plan and psycopg adapter in alpha
mode, while keeping SQLite available for local launch checks.

## Deploy Draft

Review and edit parameters first. Do not deploy into a shared or production
account without a security review. After pushing the image and creating or
importing an ACM certificate for the chosen alpha hostname, update the same
stack with `DeployRegistryService=true`, the pinned alpha image URI, and
`CertificateArn`.

Current DNS/certificate values:

```text
Hosted zone: Z0473553HH2GBFCD61DC / saurus-audio.com
Alpha endpoint: https://registry-alpha.saurus-audio.com
Certificate ARN: arn:aws:acm:us-east-2:753695657434:certificate/454af841-34e4-464b-85ad-38758b29d021
Route 53 nameservers:
  ns-1547.awsdns-01.co.uk
  ns-528.awsdns-02.net
  ns-1111.awsdns-10.org
  ns-463.awsdns-57.com
```

The ACM validation CNAME and alpha ALB alias record are already present in
Route 53. Public DNS sees the Route 53 nameservers and validation CNAME, ACM
has issued the certificate, and the service is enabled for restricted internal
smoke with `AllowedIngressCidr=73.135.7.209/32`.

For internal alpha smoke, set `AllowedIngressCidr` to the operator's current
public IPv4 address with `/32`. The default is `127.0.0.1/32`, which keeps the
public ALB effectively closed until a smoke-window CIDR is supplied.

```powershell
aws cloudformation deploy `
  --template-file infra/aws-alpha/template.yaml `
  --stack-name saurus-alpha `
  --capabilities CAPABILITY_NAMED_IAM `
  --parameter-overrides Owner=your-name AlertEmail=you@example.com DeployRegistryService=true ContainerImage=123456789012.dkr.ecr.us-east-2.amazonaws.com/saurus-alpha-registry:alpha-20261012-001 VpcId=vpc-000000 PublicSubnetIds=subnet-000000,subnet-111111 CertificateArn=arn:aws:acm:region:account:certificate/example AllowedIngressCidr=203.0.113.10/32
```

## Teardown Draft

Export any approved backup artifacts before teardown.

```powershell
aws cloudformation delete-stack --stack-name saurus-alpha
```

## Endpoint Smoke Draft

After deployment and DNS/certificate validation, run the public health smoke
check. This is not the full registry workflow smoke; it only validates the HTTPS
edge and `/health` response shape. The first public health smoke passed on
2026-10-14.

```powershell
python -m saurus_infra.endpoint_smoke https://registry-alpha.example.test
```

The deployed registry workflow smoke is:

```powershell
$env:SAURUS_API_SIGNING_SECRET = "<from Secrets Manager>"
python -m saurus_infra.live_registry_smoke https://registry-alpha.saurus-audio.com `
  --tenant-id tenant-live-smoke-20261014 `
  --actor-id alpha-live-smoke
Remove-Item Env:SAURUS_API_SIGNING_SECRET
```

It uses synthetic records only and prints no bearer token, signing secret, or
retained private payload.

## Web Gateway Draft

The web gateway is staged behind `DeployWebGateway=false` until a packaged
Lambda artifact exists and the tenant mapping secret is populated. The intended
front door is API Gateway HTTP API with the Cognito JWT authorizer. API Gateway
validates issuer, audience, expiry, and signature; the Lambda gateway enforces
Saurus tenant and registry-role mapping before minting internal registry
credentials.

The tenant mapping secret starts as:

```json
{"records":[]}
```

Populate it only with approved alpha users before setting `DeployWebGateway` to
`true`.

## Open Items

- Run the first deployed PostgreSQL smoke against the managed database before
  holding pilot data; the container launch check already validates injected
  secret shapes and PostgreSQL endpoint metadata without printing secret values.
- Keep pilot/customer data blocked until the base-image risk decision is
  refreshed and production-readiness gates have live evidence.
- Review the draft task role policy against the packaged service before first
  deployment, then validate KMS and CloudTrail evidence in the alpha account.
- Confirm the SNS email subscription and alarm delivery in the alpha account.
- Validate VPC/subnet/certificate parameters in the deployment account.
- Add a smoke test against the deployed endpoint.
- Package and upload the web gateway Lambda artifact, populate the tenant
  mapping secret, then deploy `DeployWebGateway=true` and run a Cognito callback
  plus gateway song-create smoke.

# AWS Alpha Image Risk Decision

**Date:** 2026-10-14  
**Image:** `753695657434.dkr.ecr.us-east-2.amazonaws.com/saurus-alpha-registry:alpha-20261014-003`  
**Digest:** `sha256:e07ae0f8a075b57b644fdadb9795ba5aee87bfca231757e2e51b731dc387a398`  
**Status:** Conditional internal-alpha acceptance only

## Decision

The current registry image may be used for short-lived internal alpha endpoint
smoke testing, but it should not hold pilot/customer data and should not be
described as production-ready.

The acceptance expires when any of these conditions is true:

- A patched base image becomes available.
- The alpha service is opened beyond internal testing.
- The registry will hold real client records.
- The decision is older than 14 days.

At that point, rebuild, rescan, and record a new decision before continuing.

## Evidence Reviewed

- ECR basic scan for `alpha-20261014-003` completed with `HIGH: 3`,
  `MEDIUM: 9`, and `LOW: 3`.
- The deployed phase-one stack was updated on 2026-10-14 with
  `DeployRegistryService=false`; the ALB target group health matcher now
  accepts only HTTP `200` on `/health`.
- Route 53 hosted zone `Z0473553HH2GBFCD61DC` now exists for
  `saurus-audio.com`; ACM certificate
  `arn:aws:acm:us-east-2:753695657434:certificate/454af841-34e4-464b-85ad-38758b29d021`
  is requested for `registry-alpha.saurus-audio.com`; public DNS sees the Route
- 53 nameservers and validation CNAME, and ACM is `ISSUED`.
- The service phase is deployed with ALB ingress restricted to
  `73.135.7.209/32`; ECS reached steady state with one running task, the ALB
  target is healthy, and
  `python -m saurus_infra.endpoint_smoke https://registry-alpha.saurus-audio.com`
  returned HTTP `200` with the expected `{"status":"ok"}` body.
- The synthetic live registry workflow smoke passed against
  `tenant-live-smoke-20261014`, covering song create, idempotent replay,
  reserve, finalize, record read, verification bundle, lineage, verification
  event, revoke, fail, and authorization denial behavior.
- A recent CloudWatch log scan after the smoke returned no matches for
  `ERROR`, `Traceback`, `Exception`, `password`, `secret`, `token`, or
  `payload_b64`.
- High findings:
  - `CVE-2026-5435` in Debian `glibc` package `2.41-12+deb13u4`
  - `CVE-2026-85091` in Debian `zlib` package `1.3.dfsg+really1.3.1-1`
  - `CVE-2026-19499` in Debian `glibc` package `2.41-12+deb13u4`
- Local reachability review found no direct Saurus calls to the named glibc
  functions and no registry-side gzip or zlib request decompression path.
- The registry container exposes a small JSON HTTP API plus `/health`.
- The alpha stack keeps source audio local by default; the hosted service is
  registry metadata and retained-record custody, not server-side audio upload.

## Finding Assessment

| Finding | Package | Current reachability view | Alpha posture |
| --- | --- | --- | --- |
| `CVE-2026-5435` | `glibc` | Appears unlikely to be reachable from the Python registry API; it concerns deprecated DNS record printing functions. | Accept only for internal alpha while patched base is unavailable. |
| `CVE-2026-85091` | `zlib` | Appears unlikely to be reachable because the registry API does not implement gzip request handling or zlib writes. | Accept only for internal alpha while patched base is unavailable. |
| `CVE-2026-19499` | `glibc` | Appears unlikely to be reachable; it concerns monetary formatting functions, and no network-facing impact is known from the reviewed advisory text. | Accept only for internal alpha while patched base is unavailable. |

This is not a dismissal of the scanner results. It is a scoped exception based
on current application reachability, alpha data limits, and the lack of a fixed
Debian package in the current slim base image.

## Compensating Controls

- Use only synthetic/test tenant data until the image scans without high
  findings or a fresh risk decision is accepted.
- Keep source audio out of the hosted service.
- Keep discovery crawling disabled.
- Keep the service behind HTTPS and signed bearer authentication.
- Keep the ECS desired count at `1` and use the shortest practical test window.
- Keep ALB ingress restricted to `73.135.7.209/32` during this smoke window.
- Confirm SNS operations email delivery before leaving the service running.
- Run endpoint smoke immediately after service enablement.
- Rotate bootstrap/API/device secrets if an exposed alpha endpoint behaves
  unexpectedly.
- Rebuild and rescan at least once before any pilot-data rehearsal.

## Hardening Before Service Enablement

- Done: tighten the ALB target group health matcher from `200-499` to `200` so
  only a clean `/health` response marks the registry task healthy.
- Consider adding an `AllowedIngressCidr` parameter for alpha so the ALB can be
  limited to the operator's current public IP during smoke testing.
- Restrict task-to-database egress to the database security group where
  CloudFormation support and the selected VPC shape allow it.
- Record the chosen image tag, digest, and scan result in the service update
  command or change record.

## Exit Criteria

This exception closes when one of these is recorded:

- A new image tag scans with zero high findings and passes launch check.
- A different base image scans clean enough for the current gate and passes
  launch check.
- A deliberate pilot-risk decision is signed off before holding real client
  registry data.

# Saurus Web Alpha Plan

**Date:** 2026-10-15

This plan turns Saurus from a desktop-first prototype plus internal registry API
into a small web alpha with three clear surfaces: a public page, account
lifecycle, and the authenticated application.

## Product Shape

- [~] **Public page:** Keep `src/saurus_site/index.html` as the public story for
  artists, managers, labels, and collaborators. Add one clear alpha entry point
  without requiring login on the marketing page.
- [~] **Account lifecycle:** Use AWS Cognito managed login for sign-up, sign-in,
  email verification, password reset, sign-out, and eventual account deletion
  requests.
- [~] **Application:** Start with a browser alpha shell for adding a track,
  reviewing registry status, tracking exports, and reading verification
  outcomes. Do not expose registry signing secrets in browser code.

## Current Constraint

The live registry alpha is API-only. It is protected by an HMAC bearer secret
and restricted ingress, which is appropriate for internal smoke tests but not
safe for a browser application. A browser build needs a thin authenticated
gateway before it can create songs, reserve exports, finalize exports, or post
verification events.

## Target AWS Alpha Architecture

- [x] Create one Cognito user pool draft for alpha users.
- [x] Create one public app client draft with authorization-code flow plus PKCE.
- [x] Use Cognito managed login for the first alpha instead of custom password
  screens.
- [~] Add a small registry gateway behind HTTPS.
- [~] Have the gateway validate Cognito JWTs, map users to tenants and roles,
  and sign internal registry requests server-side.
- [ ] Keep the registry service private to the gateway once browser traffic is
  enabled.
- [ ] Keep source audio local or explicitly design an upload policy before
  accepting media in the web app.

## Surface Checklist

### Public Page

- [x] Existing visual story page exists.
- [x] Add a link to the web alpha shell.
- [ ] Add a production waitlist/contact capture only after an approved storage
  and email policy exists.
- [ ] Keep public claims aligned with measured evaluations.

### Account Lifecycle

- [x] Configure Cognito user pool in the alpha AWS stack draft.
- [x] Configure hosted domain and callback/logout URL parameters.
- [ ] Define tenant enrollment: invite-only for alpha.
- [ ] Define roles: owner, operator, reviewer.
- [ ] Add device/session audit records for application actions.
- [ ] Add account deletion request flow after retention policy approval.

### Application

- [x] Add a static web alpha shell for product iteration.
- [ ] Connect alpha shell to managed login.
- [x] Add an API Gateway HTTP API event adapter for the registry gateway.
- [ ] Add gateway-backed song creation.
- [ ] Add gateway-backed export reservation and finalization.
- [ ] Add verification-event posting.
- [ ] Add registry health and tenant-isolation smoke checks.
- [ ] Add a no-customer-data demo mode for sales and design review.

## Pitfalls

- **Secret exposure:** The current HMAC registry secret must never ship to the
  browser.
- **CORS is not auth:** Adding CORS to the registry would not make it safe for
  public browser use.
- **Tenant mapping:** Login identity and registry tenant identity need an
  explicit mapping table, not ad hoc email parsing.
- **Audio custody:** A web app can accidentally imply upload/storage. The alpha
  must clearly decide whether source audio stays local, is uploaded briefly, or
  is stored.
- **Account deletion:** Deletion must follow retention and evidence policy. It
  cannot simply erase retained registry facts until counsel approves the model.
- **Claims drift:** Marketing, app copy, and reports must keep the distinction
  between encoding, statistical detection, and attribution review.

## Living Checklist

- [~] Keep the public page, web alpha shell, and registry API as separate layers.
- [x] Add Cognito resources to the AWS alpha template.
- [~] Add the authenticated registry gateway.
- [x] Add the Lambda/API Gateway adapter for already-verified Cognito JWT
  claims.
- [x] Add staged CloudFormation wiring for HTTP API, JWT authorizer, Lambda
  integration, tenant mapping, and gateway database access.
- [ ] Move public browser traffic through the gateway only.
- [ ] Add local UI smoke checks for the web alpha shell.
- [ ] Run hosted auth callback smoke tests after Cognito is deployed.
- [ ] Run live tenant-isolation probes before inviting outside users.
- [ ] Keep pilot/customer data blocked until image risk and production gates are
  cleared.

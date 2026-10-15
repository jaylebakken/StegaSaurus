"""Expose the Saurus web-to-registry gateway boundary.

The gateway is the server-side bridge between a browser login session and the
private registry API. Browsers present Cognito-issued JWTs to this layer; the
gateway validates identity through an injected verifier, maps the user to a
tenant-scoped registry principal, and signs the private registry request with
server-held credentials.

It does not perform audio encoding, retained-record storage, or public web
crawling. Those stay in their existing packages.
"""

from __future__ import annotations

from .gateway import GatewayPrincipal, JwtClaims, JwtVerifier, RegistryGateway, TenantResolver
from .lambda_adapter import StaticTenantResolver, api_request_from_http_api_event, handle_http_api_event, http_api_response_from_api_response, jwt_claims_from_http_api_event

__all__ = [
    "GatewayPrincipal",
    "JwtClaims",
    "JwtVerifier",
    "RegistryGateway",
    "StaticTenantResolver",
    "TenantResolver",
    "api_request_from_http_api_event",
    "handle_http_api_event",
    "http_api_response_from_api_response",
    "jwt_claims_from_http_api_event",
]

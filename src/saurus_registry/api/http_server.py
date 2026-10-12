"""Adapt the registry API router to Python's standard HTTP server.

This module is deliberately small and framework-free. It is useful for local
development and contract tests; production deployment can wrap the same
`RegistryApi` router in a stronger server stack without changing application
policy or audio code.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler

from .contracts import ApiRequest
from .router import RegistryApi


def registry_handler(api: RegistryApi) -> type[BaseHTTPRequestHandler]:
    """Return a stdlib request handler bound to one registry API router."""

    class RegistryHandler(BaseHTTPRequestHandler):
        """Serve versioned registry API requests over HTTP."""

        def do_GET(self) -> None:
            """Handle one GET request."""

            self._handle()

        def do_POST(self) -> None:
            """Handle one POST request."""

            self._handle()

        def _handle(self) -> None:
            """Translate the stdlib handler state into an API request."""

            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else b""
            request = ApiRequest(self.command, self.path, dict(self.headers.items()), body)
            response = api.handle(request)
            self.send_response(response.status)
            for name, value in response.headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(response.body)))
            self.end_headers()
            self.wfile.write(response.body)

    return RegistryHandler

"""Manage desktop registry device credentials behind a storage seam.

The desktop should eventually store short-lived registry credentials in the
operating system credential store. This module defines that boundary and a
memory implementation for tests and local wiring; it does not persist tokens to
project files or recovery receipts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class DeviceCredential:
    """Represent one enrolled desktop registry credential."""

    registry_url: str
    tenant_id: str
    actor_id: str
    bearer_token: str

    def __post_init__(self) -> None:
        """Validate credential identity and token fields."""

        for value, name in (
            (self.registry_url, "registry_url"),
            (self.tenant_id, "tenant_id"),
            (self.actor_id, "actor_id"),
            (self.bearer_token, "bearer_token"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")


class CredentialStore(Protocol):
    """Store and load one desktop registry credential."""

    def save(self, credential: DeviceCredential) -> None:
        """Persist one desktop device credential."""

    def load(self, registry_url: str, tenant_id: str) -> DeviceCredential:
        """Return one stored desktop device credential."""


class MemoryCredentialStore:
    """Keep desktop credentials in memory for tests and local prototypes."""

    def __init__(self) -> None:
        """Initialize an empty credential store."""

        self._credentials: dict[tuple[str, str], DeviceCredential] = {}

    def save(self, credential: DeviceCredential) -> None:
        """Store one credential by registry URL and tenant."""

        self._credentials[(credential.registry_url, credential.tenant_id)] = credential

    def load(self, registry_url: str, tenant_id: str) -> DeviceCredential:
        """Load one credential or raise a clear error."""

        try:
            return self._credentials[(registry_url, tenant_id)]
        except KeyError as error:
            raise ValueError("device credential is not enrolled") from error


@dataclass(slots=True)
class DesktopCredentialManager:
    """Enroll and retrieve desktop registry credentials through a store."""

    store: CredentialStore

    def enroll(self, credential: DeviceCredential) -> DeviceCredential:
        """Save one issued registry credential for later API use."""

        self.store.save(credential)
        return credential

    def credential(self, registry_url: str, tenant_id: str) -> DeviceCredential:
        """Return one enrolled credential."""

        return self.store.load(registry_url, tenant_id)

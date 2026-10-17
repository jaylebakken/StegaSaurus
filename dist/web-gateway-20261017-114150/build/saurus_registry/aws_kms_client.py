"""Adapt AWS KMS SDK clients to the Saurus encode-grant boundary.

The encode-grant provider only needs the KMS `GenerateDataKey` operation. This
module keeps that dependency narrow: production wiring may pass a real boto3 KMS
client, while tests can pass a tiny fake object with the same method. The
adapter does not import boto3 until asked to build a default client, so local
desktop and registry tests remain usable without AWS dependencies installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["AwsKmsClientConfig", "Boto3KmsDataKeyClient"]


@dataclass(frozen=True, slots=True)
class AwsKmsClientConfig:
    """Declare optional AWS KMS client construction settings."""

    region_name: str | None = None
    endpoint_url: str | None = None


class Boto3KmsDataKeyClient:
    """Expose boto3 KMS `generate_data_key` through the local protocol."""

    def __init__(self, kms_client: Any) -> None:
        """Store one AWS KMS client-like object."""

        if not hasattr(kms_client, "generate_data_key"):
            raise TypeError("kms_client must provide generate_data_key")
        self._kms_client = kms_client

    @classmethod
    def from_session(cls, session: Any, config: AwsKmsClientConfig | None = None) -> Boto3KmsDataKeyClient:
        """Build the adapter from a boto3 session-like object."""

        if not hasattr(session, "client"):
            raise TypeError("session must provide client")
        settings = config or AwsKmsClientConfig()
        kwargs: dict[str, str] = {}
        if settings.region_name is not None:
            kwargs["region_name"] = settings.region_name
        if settings.endpoint_url is not None:
            kwargs["endpoint_url"] = settings.endpoint_url
        return cls(session.client("kms", **kwargs))

    @classmethod
    def from_default_session(cls, config: AwsKmsClientConfig | None = None) -> Boto3KmsDataKeyClient:
        """Build the adapter from boto3's default session configuration."""

        try:
            import boto3  # type: ignore[import-not-found]
        except ImportError as error:
            raise RuntimeError("boto3 is required for live AWS KMS grant issuance") from error
        return cls.from_session(boto3.Session(), config)

    def generate_data_key(self, **kwargs: object) -> dict[str, object]:
        """Forward one scoped GenerateDataKey request to AWS KMS."""

        response = self._kms_client.generate_data_key(**kwargs)
        if not isinstance(response, dict):
            raise TypeError("generate_data_key response must be a dictionary")
        return response

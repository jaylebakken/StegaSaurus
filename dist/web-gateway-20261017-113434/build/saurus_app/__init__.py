"""Expose the guided Saurus desktop application package.

The package is intentionally separate from ``stegosaurus.audio.demo_app``.  It
offers the shortest product-shaped path through the existing attribution codec:

    WAV + registry text -> encoded WAV + local registry JSON
    suspicious WAV + registry JSON -> accepted / rejected / abstained result

The JSON file is private verification state.  It is not public metadata and it
does not make blind-discovery, compression, recording, or arbitrary-edit
robustness claims.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"

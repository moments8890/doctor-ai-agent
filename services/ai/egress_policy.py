"""
PHI egress policy gate — controls whether clinical data may be sent to cloud LLM providers.

All LLM cloud-fallback paths must call ``check_cloud_egress()`` before
sending PHI-bearing payloads to external providers.  This is the single
enforcement point for the local-only / cloud-allowed boundary.

Policy is controlled by:
  - ``PHI_CLOUD_EGRESS_ALLOWED`` env var or runtime config key
  - Default: ``false`` (local-only; cloud fallback is blocked)

When egress is blocked, the fallback raises the original local error
instead of silently forwarding clinical context to a cloud provider.
"""

from __future__ import annotations

import os
from typing import Optional

from utils.log import log


_ALLOWED_VALUES = {"1", "true", "yes", "on"}

# Providers that keep data on the local network / same trust boundary.
# Everything else is treated as cloud egress.
_LOCAL_PROVIDERS = frozenset({"ollama", "local", "lmstudio"})


def is_local_provider(provider_name: str) -> bool:
    """Return True if the provider runs on the local network."""
    return provider_name.strip().lower() in _LOCAL_PROVIDERS


def _is_cloud_egress_allowed() -> bool:
    """Check whether PHI egress to cloud providers is permitted."""
    raw = os.environ.get("PHI_CLOUD_EGRESS_ALLOWED", "").strip().lower()
    return raw in _ALLOWED_VALUES


def check_cloud_egress(
    provider_name: str,
    operation: str,
    *,
    original_error: Optional[Exception] = None,
) -> None:
    """Gate check before sending PHI to a cloud provider.

    Args:
        provider_name: Target cloud provider name (e.g., "deepseek", "openai").
        operation: Human-readable operation name for logging (e.g., "routing", "structuring").
        original_error: The original local error that triggered the fallback.

    Raises:
        RuntimeError: If cloud egress is not allowed and original_error is None.
        The original_error: If cloud egress is not allowed and original_error is provided.
    """
    if _is_cloud_egress_allowed():
        log(
            f"[EgressPolicy] ALLOWED cloud egress | provider={provider_name} "
            f"operation={operation}"
        )
        return

    log(
        f"[EgressPolicy] BLOCKED cloud egress | provider={provider_name} "
        f"operation={operation} — set PHI_CLOUD_EGRESS_ALLOWED=true to permit"
    )
    if original_error is not None:
        raise original_error
    raise RuntimeError(
        f"Cloud egress blocked by PHI policy for {operation}. "
        f"Set PHI_CLOUD_EGRESS_ALLOWED=true to allow."
    )

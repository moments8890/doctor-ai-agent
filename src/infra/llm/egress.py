"""
PHI egress policy gate — controls whether clinical data may be sent to LLM providers.

All LLM cloud-fallback paths must call ``check_cloud_egress()`` before
sending PHI-bearing payloads to external providers. This is the single
enforcement point for the local / in-China / cross-border boundary.

Three tiers of provider:

  LOCAL        - runs on the local network / same trust boundary.
                 Always allowed; no flag required.
                 (ollama, local, lmstudio)

  IN_CHINA     - cloud provider hosted inside the PRC. Permitted only
                 when PHI_CLOUD_EGRESS_ALLOWED=true. PIPL data-localization
                 requirements considered satisfied (data stays on Chinese
                 soil, subject to the provider's processing agreement).
                 (tencent_lkeap, siliconflow, dashscope, deepseek)

  CROSS_BORDER - hosted outside the PRC. Permitted only when BOTH
                 PHI_CLOUD_EGRESS_ALLOWED=true AND PHI_CROSS_BORDER_ALLOWED=true,
                 because PIPL Articles 38-40 require explicit consent +
                 a security assessment / standard contract for cross-border
                 transfer of personal information (especially "敏感个人信息"
                 like medical data).
                 (groq, openai, gemini, anthropic, cerebras, sambanova,
                 openrouter, xai)

  UNKNOWN      - any provider not in the lists above. Treated as
                 CROSS_BORDER (fail safe).

When egress is blocked, the fallback raises the original local error
instead of silently forwarding clinical context to a cloud provider.
"""

from __future__ import annotations

import os
from typing import Optional

from utils.log import log


_ALLOWED_VALUES = {"1", "true", "yes", "on"}

_LOCAL_PROVIDERS = frozenset({"ollama", "local", "lmstudio"})

_IN_CHINA_PROVIDERS = frozenset({
    "tencent_lkeap",
    "siliconflow",
    "dashscope",
    "deepseek",
})

_CROSS_BORDER_PROVIDERS = frozenset({
    "groq",
    "openai",
    "gemini",
    "anthropic",
    "cerebras",
    "sambanova",
    "openrouter",
    "xai",
})


def is_local_provider(provider_name: str) -> bool:
    """Return True if the provider runs on the local network."""
    return provider_name.strip().lower() in _LOCAL_PROVIDERS


def is_in_china_provider(provider_name: str) -> bool:
    """Return True if the provider is hosted inside the PRC."""
    return provider_name.strip().lower() in _IN_CHINA_PROVIDERS


def is_cross_border_provider(provider_name: str) -> bool:
    """Return True if the provider is hosted outside the PRC.

    Unknown providers fail safe to True so a typo or new provider doesn't
    bypass the policy.
    """
    name = provider_name.strip().lower()
    if name in _LOCAL_PROVIDERS or name in _IN_CHINA_PROVIDERS:
        return False
    return True


def _is_cloud_egress_allowed() -> bool:
    raw = os.environ.get("PHI_CLOUD_EGRESS_ALLOWED", "").strip().lower()
    return raw in _ALLOWED_VALUES


def _is_cross_border_allowed() -> bool:
    raw = os.environ.get("PHI_CROSS_BORDER_ALLOWED", "").strip().lower()
    return raw in _ALLOWED_VALUES


def check_cloud_egress(
    provider_name: str,
    operation: str,
    *,
    original_error: Optional[Exception] = None,
) -> None:
    """Gate check before sending PHI to a cloud provider.

    Cross-border providers require BOTH PHI_CLOUD_EGRESS_ALLOWED and
    PHI_CROSS_BORDER_ALLOWED. In-China providers only require
    PHI_CLOUD_EGRESS_ALLOWED.

    Raises:
        RuntimeError: If egress is not allowed and original_error is None.
        original_error: If egress is not allowed and original_error is provided.
    """
    cross_border = is_cross_border_provider(provider_name)
    if not _is_cloud_egress_allowed():
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

    if cross_border and not _is_cross_border_allowed():
        log(
            f"[EgressPolicy] BLOCKED cross-border egress | provider={provider_name} "
            f"operation={operation} — set PHI_CROSS_BORDER_ALLOWED=true to permit "
            f"(PIPL Art. 38-40 requires consent + assessment / standard contract)"
        )
        if original_error is not None:
            raise original_error
        raise RuntimeError(
            f"Cross-border egress blocked by PHI policy for {operation}. "
            f"Provider {provider_name} is hosted outside the PRC. "
            f"Set PHI_CROSS_BORDER_ALLOWED=true to allow (requires explicit "
            f"patient consent + PIPL Article 38-40 compliance)."
        )

    tier = "in-china" if not cross_border else "cross-border"
    log(
        f"[EgressPolicy] ALLOWED cloud egress | provider={provider_name} "
        f"tier={tier} operation={operation}"
    )

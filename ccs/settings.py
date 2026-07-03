"""Runtime translations for app-specific configuration."""

from __future__ import annotations

import os

from .errors import CcsError
from .models import ResolvedModel, get_provider_spec


def claude_runtime_env(resolved: ResolvedModel) -> dict[str, str]:
    provider = get_provider_spec(resolved.provider)
    if provider is None:
        raise CcsError(f"unknown provider '{resolved.provider}'")

    env: dict[str, str] = {
        "ANTHROPIC_MODEL": resolved.actual_model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": resolved.actual_model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": resolved.actual_model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": resolved.actual_model,
    }
    if provider.base_url:
        env["ANTHROPIC_BASE_URL"] = provider.base_url
    if resolved.provider != "anthropic" and provider.env_key:
        token = os.environ.get(provider.env_key)
        if not token:
            raise CcsError(f"{provider.env_key} is not set for provider '{resolved.provider}'.")
        if provider.auth_mode == "api-key":
            env["ANTHROPIC_API_KEY"] = token
        else:
            env["ANTHROPIC_AUTH_TOKEN"] = token
    return env


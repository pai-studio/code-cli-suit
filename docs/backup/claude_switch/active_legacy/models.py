"""Provider/model registry for ccs.

This module intentionally stores model mappings only. API keys are read from
environment variables at runtime and are never persisted by ccs.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from . import BUILTIN, PROVIDER_PRESETS, fuzzy_match, load_profiles


PROVIDER_ALIASES: dict[str, str] = {
    "an": "anthropic",
    "anthropic": "anthropic",
    "ds": "deepseek",
    "deepseek": "deepseek",
    "moonshot": "moonshot",
    "or": "openrouter",
    "openrouter": "openrouter",
    "openai": "openai",
    "oa": "openai",
    "mm": "minimax",
    "minimax": "minimax",
}

PREFERRED_PROVIDER_ALIAS = {
    "anthropic": "an",
    "deepseek": "ds",
    "moonshot": "moonshot",
    "openrouter": "or",
    "openai": "openai",
    "minimax": "mm",
}


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    aliases: tuple[str, ...]
    name: str
    base_url: str | None
    env_key: str | None
    auth_mode: str
    desc: str
    env_is_set: bool


@dataclass(frozen=True)
class ModelSpec:
    provider: str
    name: str
    actual_model: str
    aliases: tuple[str, ...]
    legacy_profiles: tuple[str, ...]
    desc: str = ""
    source: Literal["builtin", "custom_mapping"] = "builtin"

    @property
    def model_spec(self) -> str:
        if self.provider == "anthropic" and self.name in {"sonnet", "opus", "haiku", "default"}:
            return self.name
        alias = PREFERRED_PROVIDER_ALIAS.get(self.provider, self.provider)
        return f"{alias}/{self.name}"


@dataclass(frozen=True)
class ResolvedModel:
    input: str
    provider: str
    provider_alias: str
    model: str
    actual_model: str
    canonical: str
    legacy_profile: str | None
    source: Literal["builtin", "legacy_profile", "custom_profile", "custom_mapping"]
    env_key: str | None
    env_is_set: bool


class ModelResolutionError(RuntimeError):
    pass


def _config_dir() -> Path:
    override = os.environ.get("CCS_MODELS_FILE")
    if override:
        return Path(override).expanduser().parent
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base).expanduser() / "ccs"
    return Path.home() / ".ccs"


def custom_models_file() -> Path:
    override = os.environ.get("CCS_MODELS_FILE")
    if override:
        return Path(override).expanduser()
    return _config_dir() / "models.json"


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def normalize_provider(provider: str) -> str | None:
    return PROVIDER_ALIASES.get(provider.lower())


def list_providers() -> list[ProviderSpec]:
    specs: list[ProviderSpec] = []
    for provider_id, cfg in PROVIDER_PRESETS.items():
        aliases = tuple(alias for alias, canonical in PROVIDER_ALIASES.items() if canonical == provider_id)
        env_key = cfg.get("env_key")
        specs.append(
            ProviderSpec(
                id=provider_id,
                aliases=aliases,
                name=cfg.get("name", provider_id),
                base_url=cfg.get("base_url"),
                env_key=env_key,
                auth_mode=cfg.get("auth_mode", "bearer"),
                desc=cfg.get("desc", ""),
                env_is_set=bool(env_key and os.environ.get(env_key)),
            )
        )
    return specs


def get_provider_spec(provider: str) -> ProviderSpec | None:
    canonical = normalize_provider(provider) or provider
    for spec in list_providers():
        if spec.id == canonical:
            return spec
    return None


def _builtin_model_specs() -> list[ModelSpec]:
    return [
        ModelSpec("anthropic", "sonnet", "sonnet", ("sonnet", "an/sonnet", "anthropic/sonnet"), ("sonnet",)),
        ModelSpec("anthropic", "opus", "opus", ("opus", "an/opus", "anthropic/opus"), ("opus", "best")),
        ModelSpec("anthropic", "haiku", "haiku", ("haiku", "an/haiku", "anthropic/haiku"), ("haiku",)),
        ModelSpec("anthropic", "default", "default", ("default", "an/default", "anthropic/default"), ("default",)),
        ModelSpec("anthropic", "opusplan", "opusplan", ("opusplan", "an/opusplan", "anthropic/opusplan"), ("opusplan",)),
        ModelSpec("deepseek", "flash", "deepseek-v4-flash", ("ds/flash", "deepseek/flash"), ("deepseek-flash",)),
        ModelSpec("deepseek", "pro", "deepseek-v4-pro[1m]", ("ds/pro", "deepseek/pro"), ("deepseek-pro",)),
        ModelSpec("openai", "gpt-5", "gpt-5", ("openai/gpt-5", "oa/gpt-5"), ()),
        ModelSpec("minimax", "m2.7", "minimax-m2.7", ("mm/m2.7", "minimax/m2.7"), ("minimax-m2.7",)),
        ModelSpec("moonshot", "kimi-2.6", "kimi-k2.6", ("moonshot/kimi-2.6",), ()),
        ModelSpec(
            "openrouter",
            "kimi-k2.6",
            "moonshotai/kimi-k2.6",
            ("or/kimi-k2.6", "openrouter/kimi-k2.6"),
            ("openrouter/kimi-k2.6",),
        ),
        ModelSpec("openrouter", "glm-5", "z-ai/glm-5", ("or/glm-5", "openrouter/glm-5"), ("openrouter/glm-5",)),
        ModelSpec(
            "openrouter",
            "gemini-2.5-flash",
            "google/gemini-2.5-flash",
            ("or/gemini-2.5-flash", "openrouter/gemini-2.5-flash"),
            ("openrouter/gemini-flash",),
        ),
    ]


def load_custom_model_mappings() -> dict[str, str]:
    raw = _read_json(custom_models_file())
    mappings = raw.get("models", raw)
    if not isinstance(mappings, dict):
        return {}
    result: dict[str, str] = {}
    for key, value in mappings.items():
        if isinstance(key, str) and isinstance(value, str):
            result[key] = value
    return result


def list_models(provider: str | None = None) -> list[ModelSpec]:
    canonical = normalize_provider(provider) if provider else None
    if provider and canonical is None:
        raise ModelResolutionError(f"unknown provider '{provider}'")
    specs = [spec for spec in _builtin_model_specs() if canonical is None or spec.provider == canonical]
    for model_spec, actual_model in sorted(load_custom_model_mappings().items()):
        parsed = _parse_model_spec(model_spec)
        if parsed is None:
            continue
        provider_id, model_name = parsed
        if canonical is not None and provider_id != canonical:
            continue
        specs.append(
            ModelSpec(
                provider_id,
                model_name,
                actual_model,
                (model_spec,),
                (),
                source="custom_mapping",
            )
        )
    return specs


def add_model_mapping(model_spec: str, actual_model: str) -> None:
    parsed = _parse_model_spec(model_spec)
    if parsed is None:
        raise ModelResolutionError("model alias must use provider/model")
    provider, model = parsed
    if not model:
        raise ModelResolutionError("model alias cannot be empty")
    if not actual_model.strip():
        raise ModelResolutionError("actual model cannot be empty")
    mappings = load_custom_model_mappings()
    alias = f"{PREFERRED_PROVIDER_ALIAS.get(provider, provider)}/{model}"
    mappings[alias] = actual_model.strip()
    _write_json(custom_models_file(), {"models": mappings})


def remove_model_mapping(model_spec: str) -> bool:
    parsed = _parse_model_spec(model_spec)
    if parsed is None:
        raise ModelResolutionError("model alias must use provider/model")
    provider, model = parsed
    alias = f"{PREFERRED_PROVIDER_ALIAS.get(provider, provider)}/{model}"
    mappings = load_custom_model_mappings()
    if alias not in mappings:
        return False
    del mappings[alias]
    _write_json(custom_models_file(), {"models": mappings})
    return True


def _parse_model_spec(value: str) -> tuple[str, str] | None:
    if value.count("/") != 1:
        return None
    provider_raw, model = value.split("/", 1)
    provider = normalize_provider(provider_raw)
    if provider is None:
        return None
    model = model.strip()
    if not model:
        return None
    return provider, model


def resolve_model_spec(value: str | None) -> ResolvedModel:
    query = (value or "default").strip()
    if not query:
        query = "default"

    if "/" in query:
        parsed = _parse_model_spec(query)
        if parsed is not None:
            provider, model = parsed
            resolved = _resolve_provider_model(query, provider, model)
            if resolved is not None:
                return resolved
        legacy = _resolve_legacy_profile(query)
        if legacy is not None:
            return legacy
        if parsed is None:
            raise ModelResolutionError(
                f"unknown model spec '{query}'. Use strict provider/model, for example or/kimi-k2.6"
            )
        raise ModelResolutionError(f"unknown model spec '{query}'. Run 'ccs models' to see available models")

    for spec in _builtin_model_specs():
        if query in spec.aliases or query in spec.legacy_profiles or query == spec.name:
            return _resolved_from_spec(query, spec, "builtin", spec.legacy_profiles[0] if spec.legacy_profiles else None)

    legacy = _resolve_legacy_profile(query)
    if legacy is not None:
        return legacy
    raise ModelResolutionError(f"unknown model spec '{query}'. Run 'ccs models' to see available models")


def _resolve_provider_model(query: str, provider: str, model: str) -> ResolvedModel | None:
    canonical_query = f"{PREFERRED_PROVIDER_ALIAS.get(provider, provider)}/{model}"
    for spec in _builtin_model_specs():
        if spec.provider == provider and (model == spec.name or canonical_query in spec.aliases or query in spec.aliases):
            return _resolved_from_spec(query, spec, "builtin", spec.legacy_profiles[0] if spec.legacy_profiles else None)
    mappings = load_custom_model_mappings()
    actual = mappings.get(canonical_query) or mappings.get(query)
    if actual:
        spec = ModelSpec(provider, model, actual, (canonical_query,), (), source="custom_mapping")
        return _resolved_from_spec(query, spec, "custom_mapping", None)
    return None


def _resolve_legacy_profile(query: str) -> ResolvedModel | None:
    profiles = load_profiles()
    matched = fuzzy_match(profiles, query)
    if matched is None:
        return None
    cfg = profiles[matched]
    provider = normalize_provider(str(cfg.get("provider", ""))) or str(cfg.get("provider", "custom"))
    if provider not in PROVIDER_PRESETS:
        provider = str(cfg.get("provider", "custom"))
    spec = ProviderSpec(
        id=provider,
        aliases=(provider,),
        name=provider,
        base_url=None,
        env_key=PROVIDER_PRESETS.get(provider, {}).get("env_key"),
        auth_mode=PROVIDER_PRESETS.get(provider, {}).get("auth_mode", "bearer"),
        desc="",
        env_is_set=bool(PROVIDER_PRESETS.get(provider, {}).get("env_key") and os.environ.get(PROVIDER_PRESETS[provider]["env_key"])),
    )
    preferred = PREFERRED_PROVIDER_ALIAS.get(provider, provider)
    actual = str(cfg.get("model", matched))
    return ResolvedModel(
        input=query,
        provider=provider,
        provider_alias=preferred,
        model=matched,
        actual_model=actual,
        canonical=f"{preferred}/{matched}" if provider != "anthropic" else matched,
        legacy_profile=matched,
        source="legacy_profile" if matched in BUILTIN else "custom_profile",
        env_key=spec.env_key,
        env_is_set=spec.env_is_set,
    )


def _resolved_from_spec(
    query: str,
    spec: ModelSpec,
    source: Literal["builtin", "custom_mapping"],
    legacy_profile: str | None,
) -> ResolvedModel:
    provider = get_provider_spec(spec.provider)
    env_key = provider.env_key if provider else None
    preferred = PREFERRED_PROVIDER_ALIAS.get(spec.provider, spec.provider)
    return ResolvedModel(
        input=query,
        provider=spec.provider,
        provider_alias=preferred,
        model=spec.name,
        actual_model=spec.actual_model,
        canonical=spec.model_spec,
        legacy_profile=legacy_profile,
        source=source,
        env_key=env_key,
        env_is_set=bool(env_key and os.environ.get(env_key)),
    )


def resolved_to_profile(resolved: ResolvedModel) -> dict:
    if resolved.legacy_profile:
        profiles = load_profiles()
        if resolved.legacy_profile in profiles:
            return profiles[resolved.legacy_profile]
    aliases = {
        "haiku": resolved.actual_model,
        "sonnet": resolved.actual_model,
        "opus": resolved.actual_model,
    }
    return {
        "model": resolved.actual_model,
        "provider": resolved.provider,
        "aliases": aliases,
    }


def validate_runtime_key(resolved: ResolvedModel) -> None:
    if resolved.provider in {"anthropic", "custom"}:
        return
    if resolved.env_key and not resolved.env_is_set:
        raise ModelResolutionError(
            f"{resolved.env_key} is not set for provider '{resolved.provider}'. "
            f'Set it with: export {resolved.env_key}="sk-..."'
        )

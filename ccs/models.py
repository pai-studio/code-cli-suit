"""Provider/model registry for ccs."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .errors import CcsError


PROVIDER_ALIASES: dict[str, str] = {
    "an": "anthropic",
    "anthropic": "anthropic",
    "ds": "deepseek",
    "deepseek": "deepseek",
    "mm": "minimax",
    "minimax": "minimax",
    "moonshot": "moonshot",
    "openai": "openai",
    "oa": "openai",
    "or": "openrouter",
    "openrouter": "openrouter",
}

PREFERRED_PROVIDER_ALIAS: dict[str, str] = {
    "anthropic": "an",
    "deepseek": "ds",
    "minimax": "mm",
    "moonshot": "moonshot",
    "openai": "openai",
    "openrouter": "or",
}


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    aliases: tuple[str, ...]
    name: str
    base_url: str | None
    env_key: str | None
    auth_mode: Literal["bearer", "api-key"]
    desc: str

    @property
    def env_is_set(self) -> bool:
        return bool(self.env_key and os.environ.get(self.env_key))


@dataclass(frozen=True)
class ModelSpec:
    provider: str
    name: str
    actual_model: str
    desc: str = ""
    source: Literal["builtin", "custom"] = "builtin"

    @property
    def model_spec(self) -> str:
        alias = PREFERRED_PROVIDER_ALIAS.get(self.provider, self.provider)
        return f"{alias}/{self.name}"


@dataclass(frozen=True)
class ResolvedModel:
    input: str
    provider: str
    provider_alias: str
    name: str
    actual_model: str
    canonical: str
    source: Literal["builtin", "custom"]
    env_key: str | None
    env_is_set: bool


class ModelResolutionError(CcsError):
    pass


PROVIDERS: dict[str, ProviderSpec] = {
    "anthropic": ProviderSpec(
        id="anthropic",
        aliases=("an", "anthropic"),
        name="Anthropic",
        base_url=None,
        env_key="ANTHROPIC_API_KEY",
        auth_mode="bearer",
        desc="Anthropic native models",
    ),
    "deepseek": ProviderSpec(
        id="deepseek",
        aliases=("ds", "deepseek"),
        name="DeepSeek",
        base_url="https://api.deepseek.com/anthropic",
        env_key="DEEPSEEK_API_KEY",
        auth_mode="bearer",
        desc="DeepSeek Anthropic-compatible endpoint",
    ),
    "minimax": ProviderSpec(
        id="minimax",
        aliases=("mm", "minimax"),
        name="MiniMax",
        base_url="https://api.minimax.io/anthropic",
        env_key="MINIMAX_API_KEY",
        auth_mode="bearer",
        desc="MiniMax Anthropic-compatible endpoint",
    ),
    "moonshot": ProviderSpec(
        id="moonshot",
        aliases=("moonshot",),
        name="Moonshot",
        base_url=None,
        env_key="MOONSHOT_API_KEY",
        auth_mode="bearer",
        desc="Moonshot provider",
    ),
    "openai": ProviderSpec(
        id="openai",
        aliases=("openai", "oa"),
        name="OpenAI",
        base_url=None,
        env_key="OPENAI_API_KEY",
        auth_mode="bearer",
        desc="OpenAI provider",
    ),
    "openrouter": ProviderSpec(
        id="openrouter",
        aliases=("or", "openrouter"),
        name="OpenRouter",
        base_url="https://openrouter.ai/api",
        env_key="OPENROUTER_API_KEY",
        auth_mode="bearer",
        desc="OpenRouter provider",
    ),
}


BUILTIN_MODELS: tuple[ModelSpec, ...] = (
    ModelSpec("anthropic", "sonnet", "sonnet", "Claude Sonnet"),
    ModelSpec("anthropic", "opus", "opus", "Claude Opus"),
    ModelSpec("anthropic", "haiku", "haiku", "Claude Haiku"),
    ModelSpec("deepseek", "flash", "deepseek-v4-flash", "DeepSeek flash"),
    ModelSpec("deepseek", "pro", "deepseek-v4-pro[1m]", "DeepSeek pro"),
    ModelSpec("minimax", "m2.7", "minimax-m2.7", "MiniMax M2.7"),
    ModelSpec("moonshot", "kimi-2.6", "kimi-k2.6", "Moonshot Kimi"),
    ModelSpec("openai", "gpt-5", "gpt-5", "OpenAI GPT-5"),
    ModelSpec("openrouter", "kimi-k2.6", "moonshotai/kimi-k2.6", "OpenRouter Kimi"),
    ModelSpec("openrouter", "glm-5", "z-ai/glm-5", "OpenRouter GLM"),
    ModelSpec("openrouter", "gemini-2.5-flash", "google/gemini-2.5-flash", "OpenRouter Gemini"),
)


def ccs_home() -> Path:
    override = os.environ.get("CCS_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".ccs"


def custom_models_file() -> Path:
    override = os.environ.get("CCS_MODELS_FILE")
    if override:
        return Path(override).expanduser()
    return ccs_home() / "models.json"


def normalize_provider(provider: str) -> str | None:
    return PROVIDER_ALIASES.get(provider.strip().lower())


def preferred_provider_alias(provider: str) -> str:
    return PREFERRED_PROVIDER_ALIAS.get(provider, provider)


def get_provider_spec(provider: str) -> ProviderSpec | None:
    canonical = normalize_provider(provider) or provider
    return PROVIDERS.get(canonical)


def list_providers() -> list[ProviderSpec]:
    return [PROVIDERS[key] for key in sorted(PROVIDERS)]


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


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


def _parse_model_spec(value: str) -> tuple[str, str] | None:
    if value.count("/") != 1:
        return None
    provider_raw, model = value.split("/", 1)
    provider = normalize_provider(provider_raw)
    model = model.strip()
    if provider is None or not model:
        return None
    return provider, model


def list_models(provider: str | None = None) -> list[ModelSpec]:
    canonical = normalize_provider(provider) if provider else None
    if provider and canonical is None:
        raise ModelResolutionError(f"unknown provider '{provider}'")

    specs = [spec for spec in BUILTIN_MODELS if canonical is None or spec.provider == canonical]
    for model_spec, actual in sorted(load_custom_model_mappings().items()):
        parsed = _parse_model_spec(model_spec)
        if parsed is None:
            continue
        provider_id, name = parsed
        if canonical is not None and provider_id != canonical:
            continue
        specs.append(ModelSpec(provider_id, name, actual, source="custom"))
    return specs


def add_model_mapping(model_spec: str, actual_model: str) -> None:
    parsed = _parse_model_spec(model_spec)
    if parsed is None:
        raise ModelResolutionError("model alias must use provider/model")
    provider, name = parsed
    actual = actual_model.strip()
    if not actual:
        raise ModelResolutionError("actual model cannot be empty")
    canonical = f"{preferred_provider_alias(provider)}/{name}"
    mappings = load_custom_model_mappings()
    mappings[canonical] = actual
    _write_json(custom_models_file(), {"models": mappings})


def remove_model_mapping(model_spec: str) -> bool:
    parsed = _parse_model_spec(model_spec)
    if parsed is None:
        raise ModelResolutionError("model alias must use provider/model")
    provider, name = parsed
    canonical = f"{preferred_provider_alias(provider)}/{name}"
    mappings = load_custom_model_mappings()
    if canonical not in mappings:
        return False
    del mappings[canonical]
    _write_json(custom_models_file(), {"models": mappings})
    return True


def resolve_model_spec(value: str) -> ResolvedModel:
    query = value.strip()
    parsed = _parse_model_spec(query)
    if parsed is None:
        raise ModelResolutionError(
            f"unknown model '{value}'. Use provider/model, for example ds/flash or openai/gpt-5."
        )

    provider, name = parsed
    canonical = f"{preferred_provider_alias(provider)}/{name}"
    for spec in BUILTIN_MODELS:
        if spec.provider == provider and spec.name == name:
            return _resolved_from_spec(query, spec)

    actual = load_custom_model_mappings().get(canonical)
    if actual:
        return _resolved_from_spec(query, ModelSpec(provider, name, actual, source="custom"))

    raise ModelResolutionError(f"unknown model '{value}'. Run 'ccs models' to see available models.")


def _resolved_from_spec(query: str, spec: ModelSpec) -> ResolvedModel:
    provider = get_provider_spec(spec.provider)
    alias = preferred_provider_alias(spec.provider)
    env_key = provider.env_key if provider else None
    return ResolvedModel(
        input=query,
        provider=spec.provider,
        provider_alias=alias,
        name=spec.name,
        actual_model=spec.actual_model,
        canonical=spec.model_spec,
        source=spec.source,
        env_key=env_key,
        env_is_set=bool(env_key and os.environ.get(env_key)),
    )


def validate_model_known(value: str) -> None:
    resolve_model_spec(value)


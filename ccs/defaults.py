"""Default model configuration."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .models import ccs_home


@dataclass
class Defaults:
    global_model: str | None = None
    app_models: dict[str, str] = field(default_factory=dict)


def config_file() -> Path:
    override = os.environ.get("CCS_CONFIG_FILE")
    if override:
        return Path(override).expanduser()
    return ccs_home() / "config.toml"


def load_defaults(path: Path | None = None) -> Defaults:
    path = path or config_file()
    try:
        text = path.read_text()
    except FileNotFoundError:
        return Defaults()

    current_section = ""
    result = Defaults()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line == "[apps]":
            current_section = "apps"
            continue
        if line.startswith("[") and line.endswith("]"):
            current_section = line.strip("[]")
            continue
        if "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        parsed = _parse_toml_string(value)
        if parsed is None:
            continue
        if current_section == "apps":
            result.app_models[key] = parsed
        elif key == "default_model":
            result.global_model = parsed
    return result


def save_defaults(defaults: Defaults, path: Path | None = None) -> None:
    path = path or config_file()
    lines: list[str] = []
    if defaults.global_model:
        lines.append(f"default_model = {json.dumps(defaults.global_model)}")
        lines.append("")
    lines.append("[apps]")
    for app, model in sorted(defaults.app_models.items()):
        lines.append(f"{app} = {json.dumps(model)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(lines).rstrip() + "\n")
    tmp.replace(path)


def set_default_model(model: str, app: str | None = None) -> Defaults:
    defaults = load_defaults()
    if app:
        defaults.app_models[app] = model
    else:
        defaults.global_model = model
    save_defaults(defaults)
    return defaults


def get_default_model(app: str) -> str | None:
    defaults = load_defaults()
    return defaults.app_models.get(app) or defaults.global_model


def _parse_toml_string(value: str) -> str | None:
    value = value.strip()
    if len(value) < 2 or value[0] != '"' or value[-1] != '"':
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, str) else None


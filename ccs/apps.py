"""Application specs and launch-plan construction."""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path

from . import memory
from .errors import CcsError
from .models import ResolvedModel, resolve_model_spec
from .settings import claude_runtime_env


APP_NAMES = ("claude", "codex", "opencode")
QUICK_MODES = ("auto", "danger", "plan")


@dataclass(frozen=True)
class AppSpec:
    name: str
    executable: str
    native_model_flags: tuple[str, ...]
    native_mode_flags: tuple[str, ...]
    value_flags: tuple[str, ...]
    mode_mappings: dict[str, tuple[str, ...] | None]
    passthrough_heads: tuple[str, ...] = ("--help", "-h", "help", "auth", "doctor", "mcp")
    supported_providers: tuple[str, ...] | None = None


@dataclass(frozen=True)
class LaunchRequest:
    app: str
    native_args: list[str]
    ccs_model: str | None = None
    default_model: str | None = None
    quick_mode: str | None = None
    memory_enabled: bool = True
    dry_run: bool = False
    cwd: Path = field(default_factory=lambda: Path.cwd())


@dataclass(frozen=True)
class LaunchPlan:
    executable: str
    argv: list[str]
    env: dict[str, str]
    cwd: Path
    runtime_files: tuple[Path, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def command(self) -> list[str]:
        return [self.executable, *self.argv]

    def shell_command(self) -> str:
        return shlex.join(self.command)


APPS: dict[str, AppSpec] = {
    "claude": AppSpec(
        name="claude",
        executable="claude",
        native_model_flags=("--model",),
        native_mode_flags=("--permission-mode", "--dangerously-skip-permissions"),
        value_flags=("--model", "--permission-mode", "--append-system-prompt", "--settings", "--add-dir", "--name"),
        mode_mappings={
            "auto": ("--permission-mode", "auto"),
            "danger": ("--dangerously-skip-permissions",),
            "plan": ("--permission-mode", "plan"),
        },
        supported_providers=("anthropic", "deepseek", "minimax", "openrouter"),
    ),
    "codex": AppSpec(
        name="codex",
        executable="codex",
        native_model_flags=("--model", "-m"),
        native_mode_flags=("--ask-for-approval", "--dangerously-bypass-approvals-and-sandbox"),
        value_flags=("--model", "-m", "--sandbox", "--ask-for-approval", "--cd", "-C", "--add-dir"),
        mode_mappings={
            "auto": ("--ask-for-approval", "never"),
            "danger": ("--dangerously-bypass-approvals-and-sandbox",),
            "plan": None,
        },
        passthrough_heads=("--help", "-h", "help", "auth"),
        supported_providers=("openai",),
    ),
    "opencode": AppSpec(
        name="opencode",
        executable="opencode",
        native_model_flags=("--model", "-m"),
        native_mode_flags=("--auto",),
        value_flags=("--model", "-m", "--prompt", "-p", "--file", "-f"),
        mode_mappings={
            "auto": ("--auto",),
            "danger": ("--auto",),
            "plan": None,
        },
        passthrough_heads=("--help", "-h", "help", "auth"),
        supported_providers=None,
    ),
}


def get_app(name: str) -> AppSpec:
    try:
        return APPS[name]
    except KeyError as exc:
        raise CcsError(f"unknown app '{name}'. Supported apps: {', '.join(APP_NAMES)}.") from exc


def build_launch_plan(request: LaunchRequest) -> LaunchPlan:
    spec = get_app(request.app)
    if request.quick_mode and request.quick_mode not in QUICK_MODES:
        raise CcsError(f"unknown quick mode '{request.quick_mode}'")

    native_args = list(request.native_args)
    if is_passthrough_only(spec, native_args) and not request.ccs_model and not request.quick_mode:
        return LaunchPlan(spec.executable, native_args, {}, request.cwd.resolve())

    if request.ccs_model and has_any_flag(native_args, spec.native_model_flags):
        raise CcsError("model is specified twice: --cc-model and native model flag.")

    if request.quick_mode and has_any_flag(native_args, spec.native_mode_flags):
        raise CcsError(f"mode is specified twice: --cc-{request.quick_mode} and native mode flag.")

    model_value = request.ccs_model or (None if has_any_flag(native_args, spec.native_model_flags) else request.default_model)
    argv: list[str] = []
    env: dict[str, str] = {}
    warnings: list[str] = []

    if model_value:
        resolved = resolve_model_spec(model_value)
        _validate_provider_supported(spec, resolved)
        model_args, model_env = _model_args(spec, resolved)
        argv.extend(model_args)
        env.update(model_env)

    if request.quick_mode:
        mode_args = spec.mode_mappings.get(request.quick_mode)
        if mode_args is None:
            raise CcsError(f"--cc-{request.quick_mode} is not supported for {spec.name}.")
        argv.extend(mode_args)
        if spec.name == "opencode" and request.quick_mode == "danger":
            warnings.append("opencode has no stronger danger flag; --cc-danger expands to --auto.")

    if request.memory_enabled:
        paths = memory.prepare_memory(request.cwd, create=not request.dry_run)
        prompt = memory.prelude(paths)
        native_args = _inject_memory(spec, native_args, prompt)

    argv.extend(native_args)
    return LaunchPlan(spec.executable, argv, env, request.cwd.resolve(), warnings=tuple(warnings))


def is_passthrough_only(spec: AppSpec, native_args: list[str]) -> bool:
    if not native_args:
        return False
    head = native_args[0]
    return head in spec.passthrough_heads or head.startswith("--help")


def has_any_flag(args: list[str], flags: tuple[str, ...]) -> bool:
    for arg in args:
        for flag in flags:
            if arg == flag or arg.startswith(flag + "="):
                return True
    return False


def _validate_provider_supported(spec: AppSpec, resolved: ResolvedModel) -> None:
    if spec.supported_providers is not None and resolved.provider not in spec.supported_providers:
        supported = ", ".join(spec.supported_providers)
        raise CcsError(f"{spec.name} does not support provider '{resolved.provider}'. Supported providers: {supported}.")


def _model_args(spec: AppSpec, resolved: ResolvedModel) -> tuple[list[str], dict[str, str]]:
    if spec.name == "claude":
        return ["--model", resolved.actual_model], claude_runtime_env(resolved)
    if spec.name == "codex":
        return ["--model", resolved.actual_model], {}
    if spec.name == "opencode":
        return ["--model", f"{resolved.provider}/{resolved.actual_model}"], {}
    raise CcsError(f"unsupported app '{spec.name}'")


def _inject_memory(spec: AppSpec, args: list[str], prompt: str) -> list[str]:
    if spec.name == "claude":
        return _inject_value_flag(args, "--append-system-prompt", prompt, spec.value_flags)
    if spec.name == "codex":
        if args and args[0] == "exec":
            return ["exec", *_inject_positional_prompt(args[1:], prompt, spec.value_flags)]
        return _inject_positional_prompt(args, prompt, spec.value_flags)
    if spec.name == "opencode":
        if args and args[0] == "run":
            return ["run", *_inject_positional_prompt(args[1:], prompt, spec.value_flags)]
        return _inject_value_flag(args, "--prompt", prompt, spec.value_flags, aliases=("-p",))
    raise CcsError(f"memory injection is not supported for {spec.name}.")


def _inject_value_flag(
    args: list[str],
    flag: str,
    prompt: str,
    value_flags: tuple[str, ...],
    *,
    aliases: tuple[str, ...] = (),
) -> list[str]:
    flags = (flag, *aliases)
    result = list(args)
    for idx, arg in enumerate(result):
        for candidate in flags:
            prefix = candidate + "="
            if arg.startswith(prefix):
                old = arg[len(prefix) :]
                result[idx] = f"{candidate}={_combine_prompt(prompt, old)}"
                return result
            if arg == candidate:
                if idx + 1 >= len(result):
                    raise CcsError(f"{candidate} requires a value")
                result[idx + 1] = _combine_prompt(prompt, result[idx + 1])
                return result
    result.extend([flag, prompt])
    return result


def _inject_positional_prompt(args: list[str], prompt: str, value_flags: tuple[str, ...]) -> list[str]:
    result: list[str] = []
    idx = 0
    while idx < len(args):
        arg = args[idx]
        if arg == "--":
            existing = " ".join(args[idx + 1 :]).strip()
            result.append(_combine_prompt(prompt, existing) if existing else prompt)
            return result
        if arg.startswith("-"):
            result.append(arg)
            if _flag_takes_value(arg, value_flags):
                if idx + 1 >= len(args):
                    raise CcsError(f"{arg} requires a value")
                result.append(args[idx + 1])
                idx += 2
                continue
            idx += 1
            continue
        existing = " ".join(args[idx:]).strip()
        result.append(_combine_prompt(prompt, existing))
        return result
    result.append(prompt)
    return result


def _flag_takes_value(arg: str, value_flags: tuple[str, ...]) -> bool:
    if "=" in arg:
        return False
    return arg in value_flags


def _combine_prompt(ccs_prompt: str, user_prompt: str) -> str:
    user_prompt = user_prompt.strip()
    if not user_prompt:
        return ccs_prompt
    return f"{ccs_prompt}\n\nUser request:\n{user_prompt}"

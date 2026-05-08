"""
claude-switch — switch claude-code models across providers like opencode.
"""
HELP_EN = """\
claude-switch v{V} — multi-provider model switcher for claude-code

QUICK START
  claude-switch                   interactive picker (grouped by provider)
  claude-switch <name>            switch by fuzzy-matching a profile name
  claude-switch sonnet            use a built-in Anthropic profile
  claude-switch -                 go back to the previous model

ADDING PROFILES
  claude-switch add <name> <model> -p <PROVIDER>
      --haiku MODEL   /model haiku → MODEL  (default: <model>)
      --sonnet MODEL  /model sonnet → MODEL
      --opus MODEL    /model opus → MODEL
      -t, --auth-token TOKEN  explicit API token

  Examples:
    claude-switch add dp deepseek-v4-pro -p deepseek
    claude-switch add dp deepseek-v4-pro -p deepseek --haiku deepseek-v4-flash
    claude-switch add or-sonnet anthropic/claude-sonnet-4-20250514 -p openrouter

SUBCOMMANDS
  list             list all profiles (grouped by provider)
  show             show active model across 3 layers (local > project > user)
  show <name>      show a profile's full config: auth source, aliases, translation
  log              show switch history
  providers        list known providers (built-in + custom)
  rm <name>        delete a custom profile
  add-provider <name> <base_url> [--env-key KEY]

SCOPES (where settings are written)
  (default)        project   <project>/.claude/settings.json
  -l, --local      local     <project>/.claude/settings.local.json
  -u, --user       user      ~/.claude/settings.json

ADVANCED
  --dry-run <name>  print the settings.json but don't write
  --preview         show diff and confirm before writing
  --help-zh         中文帮助

BUILT-IN PROVIDERS
  anthropic   (native)           $ANTHROPIC_API_KEY
  deepseek    api.deepseek.com   $DEEPSEEK_API_KEY
  minimax     api.minimax.io     $MINIMAX_API_KEY
  openrouter  openrouter.ai/api  $OPENROUTER_API_KEY

CONFIG FILES
  ~/.claude-switch-profiles.json
  ~/.claude-switch-providers.json
  ~/.claude-switch-history.json
"""

HELP_ZH = """\
claude-switch v{V} — claude-code 多 provider 模型切换器

快速上手
  claude-switch                   交互式选择 (按 provider 分组)
  claude-switch <name>            前缀模糊匹配切换 profile
  claude-switch sonnet            使用内置 Anthropic profile
  claude-switch -                 回退到上一个模型

添加 profile
  claude-switch add <name> <model> -p <PROVIDER>
      --haiku MODEL    /model haiku → MODEL  (默认: 同 <model>)
      --sonnet MODEL   /model sonnet → MODEL
      --opus MODEL     /model opus → MODEL
      -t, --auth-token TOKEN  显式 API token

  示例:
    claude-switch add dp deepseek-v4-pro -p deepseek
    claude-switch add dp deepseek-v4-pro -p deepseek --haiku deepseek-v4-flash
    claude-switch add or-sonnet anthropic/claude-sonnet-4-20250514 -p openrouter

子命令
  list             列出所有 profile (按 provider 分组)
  show             显示三层覆盖: local > project > user
  show <name>      展示 profile 完整配置 (认证来源/别名/翻译结果)
  log              切换历史
  providers        列出已知 provider (内置 + 自定义)
  rm <name>        删除自定义 profile
  add-provider <name> <base_url> [--env-key KEY]

作用域 (写入目标)
  (默认)           项目级   <project>/.claude/settings.json
  -l, --local      本地级   <project>/.claude/settings.local.json
  -u, --user       用户级   ~/.claude/settings.json

高级
  --dry-run <name>  仅输出 settings.json 内容, 不写入
  --preview         预览并确认后再写入
  --help-zh         中文帮助

内置 Provider
  anthropic   (原生)           $ANTHROPIC_API_KEY
  deepseek    api.deepseek.com $DEEPSEEK_API_KEY
  minimax     api.minimax.io   $MINIMAX_API_KEY
  openrouter  openrouter.ai    $OPENROUTER_API_KEY

配置文件
  ~/.claude-switch-profiles.json
  ~/.claude-switch-providers.json
  ~/.claude-switch-history.json
"""


import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.5.0"
HOME = Path.home()
PROFILES_FILE  = HOME / ".claude-switch-profiles.json"
PROVIDERS_FILE = HOME / ".claude-switch-providers.json"
HISTORY_FILE   = HOME / ".claude-switch-history.json"
USER_SETTINGS  = HOME / ".claude" / "settings.json"

PROVIDER_PRESETS = {
    "anthropic": {
        "name": "Anthropic",
        "base_url": None,
        "env_key": "ANTHROPIC_API_KEY",
        "auth_mode": "bearer",
        "desc": "原生 Anthropic API, 无需额外配置",
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/anthropic",
        "env_key": "DEEPSEEK_API_KEY",
        "auth_mode": "bearer",
        "desc": "DeepSeek Anthropic-compatible 端点",
    },
    "minimax": {
        "name": "MiniMax",
        "base_url": "https://api.minimax.io/anthropic",
        "env_key": "MINIMAX_API_KEY",
        "auth_mode": "bearer",
        "desc": "MiniMax Anthropic-compatible 端点",
    },
    "openrouter": {
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api",
        "env_key": "OPENROUTER_API_KEY",
        "auth_mode": "bearer",
        "desc": "OpenRouter Anthropic-compatible 端点, 支持 200+ 模型",
    },
    "openai": {
        "name": "OpenAI",
        "base_url": None,
        "env_key": "OPENAI_API_KEY",
        "auth_mode": "bearer",
        "desc": "OpenAI API",
    },
}

BUILTIN = {
    "sonnet":   {"model": "sonnet",   "provider": "anthropic", "aliases": {"haiku": "haiku", "sonnet": "sonnet", "opus": "opus"}},
    "opus":     {"model": "opus",     "provider": "anthropic", "aliases": {"haiku": "haiku", "sonnet": "sonnet", "opus": "opus"}},
    "haiku":    {"model": "haiku",    "provider": "anthropic", "aliases": {"haiku": "haiku", "sonnet": "sonnet", "opus": "opus"}},
    "best":     {"model": "opus",     "provider": "anthropic", "aliases": {"haiku": "haiku", "sonnet": "sonnet", "opus": "opus"}},
    "default":  {"model": "default",  "provider": "anthropic", "aliases": {"haiku": "haiku", "sonnet": "sonnet", "opus": "opus"}},
    "opusplan": {"model": "opusplan", "provider": "anthropic", "aliases": {"haiku": "haiku", "sonnet": "sonnet", "opus": "opus"}},
    "deepseek-pro":    {"model": "deepseek-v4-pro[1m]", "provider": "deepseek",   "aliases": {"haiku": "deepseek-v4-flash",  "sonnet": "deepseek-v4-pro[1m]", "opus": "deepseek-v4-pro[1m]"}, "subagent_model": "deepseek-v4-flash", "effort_level": "max"},
    "deepseek-flash":  {"model": "deepseek-v4-flash",  "provider": "deepseek",   "aliases": {"haiku": "deepseek-v4-flash",  "sonnet": "deepseek-v4-flash",  "opus": "deepseek-v4-flash"}},
    "minimax-m2.7":    {"model": "minimax-m2.7",       "provider": "minimax",    "aliases": {"haiku": "minimax-m2.7",       "sonnet": "minimax-m2.7",       "opus": "minimax-m2.7"}},
    "openrouter/glm-5":          {"model": "z-ai/glm-5",            "provider": "openrouter", "aliases": {"haiku": "z-ai/glm-5",            "sonnet": "z-ai/glm-5",            "opus": "z-ai/glm-5"}},
    "openrouter/kimi-k2.6":     {"model": "moonshotai/kimi-k2.6",   "provider": "openrouter", "aliases": {"haiku": "moonshotai/kimi-k2.6",   "sonnet": "moonshotai/kimi-k2.6",   "opus": "moonshotai/kimi-k2.6"}},
    "openrouter/gemini-flash":  {"model": "google/gemini-2.5-flash","provider": "openrouter", "aliases": {"haiku": "google/gemini-2.5-flash","sonnet": "google/gemini-2.5-flash","opus": "google/gemini-2.5-flash"}},
}
BUILTIN_NAMES = set(BUILTIN.keys())

NON_MODEL_KEYS = {"alwaysThinkingEnabled"}

MIGRATIONS = [
    (HOME / ".cc-switch-profiles.json",  HOME / ".claude-switch-profiles.json"),
    (HOME / ".cc-switch-providers.json", HOME / ".claude-switch-providers.json"),
    (HOME / ".cc-switch-history.json",   HOME / ".claude-switch-history.json"),
]


def _migrate_legacy() -> None:
    for old, new in MIGRATIONS:
        if old.exists() and not new.exists():
            new.write_text(old.read_text())


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def err(msg: str) -> None:
    print(f"claude-switch: {msg}", file=sys.stderr)


def find_project_root() -> Path:
    d = Path.cwd().resolve()
    while True:
        if (d / ".claude").is_dir():
            return d
        if d.parent == d:
            break
        d = d.parent
    return Path.cwd().resolve()


def load_providers() -> dict:
    combined = {}
    for k, v in PROVIDER_PRESETS.items():
        combined[k] = dict(v)
    if PROVIDERS_FILE.exists():
        try:
            custom = json.loads(PROVIDERS_FILE.read_text())
            for k, v in custom.items():
                if k in PROVIDER_PRESETS:
                    merged = dict(PROVIDER_PRESETS[k])
                    merged["env_key"] = v.get("env_key", merged["env_key"])
                    merged["name"] = v.get("name", merged["name"])
                    merged["desc"] = v.get("desc", merged.get("desc", ""))
                    combined[k] = merged
                else:
                    combined[k] = v
        except json.JSONDecodeError:
            err(f"\u26a0 {PROVIDERS_FILE} 格式错误, 已忽略")
    return combined


def get_provider(name: str) -> dict:
    return load_providers().get(name, {})


def provider_env_key(name: str) -> str | None:
    return get_provider(name).get("env_key")


def resolve_auth_token(profile: dict) -> str | None:
    if profile.get("auth_token"):
        return profile["auth_token"]
    if profile.get("auth", {}).get("token"):
        return profile["auth"]["token"]
    env_key = provider_env_key(profile.get("provider", ""))
    if env_key:
        val = os.environ.get(env_key)
        if val:
            return val
    if profile.get("api_key"):
        return profile["api_key"]
    return None


def resolve_base_url(profile: dict) -> str | None:
    provider_name = profile.get("provider", "custom")
    provider = get_provider(provider_name)
    if provider_name in PROVIDER_PRESETS:
        return provider.get("base_url")
    return profile.get("base_url") or provider.get("base_url")


def auth_source_label(profile: dict) -> str:
    if profile.get("auth_token"):
        return "profile 显式"
    if profile.get("api_key"):
        return "profile.api_key"
    env_key = provider_env_key(profile.get("provider", ""))
    if env_key and os.environ.get(env_key):
        return f"${env_key}"
    if env_key:
        return f"${env_key} (未设置)"
    return "(未设置)"


def profile_to_settings(profile: dict) -> dict:
    result: dict = {}
    env: dict = {}

    model = profile.get("model")
    if not model:
        return result

    result["model"] = model
    env["ANTHROPIC_MODEL"] = model

    base_url = resolve_base_url(profile)
    if base_url:
        env["ANTHROPIC_BASE_URL"] = base_url

    token = resolve_auth_token(profile)
    if token:
        auth_mode = profile.get("auth", {}).get("type") or \
                    get_provider(profile.get("provider", "")).get("auth_mode", "bearer")
        if auth_mode == "api-key":
            env["ANTHROPIC_API_KEY"] = token
        else:
            env["ANTHROPIC_AUTH_TOKEN"] = token

    aliases = profile.get("aliases", {})
    if aliases.get("opus"):
        env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = aliases["opus"]
    if aliases.get("sonnet"):
        env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = aliases["sonnet"]
    if aliases.get("haiku"):
        env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = aliases["haiku"]

    if profile.get("subagent_model"):
        env["CLAUDE_CODE_SUBAGENT_MODEL"] = profile["subagent_model"]
    if profile.get("effort_level"):
        env["CLAUDE_CODE_EFFORT_LEVEL"] = profile["effort_level"]

    s = profile.get("settings", {})
    if s.get("alwaysThinkingEnabled") is not None:
        result["alwaysThinkingEnabled"] = s["alwaysThinkingEnabled"]
    if s.get("apiTimeoutMs"):
        env["API_TIMEOUT_MS"] = str(s["apiTimeoutMs"])
    if s.get("disableNonessentialTraffic"):
        env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"

    raw = profile.get("raw", {})
    result.update(raw)

    if env:
        result["env"] = env
    return result


def apply_profile(settings_path: Path, profile: dict) -> None:
    data = profile_to_settings(profile)
    cur = read_json(settings_path)
    for k in NON_MODEL_KEYS:
        if k in cur and k not in data:
            del cur[k]
    cur.update(data)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(cur, indent=2) + "\n")
    settings_path.chmod(0o600)


def normalize_profile(v) -> dict:
    if isinstance(v, str):
        return {"model": v, "provider": "custom"}
    return v


def load_profiles() -> dict:
    combined = dict(BUILTIN)
    if PROFILES_FILE.exists():
        try:
            custom = json.loads(PROFILES_FILE.read_text())
            for k, v in custom.items():
                combined[k] = normalize_profile(v)
        except json.JSONDecodeError:
            err(f"\u26a0 {PROFILES_FILE} 格式错误, 已忽略")
    return combined


def profile_provider_label(name: str, cfg: dict) -> str:
    prov = cfg.get("provider", "custom")
    return get_provider(prov).get("name", prov.capitalize())


MAX_HISTORY = 50


def read_history() -> list:
    try:
        return json.loads(HISTORY_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def write_history(entries: list) -> None:
    HISTORY_FILE.write_text(json.dumps(entries[-MAX_HISTORY:], indent=2) + "\n")


def record_switch(profile_name: str, scope: str, path: Path) -> None:
    entries = read_history()
    entries.append({
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "profile": profile_name, "scope": scope, "path": str(path),
    })
    write_history(entries)


def get_previous_profile() -> str | None:
    entries = read_history()
    return entries[-2]["profile"] if len(entries) >= 2 else None


def fuzzy_match(profiles: dict, query: str) -> str | None:
    if query in profiles:
        return query
    lower = query.lower()
    for name in profiles:
        if name.lower().startswith(lower):
            return name
    for name in profiles:
        if lower in name.lower():
            return name
    return None


def switch_auth_info(cfg: dict) -> str:
    token = resolve_auth_token(cfg)
    if token:
        return " (token: 已设置)"
    env_key = provider_env_key(cfg.get("provider", ""))
    if env_key:
        return f" (token: ${env_key})"
    return ""


def do_switch(profile_name: str, scope: str, path: Path, label: str,
              dry_run: bool = False, preview: bool = False) -> None:
    profiles = load_profiles()
    matched = fuzzy_match(profiles, profile_name)
    if matched is None:
        err(f"未找到 profile '{profile_name}'")
        print("  tip: 'claude-switch list' 查看所有可选 profile", file=sys.stderr)
        sys.exit(1)
    cfg = profiles[matched]

    if dry_run:
        data = profile_to_settings(cfg)
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    if preview:
        data = profile_to_settings(cfg)
        print("将要写入:\n")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"\n目标: {path}")
        try:
            ans = input("确认写入? [Y/n] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if ans and ans not in ("y", "yes"):
            print("已取消")
            return

    apply_profile(path, cfg)
    record_switch(matched, scope, path)
    print(f"[{label}]  \u2192  {cfg['model']}{switch_auth_info(cfg)}")

    env_key = provider_env_key(cfg.get("provider", ""))
    has_explicit_token = cfg.get("auth_token") or cfg.get("auth", {}).get("token") or cfg.get("api_key")
    if env_key and not has_explicit_token and not os.environ.get(env_key):
        print(f"\n  \u26a0  ${env_key} 未设置")
        print(f"  export {env_key}=\"your-key\"")
        print(f"  source ~/.zshrc  # 或 ~/.bashrc")


def alias_display(aliases: dict) -> str:
    """Return alias display string. Always show aliases so users know what /model haiku etc. resolve to."""
    parts = []
    for a in ("haiku", "sonnet", "opus"):
        if aliases.get(a):
            parts.append(f"{a}\u2192{aliases[a]}")
    return f"  [{', '.join(parts)}]" if parts else ""


def group_by_provider(profiles: dict) -> dict[str, list[tuple[str, dict]]]:
    groups: dict[str, list] = {}
    for name in sorted(profiles.keys()):
        cfg = profiles[name]
        prov = cfg.get("provider", "custom")
        groups.setdefault(prov, []).append((name, cfg))
    providers = load_providers()

    def sort_key(pk: str):
        return providers.get(pk, {}).get("name", pk.capitalize()).lower()
    return dict(sorted(groups.items(), key=lambda x: sort_key(x[0])))


def print_provider_header(prov_key: str) -> None:
    providers = load_providers()
    pinfo = providers.get(prov_key, {})
    name = pinfo.get("name", prov_key.capitalize())
    desc = pinfo.get("desc", "")
    header = f"\u2500\u2500 {name}"
    if desc:
        header += f"  ({desc})"
    print(f"  {header}")


def interactive_pick(scope: str, path: Path, label: str, preview: bool = False) -> None:
    profiles = load_profiles()
    if not profiles:
        show_first_time_guide()
        return

    current_data = read_json(path)
    current_model = current_data.get("model", "(未设置)")

    print(f"\n  \u5f53\u524d [{label}]: {current_model}\n")
    groups = group_by_provider(profiles)
    flat: list[tuple[str, dict]] = []

    for prov_key, items in groups.items():
        print_provider_header(prov_key)
        for name, cfg in items:
            idx = len(flat) + 1
            flat.append((name, cfg))
            tag = "\u2605" if cfg["model"] == current_model else " "
            info = cfg["model"]
            alias_str = alias_display(cfg.get("aliases", {}))
            if alias_str:
                info += alias_str
            elif cfg.get("desc"):
                info += f"  \u2014 {cfg['desc']}"
            print(f"    {idx:>2}. {tag} {name:<16} {info:<60}")
        print()
    print("  \u8f93\u5165\u7f16\u53f7\u3001\u540d\u5b57\u6216\u524d\u7f00 \u2192 ", end="", flush=True)

    try:
        choice = input().strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if not choice:
        return

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(flat):
            do_switch(flat[idx][0], scope, path, label, preview=preview)
            return
    except ValueError:
        pass

    do_switch(choice, scope, path, label, preview=preview)


def show_first_time_guide() -> None:
    print(r"""
╭──────────────────────────────────────────────────╮
│  👋 欢迎使用 claude-switch v""" + VERSION + r"""                      │
│                                                  │
│  内置热门模型 (开箱即用):                          │
│    sonnet · haiku · opus           (Anthropic)   │
│    deepseek-pro  · deepseek-flash  (DeepSeek)    │
│    minimax-m2.7                    (MiniMax)     │
│    glm-5 · kimi-k2.6 · gemini-flash (OpenRouter) │
│                                                  │
│  设置 API Key 后即可使用:                          │
│    export DEEPSEEK_API_KEY="sk-xxx"              │
│    export OPENROUTER_API_KEY="sk-or-v1-xxx"      │
│    export MINIMAX_API_KEY="sk-xxx"               │
│                                                  │
│  更多:                                            │
│    claude-switch list / --help / --help-zh          │
╰──────────────────────────────────────────────────╯
""")


def cmd_list(profiles: dict) -> None:
    groups = group_by_provider(profiles)
    for prov_key, items in groups.items():
        print_provider_header(prov_key)
        for name, cfg in items:
            info = cfg["model"]
            alias_str = alias_display(cfg.get("aliases", {}))
            if alias_str:
                info += alias_str
            print(f"    {name:<18} {info:<50} {profile_provider_label(name, cfg)}")
        print()


def cmd_show(scope: str, path: Path, label: str, name: str | None = None) -> None:
    if name:
        _cmd_show_detail(name)
        return

    root = find_project_root()
    layers = [
        ("local",   root / ".claude" / "settings.local.json"),
        ("project", root / ".claude" / "settings.json"),
        ("user",    USER_SETTINGS),
    ]
    active_model = None
    active_layer = None
    print()
    for layer_name, layer_path in layers:
        data = read_json(layer_path)
        model = data.get("model", "\u2014")
        env = data.get("env", {})
        base_info = f"  (base_url: {env['ANTHROPIC_BASE_URL']})" if env.get("ANTHROPIC_BASE_URL") else ""
        if not layer_path.exists():
            marker = "\u2205"
        elif active_model is None and model != "\u2014":
            marker, active_model, active_layer = "\u2726", model, layer_name
        elif model == "\u2014":
            marker = "\u00b7"
        else:
            marker = "\u00b7"
        print(f"  {marker} {layer_name:<10} {model:<30}{base_info}")
    if active_layer:
        print(f"\n  \u751f\u6548: {active_layer} \u2192 {active_model}")
    print()


def _cmd_show_detail(name: str) -> None:
    profiles = load_profiles()
    matched = fuzzy_match(profiles, name)
    if matched is None:
        err(f"未找到 profile '{name}'")
        sys.exit(1)
    cfg = profiles[matched]
    provider = get_provider(cfg.get("provider", "custom"))

    print(f"\n  profile: {matched}")
    print(f"  provider: {provider.get('name', cfg.get('provider', 'custom'))}")
    print(f"  model: {cfg.get('model')}")
    print()
    print("  \u2500\u2500 \u8ba4\u8bc1 \u2500\u2500")
    token = resolve_auth_token(cfg)
    source = auth_source_label(cfg)
    if token:
        print(f"  token: 已设置  (来源: {source})")
    else:
        print(f"  token: (未设置)  来源: {source}")
    print(f"  base_url: {resolve_base_url(cfg) or '(原生)'}")
    print()
    aliases = cfg.get("aliases", {})
    if aliases:
        print("  \u2500\u2500 \u573a\u666f\u6620\u5c04 (aliases) \u2500\u2500")
        for a in ("haiku", "sonnet", "opus"):
            if aliases.get(a):
                print(f"  /model {a} \u2192 {aliases[a]}")
        print()

    s = cfg.get("settings", {})
    if s:
        print("  \u2500\u2500 \u9ad8\u7ea7\u8bbe\u7f6e \u2500\u2500")
        if s.get("alwaysThinkingEnabled") is not None:
            print(f"  alwaysThinkingEnabled: {s['alwaysThinkingEnabled']}")
        if s.get("apiTimeoutMs"):
            print(f"  apiTimeoutMs: {s['apiTimeoutMs']}")
        if s.get("disableNonessentialTraffic"):
            print("  disableNonessentialTraffic: true")
        print()

    raw = cfg.get("raw", {})
    if raw:
        print("  \u2500\u2500 \u900f\u4f20 (raw) \u2500\u2500")
        print(f"  {json.dumps(raw, indent=2, ensure_ascii=False)}")
        print()

    print(f"  \u2500\u2500 \u7ffb\u8bd1\u7ed3\u679c \u2500\u2500")
    translated = profile_to_settings(cfg)
    print(f"  {json.dumps(translated, indent=2, ensure_ascii=False)}")
    print()


def cmd_log() -> None:
    entries = read_history()
    if not entries:
        print("还没有切换记录")
        return
    print()
    for i, e in enumerate(entries):
        print(f"  {i+1:>3}. {e['ts']}  {e['profile']:<16} [{e.get('scope','?')}]")
    print()


def cmd_providers() -> None:
    provs = load_providers()
    print()
    for key, info in provs.items():
        name = info.get("name", key)
        base = info.get("base_url") or "(原生)"
        env_key = info.get("env_key", "\u2014")
        preset = "\u5185\u7f6e(\u9501\u5b9a)" if key in PROVIDER_PRESETS else "\u81ea\u5b9a\u4e49"
        print(f"  {key:<14} {name:<14} base_url: {base:<45} [{preset}]")
        print(f"  {'':>30} env_key: ${env_key}")
        if info.get("desc"):
            print(f"  {'':>30}{info['desc']}")
    print()


def cmd_add(args: list) -> None:
    name = None
    model = None
    provider = None
    auth_token = None
    haiku_model = None
    sonnet_model = None
    opus_model = None

    it = iter(args)
    for a in it:
        if a in ("-p", "--provider"):
            provider = next(it, "")
        elif a in ("-t", "--auth-token"):
            auth_token = next(it, "")
        elif a == "--haiku":
            haiku_model = next(it, "")
        elif a == "--sonnet":
            sonnet_model = next(it, "")
        elif a == "--opus":
            opus_model = next(it, "")
        elif name is None:
            name = a
        elif model is None:
            model = a

    if not name or not model:
        err("缺少 name 或 model 参数")
        print("  用法: claude-switch add <name> <model> -p <PROVIDER> [-t TOKEN] [--haiku M] [--sonnet M] [--opus M]", file=sys.stderr)
        sys.exit(1)
    if not model.strip():
        err("model 不能为空")
        sys.exit(1)
    if name in BUILTIN_NAMES:
        err(f"'{name}' 是内置 profile, 不能覆盖")
        sys.exit(1)
    if provider:
        if provider not in load_providers():
            err(f"未知 provider '{provider}'. 用 'claude-switch providers' 查看已知 provider")
            sys.exit(1)
    existing = load_profiles()
    if name in existing and name not in BUILTIN_NAMES:
        print(f"\u26a0 profile '{name}' 已存在, 将被覆盖")
        try:
            ans = input("确认覆盖? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if ans not in ("y", "yes"):
            print("已取消")
            return

    entry: dict = {"model": model}
    if provider:
        entry["provider"] = provider
    if auth_token:
        entry["auth_token"] = auth_token

    aliases = {
        "haiku": haiku_model or model,
        "sonnet": sonnet_model or model,
        "opus": opus_model or model,
    }
    entry["aliases"] = aliases

    cur = read_json(PROFILES_FILE)
    cur[name] = entry
    PROFILES_FILE.write_text(json.dumps(cur, indent=2) + "\n")

    provider_label = get_provider(provider or "custom").get("name", "\u81ea\u5b9a\u4e49")
    token_source = ""
    if auth_token:
        token_source = " (token: \u663e\u5f0f\u8bbe\u7f6e)"
    else:
        env_key = provider_env_key(provider or "")
        if env_key:
            token_source = f" (token: ${env_key})"
    print(f"\u2713 已添加 profile '{name}' ({provider_label}) \u2192 {model}{token_source}")


def cmd_add_provider(args: list) -> None:
    if len(args) < 2:
        err("缺少参数")
        print("  用法: claude-switch add-provider <name> <base_url> [--env-key KEY]", file=sys.stderr)
        sys.exit(1)
    name = args[0]
    base_url = args[1]
    env_key = None
    it = iter(args[2:])
    for a in it:
        if a == "--env-key":
            env_key = next(it, "")
    entry = {"name": name.capitalize(), "base_url": base_url, "auth_mode": "bearer"}
    if env_key:
        entry["env_key"] = env_key
    cur = read_json(PROVIDERS_FILE)
    cur[name] = entry
    PROVIDERS_FILE.write_text(json.dumps(cur, indent=2) + "\n")
    print(f"\u2713 已添加 provider '{name}' \u2192 {base_url}")
    if env_key:
        print(f"  env_key: ${env_key}")


def cmd_rm(args: list) -> None:
    name = args[0] if args else None
    if not name:
        err("缺少参数")
        print("  用法: claude-switch rm <name>", file=sys.stderr)
        sys.exit(1)
    if name in BUILTIN_NAMES:
        err(f"不能删除内置 profile '{name}'")
        sys.exit(1)
    cur = read_json(PROFILES_FILE)
    if name not in cur:
        err(f"未找到 profile '{name}'")
        sys.exit(1)
    del cur[name]
    PROFILES_FILE.write_text(json.dumps(cur, indent=2) + "\n")
    print(f"\u2713 已删除 profile '{name}'")


def parse_args(argv: list) -> dict:
    scope, subcmd, rest = "project", None, []
    dry_run = False
    preview = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-u", "--user"):
            scope = "user"
        elif a in ("-l", "--local"):
            scope = "local"
        elif a in ("-h", "--help"):
            print(HELP_EN.format(V=VERSION))
            sys.exit(0)
        elif a == "--help-zh":
            print(HELP_ZH.format(V=VERSION))
            sys.exit(0)
        elif a in ("-V", "--version"):
            print(f"claude-switch v{VERSION}")
            sys.exit(0)
        elif a == "--dry-run":
            dry_run = True
        elif a == "--preview":
            preview = True
        elif a in ("list", "ls"):
            subcmd = "list"
        elif a in ("show", "status", "st"):
            subcmd = "show"
            if i + 1 < len(argv) and not argv[i + 1].startswith("-"):
                i += 1
                rest = [argv[i]]
        elif a == "log":
            subcmd = "log"
        elif a == "providers":
            subcmd = "providers"
        elif a == "add":
            subcmd = "add"
            rest = argv[i + 1:]
            break
        elif a == "add-provider":
            subcmd = "add-provider"
            rest = argv[i + 1:]
            break
        elif a in ("rm", "remove", "delete", "del"):
            subcmd = "rm"
            rest = argv[i + 1:]
            break
        elif a == "-":
            subcmd = "back"
        else:
            if not subcmd:
                subcmd = "switch"
                rest = [a]
            else:
                rest.append(a)
        i += 1
    return {"scope": scope, "subcmd": subcmd, "rest": rest,
            "dry_run": dry_run, "preview": preview}


def resolve_path_and_label(scope: str) -> tuple[Path, str]:
    if scope == "user":
        return USER_SETTINGS, f"user ({USER_SETTINGS})"
    root = find_project_root()
    if scope == "local":
        p = root / ".claude" / "settings.local.json"
        return p, f"local ({p})"
    return root / ".claude" / "settings.json", f"project ({root / '.claude' / 'settings.json'})"


def main() -> None:
    _migrate_legacy()
    args = parse_args(sys.argv[1:])
    scope = args["scope"]
    subcmd = args["subcmd"]
    rest = args["rest"]
    dry_run = args["dry_run"]
    preview = args["preview"]

    path, label = resolve_path_and_label(scope)
    profiles = load_profiles()

    if subcmd == "list":
        cmd_list(profiles)
        return
    if subcmd == "log":
        cmd_log()
        return
    if subcmd == "providers":
        cmd_providers()
        return
    if subcmd == "add":
        cmd_add(rest)
        return
    if subcmd == "add-provider":
        cmd_add_provider(rest)
        return
    if subcmd == "rm":
        cmd_rm(rest)
        return
    if subcmd == "show":
        cmd_show(scope, path, label, rest[0] if rest else None)
        return
    if subcmd == "back":
        prev = get_previous_profile()
        if prev is None:
            err("没有上一条切换记录")
            sys.exit(1)
        if prev not in profiles:
            err(f"上一个 profile '{prev}' 已不存在 (已删除?)")
            sys.exit(1)
        print(f"回退到上一步: {prev}")
        do_switch(prev, scope, path, label, dry_run=dry_run, preview=preview)
        return
    if subcmd == "switch" and rest:
        do_switch(rest[0], scope, path, label, dry_run=dry_run, preview=preview)
    else:
        interactive_pick(scope, path, label, preview=preview)

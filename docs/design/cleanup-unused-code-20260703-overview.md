# 过期与未使用代码清理设计

> 日期: 2026-07-03
> 状态: 已被 `ccs-user-interface-20260703-refactor.md` v6 取代
> 主题: 将当前主线之外的代码统一归档到 `backup/`

## 0. 废弃说明

本设计形成时仍把 `ccs tmux ...` 和 `ccs tui` 当作可保留主路径。后续用户定位已经调整为“命令行快速启动 Claude Code / Codex / OpenCode，并通过标准化项目记忆共享上下文”，不再保留 TUI、tmux、daemon 和旧 `claude-switch` 兼容命令。

当前实施应以 `docs/design/ccs-user-interface-20260703-refactor.md` v6 和 `docs/dev/PLAN-009-ccs-refactor.md` 为准。本文只作为历史分析记录，不再作为实施依据。

## 1. 背景

当前仓库同时存在多条历史路线：

- 当前主路径：`ccs claude --cc-model ...` 轻量 launcher。
- 可选主路径：`ccs tmux ...` 的命名 session 管理。
- 兼容路径：旧 `claude-switch` CLI。
- 实验路径：daemon / PTY / workbench、`labs/` 原型。

这些路线的概念混在同一个包里，导致用户接口和内部接口边界不清：

- 用户看到的命令面超过当前实际推荐路径。
- 内部模块之间存在多套 session、配置生成、模型注入机制。
- 测试覆盖被过期路线牵引，影响当前主路径演进。

用户已明确：密集开发中，不考虑兼容性；过期和没有用的代码统一放到 `backup/`。

## 2. 设计目标

1. 当前可见产品面只保留 `ccs` 主线。
2. 过期代码不直接删除，而是移动到 `backup/`，便于查阅和恢复。
3. 安装包不再包含 `backup/` 中代码。
4. 测试只覆盖当前主线，不继续为归档代码维护行为契约。
5. 归档后主包的导入关系保持清晰，不从 `backup/` 反向引用代码。

## 3. 非目标

- 不保证旧 `claude-switch` console script 兼容。
- 不继续维护 daemon / workbench / labs 的运行能力。
- 不在本次设计里重构 tmux 实现细节。
- 不迁移用户本机旧配置文件。

## 4. 用户接口判断

### 当前用户接口

当前用户接口应该只包含：

- `ccs claude [claude args...] [--cc-model MODEL]`
- `ccs codex [codex args...] [--cc-model MODEL]`
- `ccs opencode [opencode args...] [--cc-model MODEL]`
- `ccs models [provider]`
- `ccs model show <model>`
- `ccs providers`
- `ccs tmux claude ...`
- `ccs tmux list|attach|switch|kill|monitor`
- `ccs tui`

其中 `ccs tui` 是 tmux session 的辅助入口，不是 daemon/workbench。

### 应移出用户接口的命令

- `claude-switch ...`
- `ccs daemon ...`
- `ccs new ...`
- `ccs restart ...`
- 顶层 `ccs list|attach|switch|kill|monitor` 的 daemon 语义
- `ccs workbench` / panel 类入口

设计理由：这些命令属于历史路线或实验路线，会让用户误以为系统存在第三种 session 管理后端。

## 5. 内部接口判断

### 当前内部接口

主包应保留这些内部模块：

- `claude_switch.ccs`: CLI 解析和命令分发。
- `claude_switch.models`: provider/model 注册表与解析。
- `claude_switch.session`: tmux session 管理。
- `claude_switch.tui`: tmux session 的 Textual TUI。
- `claude_switch.settings`: Claude settings 翻译逻辑。

### 应归档的内部接口

- `claude_switch.daemon`
- `claude_switch.protocol`
- `claude_switch.store`
- `claude_switch.workbench`
- `claude_switch.adapters.*`
- `labs/*`
- 旧 `claude_switch.__init__` 中的 `claude-switch` CLI 实现

设计理由：这些模块定义了另一套运行时、状态存储、RPC、PTY 和 UI 契约。保留在主包内会让内部边界变成“多后端并存”，但当前目标是收敛主线。

## 6. 方案比较

### 方案 A: 直接删除过期代码

优点：

- 主包最干净。
- 测试和打包最简单。

缺点：

- 密集开发中回看历史实现成本高。
- 用户明确要求统一放到 `backup/`，直接删除不符合要求。

结论：不采用。

### 方案 B: 原路径保留但隐藏入口

优点：

- 改动小。
- 可以快速恢复旧入口。

缺点：

- 过期模块仍会被安装包发现。
- 导入关系和测试仍可能继续依赖旧代码。
- 设计边界没有真正收敛。

结论：不采用。

### 方案 C: 移动到仓库根目录 `backup/`

优点：

- 满足“统一放到 backup”。
- 主包边界清晰，打包默认不包含 `backup/`。
- 历史实现仍可查阅。

缺点：

- Git diff 会显示为删除加新增，变更较大。
- 旧代码不能直接以原模块名运行。

结论：采用。

### 方案 D: 拆成独立历史包或插件

优点：

- 可保留运行能力。
- 适合长期维护多个后端。

缺点：

- 超出当前“清理无用代码”的目标。
- 会继续消耗设计和测试成本。

结论：不采用。

## 7. 定稿方案

采用方案 C：移动到 `backup/`，主包收敛为当前 `ccs` 主线。

### 目录设计

```text
backup/
  claude_switch/
    legacy_init.py
    daemon.py
    protocol.py
    store.py
    workbench.py
    adapters/
  docs/
    README_zh_legacy.md
  labs/
    b1-tmux-tui/
    b2-pty-tui/
```

### 主包设计

```text
claude_switch/
  __init__.py       # 只保留版本和包元信息
  __main__.py       # 指向当前 ccs 入口
  ccs.py            # 当前 CLI
  models.py         # 当前模型注册表
  settings.py       # Claude settings 翻译
  session.py        # tmux session
  tui.py            # tmux TUI
```

### CLI 设计

- `ccs` 是唯一 console script。
- 不再注册 `claude-switch`。
- `ccs --help` 不展示 daemon、new、restart、workbench。
- 顶层 `list|attach|switch|kill|monitor` 不再默默走 daemon；如保留，应提示用户使用 `ccs tmux ...`。

## 8. 必要设计理由

1. `backup/` 位于仓库根目录，而不是 `claude_switch/backup/`。

   假设：归档代码不应被 setuptools 的 `claude_switch*` 包发现。

   若未来需要恢复运行能力，可以移动回主包或拆成独立包；在此假设存在时，不应把归档代码留在主包命名空间内。

2. `settings.py` 从旧 `__init__.py` 中拆出。

   假设：当前 launcher 和 tmux 仍需要把 `ResolvedModel` 翻译成 Claude settings。

   若未来 Claude settings 生成被完全替换，可以删除 `settings.py`；在此假设存在时，不应让 `__init__.py` 继续承载业务逻辑。

3. `models.py` 不再读取旧 `~/.claude-switch-profiles.json`。

   假设：不考虑旧兼容，当前模型扩展只通过 `ccs models add` 管理。

   若未来重新支持 profile，可以作为新设计加入；在此假设存在时，不应让当前模型解析依赖旧 CLI 的 profile 文件。

4. `backup/` 不纳入测试。

   假设：归档代码只用于查阅，不承诺可运行。

   若未来某段代码恢复为主线，应先移回主包并补测试；在此假设存在时，不应为归档代码继续维护测试契约。

## 9. 实施顺序

1. 暂停当前代码改动，先确认本设计。
2. 若保留已发生的工作区移动，则在此基础上继续收敛主包导入。
3. 若需要严格从设计开始，则先回滚本轮已发生的代码移动，再按本设计重新实施。
4. 新增 `settings.py`，重建 `__init__.py` 和 `__main__.py`。
5. 清理 `ccs.py` 中 daemon/workbench 入口和导入。
6. 清理 `models.py` 的旧 profile 解析。
7. 更新 `pyproject.toml`。
8. 更新测试，只覆盖当前主线。
9. 运行验证，生成 `PLAN-008-clean-unused-code-OUTCOME.md`。

## 10. 查漏补缺

### 第一轮：用户接口

- 是否仍有帮助文案暴露旧命令：需要检查 `README.md`、`HELP`、`HELP_ZH`。
- 是否仍有 console script 注册旧命令：需要检查 `pyproject.toml`。
- 顶层管理命令是否会误触旧 daemon：需要检查 `MANAGEMENT` 和 `_run_management()`。

结论：旧用户接口必须从当前主线移除。

### 第二轮：内部接口

- 是否仍从主包导入 `backup/` 代码：不允许。
- 是否仍存在 `protocol/store/daemon/workbench/adapters` 的主包引用：不允许。
- 是否仍通过旧 `__init__.py` 提供业务函数：不允许。

结论：主包只能依赖当前模块，归档代码是单向历史记录。

### 第三轮：测试与打包

- 测试文件不得导入归档模块。
- `setuptools.find` 不应包含 `backup/`。
- `pyte` 依赖若只为 daemon 使用，应移除。
- `textual` 若只为 `ccs tui` 使用，可以保留。

结论：测试和依赖必须跟随当前主线收敛。

## 11. 开放问题

1. 顶层 `ccs list|attach|switch|kill|monitor` 是直接删除，还是保留为提示 `ccs tmux ...` 的错误信息？

   推荐：保留提示错误，降低误用成本，但不执行旧逻辑。

2. `backup/` 是否需要 README 说明归档原因？

   推荐：新增简短 `backup/README.md`，说明归档代码不参与安装和测试。

3. 已经发生的预实施移动如何处理？

   推荐：如果用户认可本设计，继续在当前工作区收敛；如果需要严格流程，先恢复预实施移动，再重新按设计实施。

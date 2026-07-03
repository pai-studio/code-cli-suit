# cc-pty — 多会话 Claude Code 管理器

基于 PTY 伪终端的 TUI 多会话管理工具。纯 Python 实现，不依赖 tmux。

## 原理

```
┌──────────────────────────────────────────┐
│  Textual TUI                             │
│  ┌──────────┬──────────────────────────┐ │
│  │  侧栏    │      终端渲染区 (pyte)     │ │
│  │          │                          │ │
│  │ ○ sess1  │  ┌────────────────────┐  │ │
│  │ ● sess2  │  │  Claude Code 实例  │  │ │
│  │ ○ sess3  │  │  (pty.fork)        │  │ │
│  │          │  └────────────────────┘  │ │
│  │ [Ctrl+N] │                          │ │
│  │ [Ctrl+W] │  输入 → PTY              │ │
│  └──────────┴──────────────────────────┘ │
└──────────────────────────────────────────┘
```

每个 Claude Code 实例运行在独立伪终端中。`pyte` 库将 ANSI 转义序列渲染为 Rich 文本，直接在 Textual 界面中显示。会话元数据持久化到 `~/.cc-pty/sessions.json` 中。

## 安装

```bash
cd labs/b2-pty-tui
pip install -e .
```

依赖：Python 3.10+、textual、pyte（自动安装）。

## 使用方法

### 启动 TUI

```bash
cc-pty
```

### CLI 命令

```bash
cc-pty list       # 列出所有会话
cc-pty tui        # 启动 TUI（等同于 cc-pty）
```

### TUI 快捷键

| 按键 | 功能 |
|------|------|
| `Ctrl+N` | 新建会话 — 弹窗输入名称、项目路径、模型 |
| `Ctrl+W` | 杀掉当前会话 — 需要确认 |
| `Ctrl+R` | 重命名 / 切换模型 — 弹窗修改 |
| `Ctrl+Space` | 焦点切换到侧栏列表 |
| `F5` | 刷新侧栏 |
| `Ctrl+Q` | 退出 |
| `↑ / ↓` | 侧栏中导航 |
| `Enter` | 切换到选中的会话 |
| 鼠标点击 | 点击侧栏条目切换会话 |

### 新建会话流程

1. 按 `Ctrl+N` 弹出新建对话框
2. 填写**会话名称**（必填）
3. 填写**项目路径**（必填，支持 `.`、`~`、相对路径）
4. 填写**模型**（可选，如 `sonnet`、`deepseek-pro`）
   - 填写则自动调用 `claude-switch` 切换模型
   - 不填写则自动检测当前 settings.json 中的模型
5. 点击 **Create** 或回车确认

### 重命名 / 更换模型

1. 选中会话后按 `Ctrl+R`
2. 修改名称和/或模型
3. 点击 **Apply** 确认

> **注意：** 重命名不会影响已经在运行的 Claude Code 进程，仅修改元数据。

## 数据存储

会话信息保存在 `~/.cc-pty/sessions.json`：

```jsonc
{
  "my-project": {
    "name": "my-project",
    "project": "/Users/me/projects/my-project",
    "model": "sonnet"        // 由 claude-switch 设置
  }
}
```

删除会话会从元数据中移除，但不会删除项目文件。

## 与 claude-switch 集成

cc-pty 依赖 `claude-switch` 来切换模型：

- 新建会话时如果指定了模型，内部调用 `claude-switch <model>`
- 重命名时可以更换模型，同样调用 `claude-switch`
- 需要确保 `claude-switch` 已安装且对应的 API Key 已设置

```bash
# 确保 claude-switch 可用
which claude-switch
```

## 常见问题

**Q: 会话关闭后能恢复吗？**

不能。当前版本 PTY 会话关闭后进程即终止，没有持久化。未来版本可能支持 session detach。

**Q: 可以同时运行多少个会话？**

理论上没有限制，但每个会话占用一个 PTY 进程。实际受系统资源限制。

**Q: 退出 TUI 后会话还在吗？**

退出 TUI 会关闭所有终端进程。如需后台运行，考虑使用 tmux 方案（`b1-tmux-tui`）。

**Q: 颜色显示不对？**

终端颜色支持 16 色 ANSI 调色板 + 真彩色（`#rrggbb`）。256 色调色板暂不支持。

## 与 b1-tmux-tui 对比

| 特性 | b2-pty-tui (本方案) | b1-tmux-tui |
|------|---------------------|-------------|
| 依赖 | 纯 Python | 需要 tmux |
| 持久化 | 无（关闭即终止） | tmux session 持久 |
| 渲染 | pyte 终端模拟 | 由 tmux 处理 |
| 退出后 | 全部关闭 | 会话仍运行 |
| 适用场景 | 开发 / 调试 | 长期运行 / 生产 |

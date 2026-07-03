> [English version → README.en.md](./README.en.md)

# Mini Notes with LLM Summary

一款 Anna App，用户可以创建、查看和删除笔记。笔记通过 **Anna storage Host API**（`anna.storage.get` / `anna.storage.set`）持久化。点击 **Summarize** 按钮会通过 JSON-RPC 调用本地 **Executa Tool**，该 Tool 使用 **反向 `sampling/createMessage`** 让宿主 LLM 生成总结。

> 这是一个纯本地开发的 Anna App，不需要真实 Anna 账号，也不需要 LLM API key。

---

## 项目结构

```
mini-notes-llm/
├── manifest.json                  # Anna App 清单
├── package.json                   # 根脚本
├── bundle/                        # 前端构建产物
├── frontend/                      # Vite + 原生 JS 源码
│   ├── src/
│   │   ├── main.js               # AnnaAppRuntime.connect() 初始化
│   │   ├── storage.js            # anna.storage 封装
│   │   ├── tools.js              # anna.tools.invoke 封装
│   │   └── ui.js                 # DOM 渲染与事件
│   ├── index.html
│   ├── style.css
│   ├── package.json
│   └── vite.config.js
├── executas/
│   └── summarize/
│       ├── summarize_tool.py     # Python Executa Tool
│       ├── executa.json
│       ├── pyproject.toml
│       └── pyinstaller.spec
├── fixtures/
│   └── mock-sampling.jsonl       # Mock sampling fixture
├── scripts/
│   └── package.py                # 二进制打包脚本
├── .github/workflows/
│   └── release.yml               # GitHub Actions 发布流水线
├── README.md                     # 中文说明（本文件）
└── README.en.md                  # 英文说明
```

---

## 核心概念

| 概念 | 说明 |
|------|------|
| **manifest.json** | 声明 App 身份、权限、所需 Executa、UI bundle、host API 访问 |
| **Bundle** | 构建后的前端，在 Anna App iframe 中加载，通过 `AnnaAppRuntime` 通信 |
| **Executa Tool** | 独立进程（Python），通过 JSON-RPC 2.0 over stdio 与宿主通信 |
| **Anna storage / APS KV** | 通过 `anna.storage.get` / `anna.storage.set` 持久化 KV 数据 |
| **Sampling** | 反向 JSON-RPC：Tool 发出 `sampling/createMessage`，宿主执行 LLM 推理并返回结果 |
| **Binary archive** | PyInstaller 生成的自包含二进制 + manifest.json，打包为 .tar.gz 或 .zip |

---

## 环境准备

### 依赖

- **Node.js** >= 18
- **Python** >= 3.10
- **uv**（Python 包管理器，Anna harness 用它启动 Executa）
  ```bash
  # Windows PowerShell
  powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
  # macOS / Linux
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **`anna-app` CLI**（全局安装）：
  ```bash
  npm install -g @anna-ai/cli
  ```

### 安装

```bash
# 根目录依赖
npm install

# 前端依赖
cd frontend && npm install && cd ..

# Executa 依赖（生成 uv.lock）
cd executas/summarize && uv lock && cd ../..
```

---

## 构建前端 Bundle

```bash
npm run build
# 等价于: cd frontend && npm run build && cd ..
```

输出到 `bundle/` 目录。`manifest.json` 的 `ui.bundle.entry` 指向该目录下的 `index.html`。

---

## 校验 Manifest

```bash
anna-app validate --strict
```

检查 schema 合规性、权限、及 `required_executas`、`ui.host_api.tools` 与 UI entry 的一致性。

---

## UI Harness 测试（`anna-app dev --no-llm`）

```bash
npm run dev
# 等价于: anna-app dev --no-llm
```

启动本地 Anna harness，在 iframe 中加载前端，并注册 Executa Tool。

### 测试项目

1. **创建笔记** — 输入文字点击 Add，笔记出现在列表中。
2. **验证存储** — 每次创建/删除都会触发 `anna.storage.set(key: "mini-notes:items")`。
   加载时会调用 `anna.storage.get(key: "mini-notes:items")`。
3. **删除笔记** — 点击笔记旁的 Delete，列表立即更新。
4. **点击 Summarize** — 在 `--no-llm` 模式下，LLM/sampling 被禁用。
   前端会调用 `anna.tools.invoke(...)`，harness 将请求路由到 Executa Tool，
   Tool 发出 `sampling/createMessage`。由于 LLM 不可用，返回错误：

   ```
   [-32603] manifest does not grant 'llm.complete'
   ```

   **这是预期行为。** 它证明了完整链路：前端 → `anna.tools.invoke` → Executa invoke → `sampling/createMessage`。错误是因为 `--no-llm` 禁用了 LLM bridge，不是 Bug。

---

## 后端 Sampling 测试（`anna-app executa dev --mock-sampling`）

```bash
npm run executa:dev
```

这会：
1. 启动 Python Executa Tool
2. 完成 `initialize`、`describe` 握手
3. 进入交互式 REPL，可发送 `invoke` 命令
4. 当 Tool 发出 `sampling/createMessage` 时，mock harness 用 `fixtures/mock-sampling.jsonl` 中的内容响应
5. Tool 立即返回总结结果（不会超时）

### 验证 sampling 已发起

- **stderr 输出**会显示 "Mini Notes Summarizer v1.0.0 started"
- **`fixtures/mock-sampling.jsonl`** 包含 mock LLM 响应内容
- **手动协议测试** — 直接通过管道向 Tool 发送 JSON-RPC（见下文）
- **对比验证**：有 `--mock-sampling` 时秒返结果；无 mock（`npm run dev`）时 60 秒超时 —— 这证明 `sampling/createMessage` 确实被发起

---

## 手动 JSON-RPC 测试

### initialize（v2 握手）
```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2.0"}}' | uv run --project executas/summarize mini-notes-summarize
```
预期：返回含 `client_capabilities.sampling: {}` 的响应。

### describe（获取清单）
```bash
echo '{"jsonrpc":"2.0","id":2,"method":"describe","params":{}}' | uv run --project executas/summarize mini-notes-summarize
```
预期：返回含 `display_name`、`tools[]`、`host_capabilities` 的清单。

### invoke（调用总结）
```bash
echo '{"jsonrpc":"2.0","id":3,"method":"invoke","params":{"tool":"summarize","arguments":{"notes":[{"content":"你好","order":1}],"max_words":50},"invoke_id":"test-1"}}' | uv run --project executas/summarize mini-notes-summarize
```
预期：返回 `{"success": true, "tool": "summarize", "data": {...}}`。

### health / shutdown
```bash
echo '{"jsonrpc":"2.0","id":4,"method":"health","params":{}}' | uv run --project executas/summarize mini-notes-summarize
echo '{"jsonrpc":"2.0","id":5,"method":"shutdown","params":{}}' | uv run --project executas/summarize mini-notes-summarize
```

---

## 验证笔记存储走的是 `anna.storage.*`

1. 启动 `anna-app dev --no-llm`
2. 打开浏览器 DevTools Console
3. 观察 RPC 日志：
   - 加载时出现 `storage.get`，key 为 `"mini-notes:items"`
   - 创建/删除时出现 `storage.set`，key 为 `"mini-notes:items"`
4. `storage.js` 中从未调用 `localStorage` —— 所有持久化都走 `anna.storage.get` / `anna.storage.set`

---

## 验证总结走的是 `anna.tools.invoke -> Executa -> sampling`

**证据链：**
1. `tools.js` 调用 `anna.tools.invoke({ tool_id, method: "summarize", args })`
2. Anna harness 将请求路由到 Executa Tool 进程
3. `summarize_tool.py:_handle_invoke` 接收请求
4. `_summarize()` 调用 `sampling.create_message(...)` → 写入 stdout
5. 宿主处理 sampling，返回 LLM 响应
6. Tool 将结果返回前端

确认方式：
- 查看 `summarize_tool.py` 中 `sampling.create_message(...)` 调用，参数中包含 `metadata: { executa_invoke_id, tool: "summarize" }`
- 在 `--no-llm` 下点 Summarize 得到 timeout（证明 Tool 发出了 sampling 请求但没人响应）
- 在 `--mock-sampling` 下秒返 mock 结果（证明 mock harness 拦截了 sampling 请求）

---

## 二进制打包

```bash
pip install pyinstaller>=6.19.0
python scripts/package.py
```

脚本流程：
1. PyInstaller 将 `summarize_tool.py` 编译为单文件二进制
2. 冒烟测试：向二进制发送 `describe` JSON-RPC 请求
3. 将二进制 + `manifest.json` 打包为平台归档：
   - macOS：`mini-notes-summarize-{platform}.tar.gz`
   - Linux：`mini-notes-summarize-linux-x86_64.tar.gz`
   - Windows：`mini-notes-summarize-windows-x86_64.zip`

归档根目录包含：
- `manifest.json` — 二进制分发清单
- `mini-notes-summarize`（或 `.exe`）— 可执行入口

---

## GitHub Actions 发布

流水线位于 `.github/workflows/release.yml`。

**触发方式：** `workflow_dispatch`（手动触发）或推送 `v*` 标签自动触发。

**产出 4 个 Release Asset：**
- `mini-notes-summarize-darwin-arm64.tar.gz`
- `mini-notes-summarize-darwin-x86_64.tar.gz`
- `mini-notes-summarize-linux-x86_64.tar.gz`
- `mini-notes-summarize-windows-x86_64.zip`

每个构建产物都会在上传前进行冒烟测试（发送 `describe` JSON-RPC 并验证响应）。

---

## 快速参考

| 任务 | 命令 |
|------|------|
| 安装依赖 | `npm install && cd frontend && npm install && cd executas/summarize && uv lock && cd ../..` |
| 构建前端 | `npm run build` |
| 校验清单 | `anna-app validate --strict` |
| UI harness（无 LLM） | `npm run dev` |
| Executa sampling 测试 | `npm run executa:dev` |
| 手动 JSON-RPC 测试 | `echo '{"jsonrpc":"2.0","id":1,"method":"describe","params":{}}' \| uv run --project executas/summarize mini-notes-summarize` |
| 打包二进制 | `python scripts/package.py` |

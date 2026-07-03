# Mini Notes with LLM Summary

An Anna App that lets users create, view, and delete notes. Notes are persisted
via the **Anna storage Host API** (`anna.storage.get` / `anna.storage.set`).
A **Summarize** button invokes a local **Executa Tool** over JSON-RPC, which
uses **reverse `sampling/createMessage`** to ask the host LLM for a summary.

> This is a local-development Anna App. No real Anna account or LLM API key required.

---

## Project Structure

```
mini-notes-llm/
├── manifest.json                  # Anna App manifest
├── package.json                   # Root scripts
├── bundle/                        # Built frontend output
├── frontend/                      # Vite + vanilla JS source
│   ├── src/
│   │   ├── main.js               # AnnaAppRuntime.connect() + bootstrap
│   │   ├── storage.js            # anna.storage wrappers
│   │   ├── tools.js              # anna.tools.invoke wrapper
│   │   └── ui.js                 # DOM rendering + events
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
│   └── mock-sampling.jsonl
├── scripts/
│   └── package.py
├── .github/workflows/
│   └── release.yml
└── README.md
```

---

## Core Concepts

| Concept | Description |
|---------|-------------|
| **manifest.json** | Declares app identity, permissions, required Executas, UI bundle, host API access |
| **Bundle** | Built frontend loaded in Anna App iframe; communicates via `AnnaAppRuntime` |
| **Executa Tool** | Standalone process (Python) communicating via JSON-RPC 2.0 over stdio |
| **Anna storage / APS KV** | Persistent KV storage via `anna.storage.get` / `anna.storage.set` |
| **Sampling** | Reverse JSON-RPC: Tool sends `sampling/createMessage`, host runs LLM, returns result |
| **Binary archive** | Self-contained PyInstaller binary + manifest.json, packaged as .tar.gz or .zip |

---

## Setup

### Prerequisites

- **Node.js** >= 18
- **Python** >= 3.10
- **`anna-app` CLI** installed globally:
  ```bash
  npm install -g @anna-ai/cli
  ```

### Install Dependencies

```bash
# Root
npm install

# Frontend
cd frontend && npm install && cd ..
```

---

## Build Frontend Bundle

```bash
npm run build
# or: cd frontend && npm run build && cd ..
```

Outputs static bundle to `bundle/` directory.
`manifest.json` points `ui.bundle.entry` to `index.html` inside this directory.

---

## Validate Manifest

```bash
anna-app validate --strict
```

Checks schema compliance, permissions, and consistency between
`required_executas`, `ui.host_api.tools`, and the UI entry.

---

## UI Harness Testing (`anna-app dev --no-llm`)

```bash
npm run dev
# or: anna-app dev --no-llm
```

Launches the local Anna harness, loads your frontend in an iframe, and registers
the Executa Tool.

### What to test

1. **Create notes** — Type text and click Add. Notes appear in the list.
2. **Verify storage** — Every create/delete triggers `anna.storage.set(key: "mini-notes:items")`.
   On load, `anna.storage.get(key: "mini-notes:items")` is called.
3. **Delete notes** — Click Delete on any note. List updates immediately.
4. **Click Summarize** — In `--no-llm` mode, LLM/sampling is disabled.
   The frontend calls `anna.tools.invoke(...)`, the harness routes to the Executa
   Tool, and the Tool issues `sampling/createMessage`. Since LLM is disabled,
   the harness returns:

   ```
   [-32603] manifest does not grant 'llm.complete'
   ```

   **This is expected.** It proves the complete chain works: frontend →
   `anna.tools.invoke` → Executa invoke → `sampling/createMessage`. The error
   is caused by `--no-llm` disabling the LLM bridge, not by a bug.

---

## Backend Sampling Test (`anna-app executa dev --mock-sampling`)

```bash
npm run executa:dev
# or: anna-app executa dev --mock-sampling fixtures/mock-sampling.jsonl
```

This:
1. Starts the Python Executa Tool
2. Sends test `initialize`, `describe`, and `invoke` messages
3. When the Tool issues `sampling/createMessage`, the mock harness responds
   with content from `fixtures/mock-sampling.jsonl`
4. The Tool returns the summary result

### Verifying sampling was initiated

- **Check stderr output** for "Mini Notes Summarizer v1.0.0 started"
- **Check the fixture** at `fixtures/mock-sampling.jsonl` — it contains a mock
  LLM response consumed by the harness
- **Manual protocol test** — pipe JSON-RPC to the Tool directly (see below)

---

## Manual JSON-RPC Testing

### initialize (v2 handshake)
```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2.0"}}' | uv run --project executas/summarize mini-notes-summarize
```
Expected: response with `client_capabilities.sampling: {}`.

### describe (get manifest)
```bash
echo '{"jsonrpc":"2.0","id":2,"method":"describe","params":{}}' | uv run --project executas/summarize mini-notes-summarize
```
Expected: manifest with `display_name`, `tools[]`, `host_capabilities`.

### health / shutdown
```bash
echo '{"jsonrpc":"2.0","id":3,"method":"health","params":{}}' | uv run --project executas/summarize mini-notes-summarize
echo '{"jsonrpc":"2.0","id":4,"method":"shutdown","params":{}}' | uv run --project executas/summarize mini-notes-summarize
```

---

## Verifying Storage Uses `anna.storage.*`

1. Start `anna-app dev --no-llm`
2. Open browser DevTools Console
3. Look for `storage.get` with key `"mini-notes:items"` on load
4. Look for `storage.set` with key `"mini-notes:items"` on create/delete

The `storage.js` module never calls `localStorage` — all persistence goes
through `anna.storage.get` / `anna.storage.set`.

---

## Verifying Summary Uses `anna.tools.invoke -> Executa -> sampling`

**Evidence chain:**
1. `tools.js` calls `anna.tools.invoke({ tool_id, method: "summarize", args })`
2. Anna harness routes to Executa Tool process
3. `summarize_tool.py:_handle_invoke` receives the request
4. `_summarize()` calls `sampling.create_message(...)` → writes to stdout
5. Host processes sampling, returns LLM response
6. Tool returns result to frontend

Check `summarize_tool.py` for `sampling.create_message(...)` calls with
`metadata: { executa_invoke_id, tool: "summarize" }`.

---

## Binary Packaging

```bash
pip install pyinstaller>=6.19.0
python scripts/package.py
```

What it does:
1. PyInstaller compiles `summarize_tool.py` into a single-file binary
2. Smoke test: sends `describe` JSON-RPC to the binary
3. Packages binary + `manifest.json` into platform archive:
   - macOS: `mini-notes-summarize-{platform}.tar.gz`
   - Windows: `mini-notes-summarize-windows-x86_64.zip`

Archive root contains:
- `manifest.json` — binary distribution manifest
- `mini-notes-summarize` (or `.exe`) — entrypoint

---

## GitHub Actions Release

Workflow at `.github/workflows/release.yml`.

**Triggers:** `workflow_dispatch` (manual) or `v*` tag push.

**Produces 3 release assets:**
- `mini-notes-summarize-darwin-arm64.tar.gz`
- `mini-notes-summarize-darwin-x86_64.tar.gz`
- `mini-notes-summarize-windows-x86_64.zip`

Each includes a smoke test (describe JSON-RPC) before upload.

---

## Quick Reference

| Task | Command |
|------|---------|
| Install deps | `npm install && cd frontend && npm install` |
| Build frontend | `npm run build` |
| Validate manifest | `anna-app validate --strict` |
| UI harness (no LLM) | `npm run dev` |
| Executa sampling test | `npm run executa:dev` |
| Manual JSON-RPC test | `echo '{"jsonrpc":"2.0","id":1,"method":"describe","params":{}}' \| uv run --project executas/summarize mini-notes-summarize` |
| Package binary | `python scripts/package.py` |

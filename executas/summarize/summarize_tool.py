#!/usr/bin/env python3
# summarize_tool.py - Mini Notes Executa plugin using host LLM sampling.
#
# Exposes a single tool "summarize" that accepts a list of notes and asks
# the host to produce a concise summary via reverse JSON-RPC
# sampling/createMessage.

from __future__ import annotations

import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

try:
    import executa_sdk
except ModuleNotFoundError:
    # Fallback: look for the SDK in the cloned examples repo
    # Tool is at: mini-notes-llm/executas/summarize/summarize_tool.py
    # SDK is at:  examples/anna-executa-examples/sdk/python/
    _SDK_PATH = Path(__file__).resolve().parents[3] / "examples" / "anna-executa-examples" / "sdk" / "python"
    if _SDK_PATH.is_dir():
        sys.path.insert(0, str(_SDK_PATH))
    else:
        print(f"Warning: executa_sdk not found at {_SDK_PATH}", file=sys.stderr)

import asyncio

from executa_sdk import (
    METHOD_SAMPLING_CREATE_MESSAGE,
    PROTOCOL_VERSION_V2,
    SamplingClient,
    SamplingError,
)

# --- Manifest ----------------------------------------------------------

MANIFEST = {
    "display_name": "Mini Notes Summarizer",
    "version": "1.0.0",
    "description": "Summarizes notes via host LLM sampling.",
    "author": "Mini Notes Dev",
    "host_capabilities": ["llm.sample"],
    "tools": [
        {
            "name": "summarize",
            "description": "Summarize the list of notes into a concise paragraph.",
            "parameters": [
                {"name": "notes", "type": "array", "description": "List of note objects", "required": True},
                {"name": "max_words", "type": "integer", "description": "Approx max words", "required": False, "default": 100},
            ],
        },
    ],
    "runtime": {"type": "uv", "min_version": "0.1.0"},
}

# --- Sampling client ---------------------------------------------------

_stdout_lock = threading.Lock()


def _write_frame(msg: dict) -> None:
    payload = json.dumps(msg, ensure_ascii=False)
    with _stdout_lock:
        sys.stdout.write(payload + "\n")
        sys.stdout.flush()


sampling = SamplingClient(write_frame=_write_frame)


# --- Tool implementation -----------------------------------------------


async def _summarize(notes: list, max_words: int = 100, *, invoke_id: str) -> dict:
    if not notes:
        return {"summary": "No notes to summarize.", "note_count": 0}

    note_lines = []
    for i, note in enumerate(notes, 1):
        content = note.get("content", "") if isinstance(note, dict) else str(note)
        note_lines.append(f"{i}. {content}")

    combined_text = "\n".join(note_lines)

    max_words = max(20, min(400, int(max_words)))
    max_tokens = max(64, min(1024, max_words * 5))

    result = await sampling.create_message(
        messages=[
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": (
                        f"Summarize {len(notes)} notes in at most {max_words} words. "
                        f"Return only the summary, no preamble.\n\n"
                        f"--- NOTES ---\n{combined_text}\n--- END NOTES ---"
                    ),
                },
            }
        ],
        max_tokens=max_tokens,
        system_prompt="You are a concise editorial assistant.",
        metadata={"executa_invoke_id": invoke_id, "tool": "summarize"},
        timeout=60.0,
    )

    text_out = ""
    content = result.get("content") or {}
    if isinstance(content, dict) and content.get("type") == "text":
        text_out = content.get("text", "")

    return {
        "summary": text_out,
        "note_count": len(notes),
        "model": result.get("model"),
        "usage": result.get("usage"),
        "stopReason": result.get("stopReason"),
    }


# --- JSON-RPC dispatch -------------------------------------------------


def _make_response(req_id, *, result=None, error=None) -> dict:
    out = {"jsonrpc": "2.0", "id": req_id}
    if error is not None:
        out["error"] = error
    else:
        out["result"] = result
    return out


def _handle_initialize(req_id, params: dict) -> dict:
    proto = (params or {}).get("protocolVersion") or "1.1"
    if proto != PROTOCOL_VERSION_V2:
        sampling.disable(
            f"host did not negotiate v2 (offered protocolVersion={proto!r}); "
            "sampling/createMessage requires Executa protocol 2.0"
        )
    return _make_response(
        req_id,
        result={
            "protocolVersion": proto if proto in ("1.1", "2.0") else "2.0",
            "serverInfo": {
                "name": MANIFEST["display_name"],
                "version": MANIFEST["version"],
            },
            "client_capabilities": {"sampling": {}} if proto == PROTOCOL_VERSION_V2 else {},
            "capabilities": {},
        },
    )


def _handle_describe(req_id) -> dict:
    return _make_response(req_id, result=MANIFEST)


def _handle_health(req_id) -> dict:
    return _make_response(
        req_id,
        result={
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": MANIFEST["version"],
        },
    )


_loop = asyncio.new_event_loop()
_loop_thread = threading.Thread(target=_loop.run_forever, daemon=True)
_loop_thread.start()


def _handle_invoke(req_id, params: dict) -> dict:
    tool = params.get("tool")
    args = params.get("arguments") or {}
    invoke_id = params.get("invoke_id") or ""

    if tool != "summarize":
        return _make_response(
            req_id,
            error={"code": -32601, "message": f"Unknown tool: {tool}"},
        )

    coro = _summarize(invoke_id=invoke_id, **args)

    fut = asyncio.run_coroutine_threadsafe(coro, _loop)
    try:
        data = fut.result(timeout=120.0)
    except SamplingError as e:
        return _make_response(
            req_id,
            error={"code": e.code, "message": e.message, "data": e.data},
        )
    except Exception as e:
        return _make_response(
            req_id,
            error={"code": -32603, "message": f"Tool execution failed: {e}"},
        )
    return _make_response(req_id, result={"success": True, "tool": tool, "data": data})


def _handle_message(line: str) -> None:
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        _write_frame(_make_response(None, error={"code": -32700, "message": "Parse error"}))
        return

    if "method" not in msg:
        if not sampling.dispatch_response(msg):
            sys.stderr.write(f"unmatched response id={msg.get('id')!r}\n")
        return

    method = msg.get("method")
    req_id = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        resp = _handle_initialize(req_id, params)
    elif method == "describe":
        resp = _handle_describe(req_id)
    elif method == "invoke":
        resp = _handle_invoke(req_id, params)
    elif method == "health":
        resp = _handle_health(req_id)
    elif method == "shutdown":
        resp = _make_response(req_id, result={"ok": True})
    else:
        resp = _make_response(req_id, error={"code": -32601, "message": f"Method not found: {method}"})

    if req_id is not None:
        _write_frame(resp)


# --- Main loop ---------------------------------------------------------


def main() -> None:
    sys.stderr.write(f"Mini Notes Summarizer v{MANIFEST['version']} started\n")
    pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="invoke")
    try:
        for raw in sys.stdin:
            line = raw.strip()
            if not line:
                continue
            pool.submit(_handle_message, line)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
        _loop.call_soon_threadsafe(_loop.stop)


if __name__ == "__main__":
    main()

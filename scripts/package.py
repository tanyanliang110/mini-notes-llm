#!/usr/bin/env python3
"""
package.py — Build platform-specific binary archives for the Mini Notes Executa.

Usage:
    python scripts/package.py          # build for current platform
    python scripts/package.py --all    # build for all platforms (requires cross-compile)

Output structure (per platform):
    dist/
      mini-notes-summarize-darwin-arm64.tar.gz
        ├── manifest.json          (binary distribution manifest)
        ├── mini-notes-summarize   (entrypoint executable)
      mini-notes-summarize-windows-x86_64.zip
        ├── manifest.json
        ├── mini-notes-summarize.exe
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXECUTA_DIR = ROOT / "executas" / "summarize"
DIST_DIR = ROOT / "dist"

PLATFORM_MAP = {
    "darwin-arm64": {"system": "Darwin", "machine": "arm64", "ext": "", "format": "tar.gz"},
    "darwin-x86_64": {"system": "Darwin", "machine": "x86_64", "ext": "", "format": "tar.gz"},
    "windows-x86_64": {"system": "Windows", "machine": "AMD64", "ext": ".exe", "format": "zip"},
}

ARCHIVE_MANIFEST_VERSION = "1.0.0"
ARCHIVE_MANIFEST = {
    "manifest_version": ARCHIVE_MANIFEST_VERSION,
    "tool_id": "mini-notes-summarize",
    "name": "mini-notes-summarize",
    "display_name": "Mini Notes Summarizer",
    "version": "1.0.0",
    "description": "Summarizes notes via host LLM sampling (Executa binary distribution).",
    "author": "Mini Notes Dev",
    "entrypoint": None,  # set per platform
    "host_capabilities": ["llm.sample"],
    "runtime": {"type": "binary"},
}


def detect_current_platform():
    system = platform.system()
    machine = platform.machine().lower()
    if system == "Windows":
        return "windows-x86_64"
    if system == "Darwin":
        if machine in ("arm64", "aarch64"):
            return "darwin-arm64"
        return "darwin-x86_64"
    if system == "Linux":
        if machine in ("arm64", "aarch64"):
            return "linux-arm64"
        return "linux-x86_64"
    raise RuntimeError(f"Unsupported platform: {system} {machine}")


def build_binary(platform_key):
    """Use PyInstaller to build a single-file binary for the given platform."""
    info = PLATFORM_MAP[platform_key]
    ext = info["ext"]
    binary_name = f"mini-notes-summarize{ext}"

    print(f"[package] Building binary for {platform_key} ...")

    # uv resolves it from pyproject.toml via [tool.uv.sources]; PyInstaller
    # needs an explicit --paths so it can discover the package.
    sdk_python = ROOT.parent / "examples" / "anna-executa-examples" / "sdk" / "python"
    if not (sdk_python / "executa_sdk" / "__init__.py").exists():
        raise FileNotFoundError(
            f"executa_sdk not found at {sdk_python}\n"
            "Make sure the anna-executa-examples repo is cloned at ../examples/anna-executa-examples"
        )

    # PyInstaller build
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--distpath", str(DIST_DIR / "tmp"),
        "--workpath", str(DIST_DIR / "build"),
        "--specpath", str(DIST_DIR),
        "--name", f"mini-notes-summarize{ext}",
        "--onefile",
        "--console",
        "--clean",
        "--paths", str(sdk_python),
        "--hidden-import", "executa_sdk",
        "--hidden-import", "executa_sdk.sampling",
        "--hidden-import", "executa_sdk.storage",
        str(EXECUTA_DIR / "summarize_tool.py"),
    ]

    subprocess.run(cmd, check=True, cwd=str(ROOT))

    # Move binary to expected location
    built = DIST_DIR / "tmp" / binary_name
    if not built.exists():
        # PyInstaller may have placed it differently
        built = DIST_DIR / f"mini-notes-summarize{ext}" / binary_name
    if not built.exists():
        raise FileNotFoundError(f"PyInstaller output not found: {built}")

    return built, binary_name


def create_archive(binary_path, binary_name, platform_key):
    """Package binary + manifest.json into a .tar.gz or .zip archive."""
    info = PLATFORM_MAP[platform_key]
    fmt = info["format"]
    archive_name = f"mini-notes-summarize-{platform_key}"

    print(f"[package] Creating {fmt} archive for {platform_key} ...")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        pkg_dir = tmp / archive_name
        pkg_dir.mkdir()

        # Copy binary
        dest_binary = pkg_dir / binary_name
        shutil.copy2(binary_path, dest_binary)
        os.chmod(dest_binary, 0o755)

        # Write manifest.json
        manifest = dict(ARCHIVE_MANIFEST)
        manifest["entrypoint"] = binary_name
        manifest_path = pkg_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        # Create archive
        DIST_DIR.mkdir(parents=True, exist_ok=True)
        if fmt == "tar.gz":
            archive_path = DIST_DIR / f"{archive_name}.tar.gz"
            with tarfile.open(archive_path, "w:gz") as tar:
                tar.add(str(pkg_dir), arcname=archive_name)
        elif fmt == "zip":
            archive_path = DIST_DIR / f"{archive_name}.zip"
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for file in pkg_dir.rglob("*"):
                    zf.write(file, arcname=str(file.relative_to(tmp)))

        print(f"[package] Created: {archive_path} ({archive_path.stat().st_size} bytes)")
        return archive_path


def smoke_test(binary_path):
    """Send a JSON-RPC describe request to the binary and verify the response."""
    print(f"[package] Smoke testing {binary_path} ...")
    request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "describe", "params": {}})
    result = subprocess.run(
        [str(binary_path)],
        input=request + "\n",
        capture_output=True,
        text=True,
        timeout=10,
    )
    try:
        response = json.loads(result.stdout.strip().split("\n")[-1])
        if response.get("result", {}).get("display_name") == "Mini Notes Summarizer":
            print("[package] Smoke test PASSED: describe returned valid manifest")
        else:
            print(f"[package] Smoke test WARNING: unexpected response: {response}")
    except (json.JSONDecodeError, IndexError) as e:
        print(f"[package] Smoke test FAILED: {e}")
        print(f"  stdout: {result.stdout[:200]}")
        print(f"  stderr: {result.stderr[:200]}")
        raise


def main():
    parser = argparse.ArgumentParser(description="Package Mini Notes Executa binary")
    parser.add_argument(
        "--platform",
        help="Target platform key (e.g. darwin-arm64, windows-x86_64)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Build for all supported platforms",
    )
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="Skip smoke test",
    )
    args = parser.parse_args()

    if args.all:
        platforms = list(PLATFORM_MAP.keys())
    elif args.platform:
        platforms = [args.platform]
    else:
        platforms = [detect_current_platform()]

    for pk in platforms:
        if pk not in PLATFORM_MAP:
            print(f"[package] Skipping unsupported platform: {pk}")
            continue

        try:
            binary_path, binary_name = build_binary(pk)
            if not args.skip_smoke:
                smoke_test(binary_path)
            create_archive(binary_path, binary_name, pk)
        except Exception as e:
            print(f"[package] ERROR for {pk}: {e}", file=sys.stderr)
            if not args.all:
                sys.exit(1)

    print("[package] Done.")


if __name__ == "__main__":
    main()

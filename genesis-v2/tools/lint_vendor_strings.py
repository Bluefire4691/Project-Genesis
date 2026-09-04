#!/usr/bin/env python3
"""
CI guard: vendor lock-in and cross-namespace trust joins.

Two invariants the project cannot enforce by convention alone, because both
fail silently and both are expensive to undo:

  1. HARDWARE PORTABILITY. Vendor names (cuda/rocm/vulkan/nvidia/amd/metal/
     sycl) may appear ONLY inside genesis/backends/. Everything above the
     boundary speaks in aliases and capabilities. A single `.cuda()` outside
     that directory is how a portable engine quietly becomes an NVIDIA one.

  2. TRUST NAMESPACE SEPARATION. `source_trust` (accuracy) and
     `holder_authority` (authoritativeness-for-a-population) must never be
     joined. They mean different things: merging them silently ranks moral
     traditions by truthfulness.

Exit 1 on violation. Run in CI and pre-commit.

    python tools/lint_vendor_strings.py [root]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Directories where vendor names are legitimate — the abstraction boundary.
ALLOWED_VENDOR_DIRS = ("genesis/backends", "tools", "tests", "docs")

VENDOR = re.compile(
    r"\b(cuda|rocm|hip|vulkan|nvidia|nvidia-smi|amd|metal|sycl|mps|"
    r"bitsandbytes|torch\.cuda|\.cuda\(\))\b",
    re.IGNORECASE,
)

# Torch/device leakage above the boundary.
DEVICE_LEAK = re.compile(r"\b(torch\.Tensor|\.to\(device|device_map|\.half\(\))")

# A query touching both trust tables in one statement.
TRUST_JOIN = re.compile(
    r"source_trust[\s\S]{0,400}?holder_authority"
    r"|holder_authority[\s\S]{0,400}?source_trust",
    re.IGNORECASE,
)

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache"}


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _vendor_allowed(rel: str) -> bool:
    return any(rel.startswith(d + "/") or rel == d for d in ALLOWED_VENDOR_DIRS)


def check(root: Path) -> list[str]:
    problems: list[str] = []

    for path in sorted(root.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        rel = _rel(path, root)
        if rel == "tools/lint_vendor_strings.py":
            continue                       # this file names them by necessity

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            problems.append(f"{rel}: unreadable ({exc})")
            continue

        # 2. Trust-namespace join — checked everywhere, including tests.
        # The only escape is an explicit, greppable marker, so a real
        # violation can never be waved through by living in the wrong folder.
        if TRUST_JOIN.search(text) and "lint:allow-trust-join" not in text:
            problems.append(
                f"{rel}: joins source_trust with holder_authority. "
                f"These namespaces mean different things (accuracy vs "
                f"authoritativeness-for-a-population); merging them ranks "
                f"moral traditions by truthfulness. See docs/v2/EPISTEMICS.md.")

        if _vendor_allowed(rel):
            continue

        # 1. Vendor strings / device leakage above the boundary.
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or "lint:allow-vendor" in line:
                continue
            m = VENDOR.search(line)
            if m:
                problems.append(
                    f"{rel}:{lineno}: vendor string {m.group(0)!r} outside "
                    f"genesis/backends/. Callers use aliases and capabilities, "
                    f"never hardware names.")
            d = DEVICE_LEAK.search(line)
            if d:
                problems.append(
                    f"{rel}:{lineno}: device/tensor leak {d.group(0)!r} outside "
                    f"genesis/backends/. Only plain Python and numpy cross the "
                    f"boundary.")
    return problems


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    problems = check(root)
    if problems:
        print(f"FAIL: {len(problems)} portability/namespace violation(s)\n")
        for p in problems:
            print("  " + p)
        print("\nSee docs/v2/ARCHITECTURE_V2.md §2 and docs/v2/EPISTEMICS.md §3d.")
        return 1
    print("OK: no vendor strings outside backends/, no cross-namespace trust joins.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

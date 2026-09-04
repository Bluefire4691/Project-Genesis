"""
Capability probe — detect the silicon, then MEASURE rather than assume.

This module and the rest of `backends/` are the only places in the codebase
permitted to mention vendor names. Everything above the boundary speaks in
aliases ("llm.main") and capabilities, never in hardware.

WHY MEASURE INSTEAD OF PICK
---------------------------
Backend performance splits by WORKLOAD, not just by device. Measured on
RDNA4 with Llama-2-7B Q4_0:

    ROCm/HIP + flash-attn :  4903 t/s prefill  /   97 t/s decode
    Vulkan                :  1943 t/s prefill  /  124 t/s decode

ROCm wins prefill; Vulkan wins decode. There is no single right answer, and
a hand-picked default would be wrong half the time. So we run a ~5s
micro-benchmark on first sight of a machine and pin the winner PER WORKLOAD,
then cache it keyed on a hardware+driver fingerprint.

The preference order is declarative (config), never hard-coded logic.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Sequence

from .base import BackendUnavailable, LLMBackend, Message, SamplingParams

# Declarative preference. Config, not logic: reorder this list (or override
# via GENESIS_BACKEND_PREFERENCE) and the probe's behaviour changes with no
# code edit. Entries are candidate compute runtimes in descending priority.
DEFAULT_PREFERENCE: tuple[str, ...] = (
    "cuda", "rocm", "vulkan", "metal", "sycl", "cpu",
)

_CACHE_NAME = "backend_probe.json"
_PROBE_VERSION = 1


# ---------------------------------------------------------------------------
# Hardware enumeration
# ---------------------------------------------------------------------------

@dataclass
class HardwareReport:
    os: str
    arch: str
    cpu_count: int
    runtimes: list[str] = field(default_factory=list)   # detected, ordered
    devices: list[str] = field(default_factory=list)    # human-readable
    fingerprint: str = ""

    def banner(self) -> str:
        dev = "; ".join(self.devices) if self.devices else "cpu only"
        rt = ", ".join(self.runtimes) if self.runtimes else "cpu"
        return f"{self.os}/{self.arch} | {self.cpu_count} cores | {dev} | runtimes: {rt}"


def _run(cmd: Sequence[str], timeout: float = 6.0) -> str:
    """Run a probe command, returning '' on any failure. Never raises."""
    if shutil.which(cmd[0]) is None:
        return ""
    try:
        out = subprocess.run(list(cmd), capture_output=True, text=True,
                             timeout=timeout)
        return (out.stdout or "") + (out.stderr or "")
    except Exception:
        return ""


def detect_hardware() -> HardwareReport:
    """Enumerate available compute runtimes. Detection only — no ranking."""
    rep = HardwareReport(
        os=platform.system().lower(),
        arch=platform.machine().lower(),
        cpu_count=os.cpu_count() or 1,
    )
    found: list[str] = []
    devices: list[str] = []

    # NVIDIA
    smi = _run(["nvidia-smi", "--query-gpu=name,memory.total",
                "--format=csv,noheader"])
    if smi.strip() and "not found" not in smi.lower():
        found.append("cuda")
        devices += [f"NVIDIA {ln.strip()}" for ln in smi.splitlines() if ln.strip()]

    # AMD
    rocm = _run(["rocminfo"]) or _run(["hipInfo"])
    if "gfx" in rocm.lower():
        found.append("rocm")
        gfx = sorted({tok for tok in rocm.split() if tok.startswith("gfx")})
        if gfx:
            devices.append("AMD " + ",".join(gfx))

    # Vulkan — the widest-coverage GPU path (NVIDIA, AMD, Intel, more)
    vk = _run(["vulkaninfo", "--summary"])
    if "deviceName" in vk or "GPU id" in vk:
        found.append("vulkan")
        for ln in vk.splitlines():
            if "deviceName" in ln:
                devices.append("Vulkan " + ln.split("=")[-1].strip())

    # Apple
    if rep.os == "darwin" and rep.arch in ("arm64", "aarch64"):
        found.append("metal")
        devices.append("Apple Silicon")

    # Intel oneAPI
    if _run(["sycl-ls"]).strip():
        found.append("sycl")

    found.append("cpu")   # always available, always last resort
    rep.runtimes = found
    rep.devices = devices
    rep.fingerprint = _fingerprint(rep)
    return rep


def _fingerprint(rep: HardwareReport) -> str:
    """Stable hash of hardware + runtime set. Changes on a driver/GPU change,
    which invalidates the cached benchmark."""
    import hashlib
    blob = "|".join([rep.os, rep.arch, str(rep.cpu_count),
                     ",".join(sorted(rep.runtimes)), ",".join(sorted(rep.devices))])
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def preference_order(detected: Sequence[str]) -> list[str]:
    """Rank detected runtimes against the declarative preference table."""
    env = os.environ.get("GENESIS_BACKEND_PREFERENCE", "")
    pref = tuple(p.strip() for p in env.split(",") if p.strip()) or DEFAULT_PREFERENCE
    ranked = [p for p in pref if p in detected]
    ranked += [d for d in detected if d not in ranked]   # anything unlisted, last
    return ranked


# ---------------------------------------------------------------------------
# Micro-benchmark
# ---------------------------------------------------------------------------

@dataclass
class BenchResult:
    label: str
    prefill_tps: float = 0.0     # prompt processing throughput
    decode_tps: float = 0.0      # generation throughput
    ok: bool = False
    error: str = ""


_BENCH_PROMPT = ("Summarize the following in one sentence. " + ("data " * 96)).strip()


def micro_benchmark(llm: LLMBackend, label: str,
                    decode_tokens: int = 32) -> BenchResult:
    """~5s benchmark: one prefill-heavy call, one decode-heavy call.

    Deliberately crude — we only need to ORDER candidates, not publish
    numbers. Never raises; a failed candidate is simply not selected.
    """
    res = BenchResult(label=label)
    try:
        n_prompt = llm.count_tokens(_BENCH_PROMPT)
    except Exception:
        n_prompt = max(1, len(_BENCH_PROMPT) // 4)

    try:
        msgs = [Message(role="user", content=_BENCH_PROMPT)]

        t0 = time.perf_counter()
        llm.generate(msgs, SamplingParams(max_tokens=1, temperature=0.0, seed=0))
        t_prefill = max(time.perf_counter() - t0, 1e-6)
        res.prefill_tps = n_prompt / t_prefill

        t0 = time.perf_counter()
        out = llm.generate(msgs, SamplingParams(max_tokens=decode_tokens,
                                                temperature=0.0, seed=0))
        t_total = max(time.perf_counter() - t0, 1e-6)
        t_decode = max(t_total - t_prefill, 1e-6)
        try:
            n_out = llm.count_tokens(out)
        except Exception:
            n_out = max(1, len(out) // 4)
        res.decode_tps = n_out / t_decode

        res.ok = True
    except Exception as exc:
        res.error = f"{type(exc).__name__}: {exc}"
    return res


# ---------------------------------------------------------------------------
# Selection + cache
# ---------------------------------------------------------------------------

@dataclass
class ProbeResult:
    version: int
    fingerprint: str
    hardware: dict
    # Winner per workload — this is the whole point of measuring.
    prefill_backend: str = "cpu"
    decode_backend: str = "cpu"
    benchmarks: list[dict] = field(default_factory=list)
    measured: bool = False

    def banner(self) -> str:
        mode = "measured" if self.measured else "assumed"
        return (f"backends [{mode}]  prefill={self.prefill_backend}  "
                f"decode={self.decode_backend}")


def _cache_path(cache_dir: str | os.PathLike | None) -> Path:
    base = Path(cache_dir) if cache_dir else Path(
        os.environ.get("GENESIS_HOME", Path.home() / ".genesis"))
    base.mkdir(parents=True, exist_ok=True)
    return base / _CACHE_NAME


def load_cached(fingerprint: str,
                cache_dir: str | os.PathLike | None = None) -> ProbeResult | None:
    path = _cache_path(cache_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except Exception:
        return None
    if (data.get("version") != _PROBE_VERSION
            or data.get("fingerprint") != fingerprint):
        return None                       # hardware or driver changed
    try:
        return ProbeResult(**data)
    except TypeError:
        return None


def save_cached(result: ProbeResult,
                cache_dir: str | os.PathLike | None = None) -> None:
    try:
        _cache_path(cache_dir).write_text(json.dumps(asdict(result), indent=2))
    except Exception:
        pass                              # cache is an optimization, never required


def probe(candidates: dict[str, LLMBackend] | None = None,
          cache_dir: str | os.PathLike | None = None,
          force: bool = False) -> ProbeResult:
    """Detect hardware, then benchmark any provided candidate backends.

    `candidates` maps a runtime label ("rocm", "vulkan") to a live LLMBackend
    already pointed at a server built with that runtime. With no candidates
    the result is detection-only (`measured=False`) and falls back to the
    declarative preference order.
    """
    hw = detect_hardware()

    if not force:
        cached = load_cached(hw.fingerprint, cache_dir)
        if cached is not None:
            return cached

    ranked = preference_order(hw.runtimes)
    result = ProbeResult(
        version=_PROBE_VERSION,
        fingerprint=hw.fingerprint,
        hardware=asdict(hw),
        prefill_backend=ranked[0] if ranked else "cpu",
        decode_backend=ranked[0] if ranked else "cpu",
    )

    if candidates:
        benches = [micro_benchmark(be, label) for label, be in candidates.items()]
        result.benchmarks = [asdict(b) for b in benches]
        good = [b for b in benches if b.ok]
        if good:
            result.prefill_backend = max(good, key=lambda b: b.prefill_tps).label
            result.decode_backend = max(good, key=lambda b: b.decode_tps).label
            result.measured = True

    save_cached(result, cache_dir)
    return result

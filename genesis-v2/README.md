# Genesis v2

A local, always-on learning agent. Portable by construction.

**Status:** Phase 0 — compute abstraction landed. See
[`../PROJECT_BOARD.md`](../PROJECT_BOARD.md) for the plan and
[`../docs/v2/`](../docs/v2/) for the design record.

## Design commitments

1. **The engine runs on anything.** CUDA is an optimization, never an
   assumption. Vendor names live only in `genesis/backends/` and CI fails the
   build if they leak. Inference goes through `llama.cpp`/GGUF, whose backend
   list (CUDA, ROCm, Vulkan, SYCL, Metal, CANN, MUSA, …) is the widest
   available; the same `.gguf` runs on all of it.
2. **Measure, don't guess.** Backend performance splits by *workload* — on
   RDNA4, ROCm wins prefill (4903 t/s) while Vulkan wins decode (124 t/s). The
   startup probe micro-benchmarks and pins a winner per workload, cached
   against a hardware fingerprint.
3. **Aliases, not hardware.** Callers ask for `llm.main`, never for a model
   file, a device, or a quantization scheme. Swapping silicon and swapping
   model are the same one-line config change.
4. **Only plain Python and NumPy cross the boundary.** No tensors, no device
   handles, no vendor exceptions.
5. **The scoreboard comes before the player.** v1 ran eight months without an
   evaluation harness and could not tell a stalled system from a slow one.

## Quick start

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q          # 31 tests, no model required
python tools/lint_vendor_strings.py .
```

Everything is testable without a GPU or a running model: `genesis/backends/fake.py`
provides deterministic doubles whose embeddings have real geometry, so
retrieval and clustering logic can be tested meaningfully rather than trivially.

## Layout

```
genesis/backends/
  base.py       four interfaces + typed errors + alias registry
  llamacpp.py   llama-server client (generation, embeddings, reranking)
  probe.py      hardware detection, micro-benchmark, per-workload selection
  fake.py       deterministic test doubles
tools/
  lint_vendor_strings.py   CI guard: portability + trust-namespace separation
```

"""
Contract tests for the backend abstraction — no model required.

These are layer 1 of the testing strategy: fast, deterministic, covering the
orchestration logic and the portability invariants. They must stay runnable
on a machine with no GPU and no llama-server.

lint:allow-trust-join — this file deliberately constructs the forbidden
source_trust/holder_authority pattern as a fixture, to prove the linter
detects it. The marker is explicit and greppable by design: a genuine
violation cannot be waved through merely by living in tests/.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from genesis.backends.base import (          # noqa: E402
    BackendRegistry, BackendUnavailable, Capabilities, ContextOverflow,
    Message, ModelNotFound, SamplingParams,
)
from genesis.backends.fake import (          # noqa: E402
    FakeEmbedding, FakeLLM, FakeReranker, FakeTrainer, UnavailableLLM,
)
from genesis.backends import probe as probe_mod   # noqa: E402


# ── SamplingParams validation ────────────────────────────────────────────────

def test_sampling_params_rejects_bad_values():
    with pytest.raises(ValueError):
        SamplingParams(max_tokens=0)
    with pytest.raises(ValueError):
        SamplingParams(temperature=-1)
    with pytest.raises(ValueError):
        SamplingParams(top_p=0.0)


def test_sampling_params_is_frozen():
    p = SamplingParams()
    with pytest.raises(Exception):
        p.temperature = 1.5          # type: ignore[misc]


# ── LLM contract ─────────────────────────────────────────────────────────────

def test_fake_llm_is_deterministic():
    a, b = FakeLLM(), FakeLLM()
    msgs = [Message(role="user", content="wolves hunt deer in packs")]
    assert a.generate(msgs) == b.generate(msgs)


def test_scripted_response():
    llm = FakeLLM(responses={"capital of France": "Paris"})
    out = llm.generate([Message(role="user", content="the capital of France?")])
    assert out == "Paris"


def test_context_overflow_is_typed_not_generic():
    llm = FakeLLM(context_length=10)
    with pytest.raises(ContextOverflow) as exc:
        llm.generate([Message(role="user", content=" ".join(["word"] * 500))])
    assert exc.value.limit == 10
    assert exc.value.requested > 10


def test_health_returns_false_rather_than_raising():
    assert FakeLLM().health() is True
    assert UnavailableLLM().health() is False       # must not raise


def test_token_counting_is_available_without_importing_a_tokenizer():
    llm = FakeLLM()
    assert llm.count_tokens("one two three") == 3
    assert llm.count_tokens("") == 1                # never zero-length


def test_stream_defaults_to_single_yield():
    llm = FakeLLM(responses={"x": "hello world"})
    assert list(llm.generate_stream([Message(role="user", content="x")])) == ["hello world"]


# ── Embedding contract ───────────────────────────────────────────────────────

def test_embeddings_are_normalized_and_shaped():
    emb = FakeEmbedding(dim=32)
    vecs = emb.embed(["alpha beta", "gamma"], kind="doc")
    assert vecs.shape == (2, 32)
    assert vecs.dtype == np.float32
    assert np.allclose(np.linalg.norm(vecs, axis=1), 1.0, atol=1e-5)


def test_embeddings_have_real_geometry():
    """Similar texts must be closer — otherwise retrieval tests are vacuous."""
    emb = FakeEmbedding(dim=128)
    v = emb.embed(["wolves hunt deer",
                   "wolves hunt elk",
                   "quantum chromodynamics lattice"])
    assert float(v[0] @ v[1]) > float(v[0] @ v[2])


def test_query_and_doc_encodings_differ():
    emb = FakeEmbedding(dim=32)
    q = emb.embed(["rivers"], kind="query")
    d = emb.embed(["rivers"], kind="doc")
    assert not np.allclose(q, d)


def test_empty_embed_returns_empty_array():
    emb = FakeEmbedding(dim=16)
    assert emb.embed([]).shape[0] == 0


def test_embedder_exposes_stable_model_id():
    """Stored with every vector so a future migration knows what made it."""
    assert FakeEmbedding().model_id == "fake-embed-v1"


# ── Rerank + trainer contracts ───────────────────────────────────────────────

def test_reranker_scores_align_with_docs_and_rank_correctly():
    rr = FakeReranker()
    docs = ["paris is the capital of france", "mitochondria are organelles"]
    scores = rr.rerank("what is the capital of france", docs)
    assert len(scores) == len(docs)
    assert scores[0] > scores[1]


def test_reranker_handles_empty_docs():
    assert FakeReranker().rerank("q", []) == []


def test_trainer_loss_decreases_and_roundtrips(tmp_path):
    tr = FakeTrainer(in_dim=4, out_dim=2)
    rng = np.random.default_rng(0)
    x = rng.normal(size=(64, 4)).astype(np.float32)
    y = (x @ np.array([[1, 0], [0, 1], [1, 1], [0, 0]], np.float32))
    first = tr.fit_step({"x": x, "y": y})
    for _ in range(60):
        last = tr.fit_step({"x": x, "y": y})
    assert last < first

    path = str(tmp_path / "w.npy")
    tr.save(path)
    before = tr.predict(x[:2])
    tr2 = FakeTrainer(in_dim=4, out_dim=2)
    tr2.load(path)
    assert np.allclose(before, tr2.predict(x[:2]))


def test_trainer_returns_numpy_not_tensors():
    tr = FakeTrainer(in_dim=3, out_dim=1)
    assert isinstance(tr.predict(np.zeros((2, 3), np.float32)), np.ndarray)


# ── Registry: aliases are the caller's whole vocabulary ──────────────────────

def test_registry_resolves_aliases():
    reg = BackendRegistry()
    llm, emb = FakeLLM(), FakeEmbedding()
    reg.register("llm.main", llm)
    reg.register("embed.default", emb)
    assert reg.llm() is llm
    assert reg.embedder() is emb
    assert "llm.main" in reg
    assert reg.aliases() == ["embed.default", "llm.main"]


def test_unknown_alias_raises_typed_error_listing_options():
    reg = BackendRegistry()
    reg.register("llm.main", FakeLLM())
    with pytest.raises(ModelNotFound) as exc:
        reg.get("llm.nope")
    assert "llm.main" in str(exc.value)


def test_registry_rejects_malformed_alias():
    with pytest.raises(ValueError):
        BackendRegistry().register("noDotHere", FakeLLM())


# ── Capability probe ─────────────────────────────────────────────────────────

def test_detect_hardware_always_reports_cpu_last():
    hw = probe_mod.detect_hardware()
    assert hw.runtimes[-1] == "cpu"
    assert hw.cpu_count >= 1
    assert hw.fingerprint
    assert hw.banner()


def test_preference_order_is_declarative_and_env_overridable(monkeypatch):
    detected = ["vulkan", "rocm", "cpu"]
    assert probe_mod.preference_order(detected)[0] == "rocm"      # default table
    monkeypatch.setenv("GENESIS_BACKEND_PREFERENCE", "vulkan,cpu")
    assert probe_mod.preference_order(detected)[0] == "vulkan"


def test_probe_without_candidates_is_detection_only(tmp_path):
    res = probe_mod.probe(cache_dir=tmp_path, force=True)
    assert res.measured is False
    assert res.prefill_backend and res.decode_backend
    assert res.banner()


def test_probe_measures_and_splits_backends_per_workload(tmp_path):
    """The RDNA4 finding: one backend can win prefill while another wins
    decode. The probe must be able to express that, not pick one winner."""
    fast_prefill = FakeLLM()
    fast_decode = FakeLLM()

    def fake_bench(llm, label, decode_tokens=32):
        return probe_mod.BenchResult(
            label=label,
            prefill_tps=5000.0 if label == "rocm" else 1900.0,
            decode_tps=97.0 if label == "rocm" else 124.0,
            ok=True,
        )

    orig = probe_mod.micro_benchmark
    probe_mod.micro_benchmark = fake_bench
    try:
        res = probe_mod.probe({"rocm": fast_prefill, "vulkan": fast_decode},
                              cache_dir=tmp_path, force=True)
    finally:
        probe_mod.micro_benchmark = orig

    assert res.measured is True
    assert res.prefill_backend == "rocm"
    assert res.decode_backend == "vulkan"


def test_failed_candidate_is_never_selected(tmp_path):
    res = probe_mod.probe({"broken": UnavailableLLM()}, cache_dir=tmp_path,
                          force=True)
    assert res.measured is False          # no usable candidate -> fall back
    assert res.benchmarks and res.benchmarks[0]["ok"] is False


def test_probe_result_is_cached_and_reused(tmp_path):
    first = probe_mod.probe(cache_dir=tmp_path, force=True)
    second = probe_mod.probe(cache_dir=tmp_path)
    assert second.fingerprint == first.fingerprint
    assert (tmp_path / "backend_probe.json").exists()


def test_cache_invalidated_by_fingerprint_change(tmp_path):
    probe_mod.probe(cache_dir=tmp_path, force=True)
    assert probe_mod.load_cached("different-hardware", cache_dir=tmp_path) is None


# ── Portability invariant, enforced ──────────────────────────────────────────

def test_no_vendor_strings_outside_backends():
    """The lint rule is itself under test — it is the only thing that
    reliably holds this invariant in a solo codebase."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "lint_vendor_strings.py"), str(ROOT)],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_lint_catches_a_planted_vendor_string(tmp_path):
    pkg = tmp_path / "genesis" / "memory"
    pkg.mkdir(parents=True)
    (pkg / "leak.py").write_text("import torch\nx = torch.Tensor([1]).cuda()\n")
    from tools.lint_vendor_strings import check          # noqa: PLC0415
    problems = check(tmp_path)
    assert any("cuda" in p or "torch.Tensor" in p for p in problems)


def test_lint_catches_cross_namespace_trust_join(tmp_path):
    pkg = tmp_path / "genesis" / "memory"
    pkg.mkdir(parents=True)
    (pkg / "q.py").write_text(
        'SQL = "SELECT * FROM source_trust JOIN holder_authority USING(id)"\n')
    from tools.lint_vendor_strings import check          # noqa: PLC0415
    assert any("holder_authority" in p for p in check(tmp_path))


def test_lint_allows_vendor_strings_inside_backends(tmp_path):
    pkg = tmp_path / "genesis" / "backends"
    pkg.mkdir(parents=True)
    (pkg / "rocm_thing.py").write_text('RUNTIME = "rocm"\n')
    from tools.lint_vendor_strings import check          # noqa: PLC0415
    assert check(tmp_path) == []

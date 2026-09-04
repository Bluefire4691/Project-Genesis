# Running the first test — RX 9070 XT, Windows

You need **one thing**: an OpenAI-compatible endpoint serving a local model.
Any of the three routes below gives you that. Pick the first one that works
and move on — the falsification test does not care which serves it.

> **Throughput does not matter here.** The test reads a few dozen documents.
> Even the slowest option finishes it. Backend benchmarking is board item
> 0.2b and comes *later*, once the experiment has an answer.

---

## Route A — LM Studio *(easiest, recommended for the first run)*

1. Install from **<https://lmstudio.ai>**.
2. Search in-app for **`Qwen3 8B`**, download a **Q4_K_M** GGUF (~5 GB).
   LM Studio detects the 9070 XT and picks a GPU runtime for you.
3. Left sidebar → **Developer** (`>_` icon) → load the model → **Start Server**.
4. Note the port — LM Studio uses **1234** by default.

```bat
set GENESIS_LLM_URL=http://127.0.0.1:1234/v1/chat/completions
```

Why this first: one installer, a built-in model browser, automatic AMD GPU
detection, and a server toggle. No scripting, nothing to go wrong.

---

## Route B — Ollama

1. Install from **<https://ollama.com/download>** (ships ROCm support for AMD).
2. In a terminal:
   ```bat
   ollama pull qwen3:8b
   ollama serve
   ```

```bat
set GENESIS_LLM_URL=http://127.0.0.1:11434/v1/chat/completions
```

> I argued against Ollama earlier on **performance** — its llama.cpp
> vendoring lags and benchmarks ~54–65% slower on AMD. That matters for the
> always-on agent later. It is irrelevant for running this experiment.

---

## Route C — llama.cpp directly *(fastest, most setup)*

```bat
setup_llamacpp.bat
setup_llamacpp.bat -Backend rocm    :: RDNA4 is supported; wins prefill
setup_llamacpp.bat -Backend cpu     :: last resort, still works
```

Default endpoint is `http://127.0.0.1:8080/v1/chat/completions`, which is
what the code already expects — no env var needed.

**If the script can't find an asset**, do it by hand in ~5 minutes:

1. Open <https://github.com/ggml-org/llama.cpp/releases>
2. Grab a recent build's `llama-<build>-bin-win-vulkan-x64.zip`
   (or `...-hip-radeon-x64.zip` for ROCm)
3. Extract so `llama-server.exe` sits directly in `Project-Genesis\llama\`
4. Put any **Qwen3-8B Q4_K_M** `.gguf` in `Project-Genesis\models\`
5. Run:
   ```bat
   llama\llama-server.exe -m models\Qwen3-8B-Q4_K_M.gguf ^
       --host 127.0.0.1 --port 8080 -c 8192 -ngl 99 --jinja
   ```

---

## Then, in a second terminal

```bat
preflight.bat
```

If you used Route A or B, set `GENESIS_LLM_URL` **in that same terminal**
first — preflight checks port 8080 by default.

When it's green:

```bat
cd project-genesis
python falsification_test.py --corpus both
python falsification_test.py --corpus live --glossary
```

---

## What to send back

From the **`live`** corpus specifically (the designed corpus only measures a
ceiling — see the construct warning the script prints):

| Metric | v1 baseline | Meaning |
|---|---|---|
| **Inference reach** | **0** | Derived relations. The headline: did it leave zero? |
| **Bridge nodes** | **1** | Concepts that are both subject and object — what makes chains possible |
| **Max chain** | **2** | Longest reasoning path |
| **Singleton rate** | **94%** | Concepts appearing once — the garbage proxy |

Also glance at **triples proposed vs. kept**. If the LLM arm looks bad *and*
that ratio is poor, the **prompt** failed, not the architecture — fixable,
not a verdict.

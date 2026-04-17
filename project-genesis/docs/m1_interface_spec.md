# M1 Interface Specification
## The Survival OS Contract

*Version 1.0 — April 2026*

---

## Purpose

The architecture amendment (v0.2, Section 6) commits to evolutionary layering: M1 is the
permanent substrate, not a stepping stone. M2 through M14 sit on top of M1 and depend on
its behavior. That dependency must be explicit and frozen early, because:

- Fixing bugs in M1 after M8+ are built requires knowing exactly what those layers depend on.
- Refactoring M1 internals is safe as long as the contract below is honored.
- Violating the contract is breaking the substrate.

This document defines what higher layers **can count on** from M1. It does not specify
implementation. The implementation of M1 can be corrected, optimized, or rewritten. The
contract cannot be changed without a version bump and explicit review of all dependents.

---

## The Contract

### `SurvivalOS.tick(orchestrator_stats: dict | None) → dict`

**Called:** once per cognitive cycle, before any processor dispatch.

**Guarantees:**
1. Never raises an exception. Returns a valid dict even if internal systems fail.
2. Returns a dict containing at minimum:
   ```python
   {
       "tick": int,          # monotonically increasing, starts at 1
       "energy": float,      # 0.0–1.0; 1.0 = full resources, 0.0 = critical
       "throttle": str,      # one of: "NONE", "LIGHT", "MODERATE", "CRITICAL", "EMERGENCY"
       "pressure": float,    # 0.0–1.0; aggregate directive pressure
       "most_urgent": str,   # name of the most pressure-demanding directive
       "capabilities": list, # sorted list of currently available capability strings
   }
   ```
3. `tick` count is strictly increasing across the lifetime of the SurvivalOS instance.
4. `energy` decreases under real resource load and recovers when load drops.
5. `throttle` only increases by at most one level per tick (hysteresis: requires 2
   consecutive ticks at a new pressure level before transitioning). It can drop
   multiple levels at once on recovery.

**Higher layers must not:**
- Skip calling `tick()` to avoid overhead. The survival cycle must run every cognitive
  cycle regardless of what higher layers decide to do.
- Assume the tick dict contains any keys beyond those listed above without checking.

---

### `SurvivalOS.can(capability: str) → bool`

**Called:** before dispatching any processor or memory operation.

**Guarantees:**
1. Never raises an exception.
2. Returns `True` if and only if `capability` is in the current throttle level's
   available capability set.
3. The capability strings are stable identifiers:

   | Capability | What it gates |
   |-----------|---------------|
   | `"text"` | TextProcessor dispatch. Last to drop; never absent. |
   | `"numeric"` | NumericProcessor dispatch |
   | `"pattern"` | PatternProcessor dispatch |
   | `"memory_search"` | Long-term memory similarity search |
   | `"memory_store"` | Writing new memories to long-term store |
   | `"logging"` | Non-critical logging operations |
   | `"curriculum"` | Curriculum stage evaluation and advancement |

4. `can("text")` always returns `True`. Text processing is the last-resort fallback;
   it is never throttled away.
5. Throttle escalation order (what drops first under pressure):
   `pattern` → `numeric` → `memory_search` → `logging` → `curriculum` → `memory_store`
   → (text never drops)

**Higher layers must not:**
- Proceed with a capability that `can()` has returned `False` for.
- Assume a capability is available because it was available on the previous cycle.
  Check `can()` every cycle.

---

### `SurvivalOS.safe_call(fn, *args, fallback=None, label="", **kwargs) → Any`

**Called:** wrapping any operation that could raise.

**Guarantees:**
1. Never raises an exception.
2. Returns the result of `fn(*args, **kwargs)` if it succeeds.
3. Returns `fallback` if `fn` raises any exception.
4. Logs the exception to the shared error log (accessible via `report()`).
5. `label` is recorded with the error entry for diagnostics.

**Higher layers must not:**
- Use bare `try/except` in place of `safe_call` for critical subsystem operations.
  The shared error log is how the system tracks its own health. Bypassing it breaks
  the resilience layer.

---

### `SurvivalOS.report() → dict`

**Called:** for monitoring and diagnostics. May be called any time.

**Guarantees:**
1. Never raises an exception.
2. Returns a nested dict with key `"survival_os"` containing:
   ```python
   {
       "survival_os": {
           "tick_count": int,
           "resource": {...},    # ResourceManager report
           "directives": {...},  # DirectiveEngine report
           "resilience": {...},  # ResilienceMonitor report (includes error_count)
       }
   }
   ```
3. The `"survival_os"` key is always present even if internal subsystems fail to report.

---

## What is NOT Guaranteed

The following are implementation details that higher layers must not depend on:

- The specific thresholds (memory MB, CPU ms) at which throttle levels change.
  These are configurable and may change between deployments.
- The exact energy normalization formula. `energy` is a 0.0–1.0 float; how it's
  computed from raw CPU/RSS is an implementation detail.
- The specific error log retention limit or error rate window. Use `report()` to
  get the current rate; don't assume the window size.
- The order of internal subsystem initialization in `__init__`.
- Whether `ResourceManager` uses `/proc/self/status` or `resource.getrusage()`.
  The implementation adapts to platform availability.

---

## Throttle Level Table (informational, not contractual)

These are the current defaults. The capability sets are contractual; the thresholds
that trigger each level are not.

| Level | Name | Available Capabilities |
|-------|------|----------------------|
| 0 | NONE | text, numeric, pattern, memory_search, memory_store, logging, curriculum |
| 1 | LIGHT | text, numeric, memory_search, memory_store, logging, curriculum |
| 2 | MODERATE | text, memory_store, logging |
| 3 | CRITICAL | text, memory_store |
| 4 | EMERGENCY | text |

---

## Versioning

This is **Interface Version 1.0**.

Any change to the guarantees above constitutes a breaking change and requires:
1. A version bump in this document.
2. Explicit review of all dependents (Orchestrator, any subsystem that calls `tick()`,
   `can()`, `safe_call()`, or `report()`).
3. A note in SESSION_LOG.md with rationale.

Changes to M1 *implementation* that honor the contract above do not require version
bumps. Fix bugs freely; honor the contract.

---

## Rationale

The subsumption architecture (Brooks 1986) that Genesis is modeled on has a specific
property: lower layers run continuously and cannot be fully overridden by higher layers —
they can only be suppressed or augmented. This spec enforces that property in code.

By documenting what the Orchestrator (Layer 2) can count on from M1, we make "permanent
substrate" a real commitment rather than a metaphor. If a future developer wants to
rewrite M1 for performance, they can — as long as this contract is satisfied. If a future
developer wants to add a new capability gate, they add it to this document first, get it
reviewed, then implement it.

The spec exists because the architecture amendment (Section 6) says:
> *Testing becomes layered: the bottom layer should be testable in isolation and should
> never be absent, even during higher-layer failures.*

A layer that can be tested in isolation needs a defined interface to test against.
This is that interface.

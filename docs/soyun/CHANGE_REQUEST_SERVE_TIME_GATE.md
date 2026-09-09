# CHANGE_REQUEST — serve-time buffer gate for speculative queue reuse

**From:** soyun (speculative inference) · **Branch:** `soyun/spec-abr` · **Date:** 2026-09-09
**To:** `run_plm.py` / speculative-CLI owner (`suy2136`), `rl_policy.py` owner
**Status:** DRAFT — awaiting review
**Prerequisite reading:** [[DRAFTER_ABLATION]] §S (safety metric), §S.7 (verdict), §8 (Task 0 classification)

---

## 1. Problem — the total-rebuffering gate blocks deployment

The drafter replacement ([[DRAFTER_ABLATION]] §2) is the first speculative
configuration to clear **speedup 1.0× and 1.24×** (`repeat-last` k3 = 1.419× at
q 37.8 %, vs the parameter sweep's 0.97× ceiling). It is held back by one gate:

| gate | threshold (pre-fixed) | result |
|---|---|---|
| incidence — queue serve no likelier to rebuffer than an LLM call | C ≤ 2× the mpc control | **PASS** (C ≤ 0.97× mpc) |
| **total rebuffering** | ≤ 0.64 s (10 % of A1's 6.39 s) | **FAIL** — 18.5–37.1 s (2.9–5.8× A1) |

Evidence: [[DRAFTER_ABLATION]] §2 (table), §S.6, and **`fig4`**
(`results/soyun/figures/fig4_drafter_comparison.png` — Δrebuffer bar and the
by-buffer-band agreement panel).

## 2. Cause — draft/execute buffer drain

`decisions.jsonl` (`results/soyun/drafter_ab_20260908/*/decisions.jsonl`,
distilled in `results/soyun/derived/`) localises it precisely (§S.6(3)):

- A `queue_serve` decision runs a bitrate that the drafter proposed **k chunks
  earlier**. Between draft and execution the buffer can drain.
- Almost all queue-serve rebuffering lands in the **`< 5 s` buffer band**. The
  **`≥ 20 s` band — 76 % of all queue serves — contributes zero**.
- `hybrid`'s route-time buffer check does not help: at draft time the buffer was
  still high, so it routes to `repeat-last`; the drain happens afterwards.
- Sharpest case: **`m5_hybrid_k5`, `< 5 s` band — 7 queue serves, mean chunk
  rebuffering 1.46 s** (vs ~0.00 s for queue serves in every other band).

| phase | `<5s` queue serves | mean queue rebuffer (s/chunk) | window-union rebuffer in `<5s` (s) |
|---|---:|---:|---:|
| m2 repeat k3 | 5 | 0.339 | 7.33 |
| m3 hybrid k3 | 3 | 0.000 | 9.48 |
| m4 repeat k5 | 2 | 0.028 | 7.68 |
| m5 hybrid k5 | 7 | **1.462** | 16.02 |

## 3. Request — minimal diff for a first-class serve-time buffer floor

A queued action should not be served when the buffer is already below a floor;
fall back to one real LLM call instead. The queue-serve branch
(`rl_policy.sample_speculative`, `rl_policy.py:902-933`) already computes
`validation = validate_speculative_observation(observed_state=state, …)` and has
`buffer_size` in scope. The floor is one extra comparison.

**Proposed diff (≈ 11 lines across 3 files; team files ≈ 6 lines):**

### 3a. `plm_special/speculative/acceptance.py` — soyun-owned, backward-compatible (~5 lines)

```python
def validate_speculative_observation(
    observed_state, predicted_state, observed_return, predicted_return,
    buffer_tolerance_seconds, state_tolerance, return_tolerance,
    serve_buffer_floor_seconds=0.0,          # NEW, default = disabled
):
    ...
    # after buffer_error / state_error / return_error are computed:
    reason = None
    observed_buffer_seconds = float(observed[1, -1]) * BUFFER_NORM_FACTOR   # NEW
    if serve_buffer_floor_seconds > 0 and observed_buffer_seconds < serve_buffer_floor_seconds:
        reason = 'buffer'                     # NEW — reuse the existing reason/counter
    elif buffer_error > buffer_tolerance_seconds:
        reason = 'buffer'
    elif state_error > state_tolerance:
        ...
```

`serve_buffer_floor_seconds=0.0` keeps every existing caller byte-identical
(confirmed by the tolerance-0 regression battery, §5).

### 3b. `plm_special/models/rl_policy.py` — **team file, 3 lines**

```python
# __init__ signature + body:
    speculative_serve_buffer_floor=0.0,                              # NEW arg
    ...
    self.speculative_serve_buffer_floor = float(speculative_serve_buffer_floor)   # NEW

# sample_speculative, the existing validate_speculative_observation(...) call:
            validation = validate_speculative_observation(
                observed_state=state,
                predicted_state=queued["predicted_state"],
                ...
                return_tolerance=self.speculative_return_tolerance,
                serve_buffer_floor_seconds=self.speculative_serve_buffer_floor,   # NEW
            )
```

No new branch, no new counter, no change to `serve_verified_queue` /
`_fallback_sample` — a floor trip is already handled by the `else` path
(`_speculative_queue.clear()` → `buffer_mismatch_fallbacks += 1` →
`_fallback_sample`).

### 3c. `run_plm.py` — **team file, 3 lines**

```python
parser.add_argument('--speculative-serve-buffer-floor', type=float, default=0.0,
    help='refuse to serve a queued speculative action when the buffer is below '
         'this many seconds (0 disables)')
if args.speculative_serve_buffer_floor < 0:
    raise ValueError('--speculative-serve-buffer-floor must be non-negative')
# in the OfflineRLPolicy(...) construction (run_plm.py:442-447):
    speculative_serve_buffer_floor=args.speculative_serve_buffer_floor,
```

Recommended default from Task 1: **`<TBD from results>`** (§4 of this doc).

## 4. Impact analysis

| Surface | Impact |
|---|---|
| `acceptance.py` other callers | none — `build_acceptance_plan` untouched; `validate_speculative_observation`'s new kwarg defaults to disabled. Grep: only `rl_policy.sample_speculative` calls it. |
| `rl_policy.py` non-speculative path (`sample`, selectors) | none — the new field is only read inside the `if self._speculative_queue:` branch, which is unreachable when `speculative_draft_steps == 0`. |
| Selector modules (`selectors.py` / `event_selection.py` / `selection_layout.py`, other owner) | none — serve gate acts before any context is built; selector code path is not entered on a gated decision (it becomes a plain `_fallback_sample`, same as an existing buffer-tolerance miss). |
| NBS / trainer (`trainer.py`, `--nbs-v19`) | none — training does not call `sample_speculative`. |
| Existing results / regression fixtures | none when floor = 0 (the default). `abr_spec/tests/_reference_mpc_draft.py` and the tolerance-0 battery do not exercise `validate_speculative_observation` with a floor. |
| `decisions.jsonl` schema (`abr_spec/decision_trace.py`) | none — a gated demotion is an existing `fallback` / `reason='buffer'` record. |
| Metrics (`selector_metrics.json`) | `buffer_mismatch_fallbacks` and `fallback_calls` rise; `queued_actions_served` falls. All existing keys, no new key. |

## 5. Verification plan (post-merge)

1. **Regression — behaviour unchanged at floor 0:**
   `CUDA_VISIBLE_DEVICES="" .venv/bin/python -m pytest \
    adaptive_bitrate_streaming/tests/test_mpc_draft.py \
    adaptive_bitrate_streaming/tests/test_speculative_acceptance.py \
    abr_spec/tests/test_drafters.py -q` → must stay **40 passed**, incl. the
   60-case tolerance-0 `MPCRefactorRegressionTest` battery.
2. **End-to-end — floor 0 reproduces the ablation:** re-run `m1a_mpc_k3_sample`
   and `m2_repeat_k3` with `--speculative-serve-buffer-floor 0`; QoE / q /
   acceptance / fallback split must match `results/soyun/drafter_ab_20260908/`
   to the digit (as `m1a` reproduced SWEEP_SPEC `s0`, §3).
3. **Effect — floor `<REC>` reproduces Task 1:** re-run with the recommended
   floor; total rebuffering, speedup, QoE, and the §S metrics must match
   `results/soyun/serve_gate_20260909/` within latency noise.
4. **New unit test** (`abr_spec/tests/test_serve_gate.py`, soyun-owned): a
   `validate_speculative_observation` call with `serve_buffer_floor_seconds=5`
   and an observed buffer of 3 s returns `valid=False, reason='buffer'`; with a
   20 s buffer it is unaffected.

## 6. Alternative — no team file needed

`abr_spec/serve_gate.py` (committed, freeze `<FREEZE_2>`) already implements the
gate by monkeypatching `rl_policy.validate_speculative_observation` before
`run_plm.py` runs — the **same pattern** the fork already uses to inject the
drafter choice (`abr_spec/drafter_select.py`; see [[NEEDS_UPSTREAM]] note that
`run_plm.py` builds the drafter at a hard-coded site). It is enabled by
`abr_spec/run_wrapped.py --serve-buffer-floor N`.

- **Pro:** zero team-file change; Task 1 results are already produced this way.
- **Con:** the gate only exists when a run goes through `run_wrapped.py`; a bare
  `run_plm.py` invocation does not get it. Fine for soyun's experiments, not a
  property you would ship.

If the diff in §3 is not wanted, the monkeypatch stays as the deployment path
and this request reduces to: *acknowledge that `--serve-buffer-floor` lives on
the wrapper, not `run_plm.py`* — the same disposition as `--speculative-drafter`.

---

*Numbers in §4/§5 marked `<TBD>` / `<REC>` are filled once Task 1
(`results/soyun/serve_gate_20260909/`) completes.*

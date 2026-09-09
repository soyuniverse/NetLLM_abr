# CHANGE_REQUEST — promote the serve-time buffer gate to a first-class flag

**From:** soyun (speculative inference) · **Branch:** `soyun/spec-abr` · **Date:** 2026-09-09
**To:** `run_plm.py` / speculative-CLI owner (`suy2136`), `rl_policy.py` owner
**Status:** DRAFT — awaiting review
**Prerequisite reading:** [[DRAFTER_ABLATION]] §S.7, §8, §9 · [[SERVE_GATE_DIAGNOSIS]]

---

## 0. What this is (and is not)

This is **not** a request to unblock a feature. The serve-time buffer gate is
already implemented and measured — `abr_spec/serve_gate.py`, installed by
`abr_spec/run_wrapped.py`, monkeypatching `rl_policy.validate_speculative_observation`
before `run_plm.py` runs. That is the **same pattern** the fork already uses to
inject the drafter choice (`abr_spec/drafter_select.py`; `run_plm.py` builds the
drafter at a single hard-coded site, [[NEEDS_UPSTREAM]] closing note).

This request is to **promote** that validated knob to a first-class
`run_plm.py` CLI flag, so it works on a bare `run_plm.py` invocation and not only
through soyun's wrapper. If the team would rather it stay on the wrapper (the
same disposition as `--speculative-drafter`), this request reduces to an
acknowledgement and no code changes.

## 1. Why the gate exists

The drafter replacement ([[DRAFTER_ABLATION]] §2) is the first speculative
configuration to clear **speedup 1.0× and 1.24×** (`repeat-last` k3 = 1.419× at
q 37.8 %). It is held back by the **total-rebuffering** judgement: total
rebuffering rises from A1's 6.4 s to 18–37 s (§9). §S.6 localises the cause — a
handful of queue entries execute after the buffer has drained below ~5 s, drafted
several chunks earlier when the buffer was comfortable. The gate refuses those.

## 2. What the measurements say (`results/soyun/serve_gate_20260909/`)

- **The gate is drafter-dependent** (§9.1). It helps only `hybrid k5`, whose
  unprotected `< 5 s` queue serves directly caused 10.2 s of rebuffering; for
  every other drafter/k the same gate makes rebuffering worse.
- **`hybrid k5 + gate, floor 5 s` is the one 4/4 config** (§9.3): total
  rebuffering 18.5 → 7.0 s (Δ vs A1 +0.6 s), QoE −2.0 → −1.3 %, speedup 1.47×,
  incidence 0.56 → 0.26 %.
- **The `mode=fallback` response (demote to an LLM call) is a dead end**
  ([[SERVE_GATE_DIAGNOSIS]]): the sample-mode LLM picks an unsafe bitrate in a
  drained buffer and perturbing 3–5 decisions diverges the closed loop.
  **`mode=conservative` / `mode=safe-mode`** (serve a deterministic low bitrate,
  no LLM) is the direction — results in §9.6 `<FILL from batch 2>`.

## 3. The ask — minimal diff (~11 lines, 3 files; team files ≈ 6 lines)

Promote `--serve-buffer-floor` and `--serve-gate-mode`. The queue-serve branch
(`rl_policy.sample_speculative`, `rl_policy.py:902-933`) already computes
`validate_speculative_observation(observed_state=state, …)` and has `buffer_size`
in scope — the floor is one extra comparison; the response modes reuse the
existing `_fallback_sample` / `_append_observed_action` paths.

### 3a. `plm_special/speculative/acceptance.py` — soyun-owned, backward-compatible (~5 lines)

```python
def validate_speculative_observation(
    observed_state, predicted_state, observed_return, predicted_return,
    buffer_tolerance_seconds, state_tolerance, return_tolerance,
    serve_buffer_floor_seconds=0.0,                     # NEW, default = disabled
):
    ...
    observed_buffer_seconds = float(observed[1, -1]) * BUFFER_NORM_FACTOR   # NEW
    reason = None
    if serve_buffer_floor_seconds > 0 and observed_buffer_seconds < serve_buffer_floor_seconds:
        reason = 'buffer'                                # NEW — reuse the reason/counter
    elif buffer_error > buffer_tolerance_seconds:
        reason = 'buffer'
    elif ...
```

`serve_buffer_floor_seconds=0.0` keeps every existing caller byte-identical
(the tolerance-0 regression battery, §5, does not pass a floor).

### 3b. `plm_special/models/rl_policy.py` — **team file, ~3 lines**

```python
    speculative_serve_buffer_floor=0.0,                              # __init__ arg
    self.speculative_serve_buffer_floor = float(speculative_serve_buffer_floor)
    # in the existing validate_speculative_observation(...) call:
        serve_buffer_floor_seconds=self.speculative_serve_buffer_floor,
```

This covers `mode='fallback'` (the existing `else` path already clears the queue
and calls the LLM). `mode='conservative'` / `mode='safe-mode'` — the responses
§9.6 recommends — need ~6 more lines in `sample_speculative` (serve
`max(0, last_bitrate - 1)` directly instead of `_fallback_sample`). soyun will
send that as a follow-up diff once §9.6 names the mode; it is small and touches
only the `if self._speculative_queue:` branch.

### 3c. `run_plm.py` — **team file, ~3 lines**

```python
parser.add_argument('--speculative-serve-buffer-floor', type=float, default=0.0)
parser.add_argument('--speculative-serve-gate-mode',
                    choices=('fallback', 'conservative', 'safe-mode'), default='fallback')
if args.speculative_serve_buffer_floor < 0:
    raise ValueError('--speculative-serve-buffer-floor must be non-negative')
# pass both into OfflineRLPolicy(...) (run_plm.py:442-447)
```

## 4. Impact analysis

| Surface | Impact |
|---|---|
| `acceptance.py` other callers | none — only `rl_policy.sample_speculative` calls `validate_speculative_observation`; `build_acceptance_plan` untouched; new kwarg defaults to disabled. |
| `rl_policy.py` non-speculative path (`sample`, selectors) | none — the field is read only inside `if self._speculative_queue:`, unreachable when `speculative_draft_steps == 0`. |
| Selector modules (`selectors.py` / `event_selection.py` / `selection_layout.py`) | none — a gated decision never enters the selector path (it is a plain fallback / a forced serve, before any context is built). |
| NBS / trainer | none — training does not call `sample_speculative`. |
| Existing results & fixtures | none at floor 0 (the default). `abr_spec/tests/_reference_mpc_draft.py` and the tolerance-0 battery do not exercise a floor. |
| Metrics (`selector_metrics.json`) | `buffer_mismatch_fallbacks` / `fallback_calls` rise, `queued_actions_served` falls — all existing keys, no new key. `mode=safe-mode` adds a `low_buffer_safe` value to `last_selection_trace['stage']` (consumed only by soyun's `decision_trace.py`). |
| `decision_trace.py` schema | none for `fallback` / `conservative`; `safe-mode` adds the `low_buffer_safe` stage string (soyun-owned tracer, already handled). |

## 5. Verification plan (post-merge)

1. **Regression — behaviour unchanged at floor 0:**
   `CUDA_VISIBLE_DEVICES="" .venv/bin/python -m pytest \
    adaptive_bitrate_streaming/tests/test_mpc_draft.py \
    adaptive_bitrate_streaming/tests/test_speculative_acceptance.py \
    abr_spec/tests/test_drafters.py -q` → **40 passed** (incl. the 60-case
   tolerance-0 `MPCRefactorRegressionTest` battery).
2. **End-to-end — floor 0 reproduces the ablation:** `m1a_mpc_k3_sample` and
   `m2_repeat_k3` with the flag absent / at 0 must match
   `results/soyun/drafter_ab_20260908/` to the digit (as `m1a` reproduced
   SWEEP_SPEC `s0`, §3).
3. **Effect — the recommended config reproduces §9:** re-run it and match
   `results/soyun/serve_gate_20260909/` (behaviour) within latency noise.
4. **New unit test** (`abr_spec/tests/test_serve_gate.py`, soyun-owned):
   `validate_speculative_observation(..., serve_buffer_floor_seconds=5)` with an
   observed buffer of 3 s → `valid=False, reason='buffer'`; 20 s → unaffected.

## 6. Alternative — keep it on the wrapper (no team file)

`abr_spec/serve_gate.py` is complete and validated. Enabled by
`abr_spec/run_wrapped.py --serve-buffer-floor N --serve-gate-mode M`.

- **Pro:** zero team-file change; all of `serve_gate_20260909` is produced this way.
- **Con:** a bare `run_plm.py` run does not get the gate. Acceptable for soyun's
  experiments; not a property you would ship.

If §3 is declined, the disposition is: *`--serve-buffer-floor` lives on the
wrapper, like `--speculative-drafter`* — and this document is closed as
acknowledged.

## 7. Recommended default

`<FILL after DRAFTER_ABLATION §9.6 (batch 2) names the winning mode/floor. Batch 1
already gives one 4/4 config: hybrid k5 + mode=fallback + floor 5 s. If v2
conservative/safe-mode generalises to hybrid k3 as well, that becomes the
recommendation instead.>`

*The default in §3 is `0.0` / `fallback` regardless — the gate is opt-in.*

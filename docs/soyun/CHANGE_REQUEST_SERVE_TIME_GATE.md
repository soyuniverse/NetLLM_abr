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

## 2. What the measurements say (`results/soyun/serve_gate_20260909/`, 22 runs)

- **The gate is drafter-dependent** (§9). It helps only `hybrid k5`, whose
  unprotected `< 5 s` queue serves caused a 13 s rebuffer cascade on one trace;
  for every other drafter/k the same gate makes rebuffering worse.
- **`mode=fallback` (demote to an LLM call) is a dead end**
  ([[SERVE_GATE_DIAGNOSIS]]): the sample-mode LLM picks an unsafe bitrate in a
  drained buffer (repeat k5 gate trip: action 4 at buffer 4.0 s → 12.6 s
  rebuffer), and perturbing 2–5 decisions diverges the closed loop.
- **`mode=conservative` (serve one quality level down, deterministic, no LLM)
  on hybrid k5 + floor 5 s is the one 4/4 config** (§9.8): rebuffering 18.5 →
  **1.64 s** (Δ vs A1 −4.8 s), QoE −1.97 → **−0.05 %**, speedup **1.499×**,
  incidence 0.56 → 0.31 %. Only 3 gate trips.
- **`mode=safe-mode`** (force every low-buffer decision) over-corrects (115–261
  trips) and fails everywhere. **`conservative` does not generalise** to
  hybrid k3 (rebuffering 26.9 → 58.3 s — trajectory divergence) or repeat k3/k5
  (neutral).

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

## 7. Recommended default and the general fix

**The gate stays opt-in** (`--speculative-serve-buffer-floor 0`, `mode=fallback`
in §3). It is **not** a general safety fix — see §2 and
[[SERVE_GATE_DIAGNOSIS]]. The one configuration that passes all four judgement
criteria (DRAFTER_ABLATION §9.8) is narrow:

| | value |
|---|---|
| drafter | `hybrid`, k = 5 (`--speculative-draft-steps 5`, `--speculative-hybrid-buffer-threshold 5.0`) |
| gate | `--speculative-serve-buffer-floor 5.0 --speculative-serve-gate-mode conservative` |
| result | rebuffering 18.5 → **1.64 s** (0.26× A1), QoE −1.97 → **−0.05 %**, speedup **1.499×** (−1.5 % vs the same-session control), incidence C 0.559 → 0.306 % |
| why it works | that drafter/k's unprotected `< 5 s` queue serves caused a 13 s rebuffer cascade on one trace (stale-high queue); 3 conservative serves at the drain start prevent it |
| why it does not generalise | the same gate raises hybrid k3's rebuffering 26.9 → 58.3 s (deterministic trajectory divergence from 2–3 perturbed decisions); floor must be **exactly** 5 s (3 s is a no-op, 8 s over-triggers); `safe-mode` over-corrects everywhere |

So the `mode=conservative` follow-up diff to `rl_policy.py` (§3b, ~6 lines) is
worth taking **only if the team also adopts hybrid k5 as the speculative
operating point** — otherwise the useful default is still 0.

**The general fix is at draft time, not serve time.** The root cause is that the
drafter enqueues actions it cannot stand behind once the buffer drains. A
principled fix: the drafter (or `sample_speculative`'s enqueue loop) should not
enqueue a queue entry whose **predicted** buffer trajectory (`rollout.
predicted_buffers`, already computed in `mpc_draft.simulate_actions`) dips below
a floor. That is a `plm_special/speculative/mpc_draft.py` +
`plm_special/models/rl_policy.py` change of similar size to §3, and it would
protect every drafter, not just hybrid k5. soyun will scope it as a separate
change request once this one's disposition is known.

# CHANGE_REQUEST — serve-time buffer gate: **WITHDRAWN**

**From:** soyun (speculative inference) · **Branch:** `soyun/spec-abr` · **Date:** 2026-09-09
**To:** `run_plm.py` / speculative-CLI owner (`suy2136`), `rl_policy.py` owner
**Status:** **WITHDRAWN 2026-09-10** — no team-file change requested. See withdrawal note below.
**Prerequisite reading:** [[DRAFTER_ABLATION]] §S.7, §8, §9 · [[SERVE_GATE_DIAGNOSIS]] · [[TRAJECTORY_DIVERGENCE]] · [[RNG_CONTAMINATION_AUDIT]]

---

## Withdrawal note (2026-09-10)

**This change request is withdrawn. No change to `run_plm.py` / `rl_policy.py` /
`acceptance.py` is requested.**

Reason: the serve-time buffer gate has **no effect** once measured without the
`test.py` seed-once RNG confound. The one configuration that passed all four
criteria — `hybrid k5 + conservative + floor 5 s`, total rebuffering 18.5 → 1.6 s
at seed 1 — was a **contamination artefact**:

- Seeds {2, 3, 4}: the gate helps 1 / is byte-identical no-op 2 / hurts 1
  (+4.3 s) ([[DRAFTER_ABLATION]] §9.9).
- Re-measured with per-episode re-seeding (`abr_spec/reseed_per_episode.py`): the
  gate fires **one trip**, changes **one decision**, and moves total rebuffering
  by **0.0 s** ([[DRAFTER_ABLATION]] §9.11, [[TRAJECTORY_DIVERGENCE]] §6). The
  seed-1 "win" was a coincidental alignment between where the gate trips and
  where that particular RNG stream's pathological cascade happened to land.

The two things worth doing instead (§7): **[[NEEDS_UPSTREAM]] #6** (re-seed the
eval RNG per episode — an eval-harness fix, not this) and a **draft-time**
drain-aware enqueue rule (a separate change request, to be scoped once the
draft-time prototype is measured).

`abr_spec/serve_gate.py` and its wrapper flags stay in the tree as a research
knob (like `--speculative-drafter`) — the mechanism was worth building to *prove*
the negative and to power [[TRAJECTORY_DIVERGENCE]] — but they are **not proposed
for promotion**.

Everything below is **preserved as the investigation record** (what a first-class
flag would have cost, the impact analysis, the diagnosis). It is no longer an
"ask".

---

## 0. What this is (and is not)

This is **not** a request to unblock a feature. The serve-time buffer gate is
already implemented and measured — `abr_spec/serve_gate.py`, installed by
`abr_spec/run_wrapped.py`, monkeypatching `rl_policy.validate_speculative_observation`
before `run_plm.py` runs. That is the **same pattern** the fork already uses to
inject the drafter choice (`abr_spec/drafter_select.py`; `run_plm.py` builds the
drafter at a single hard-coded site, [[NEEDS_UPSTREAM]] closing note).

**Outcome (§7): do not promote it.** Once measured properly — across seeds and
with per-episode RNG re-seeding — the gate has no effect: it changes one decision
and moves rebuffering by zero (§9.9, §9.11). Its one seed-1 "win" was a
coincidental alignment between where the gate fires and where that RNG stream's
pathological cascade landed. The §3 diff below is kept as a record of what a
first-class flag *would* cost; §7 says what to do instead
([[NEEDS_UPSTREAM]] #6 + a draft-time change request).

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
- **`mode=conservative` on hybrid k5 + floor 5 s passed all four criteria at
  seed 1** (rebuffering 18.5 → 1.64 s, QoE −0.05 %) — **but this does not
  survive scrutiny**: seed {2,3,4} give help 1 / inert 2 / hurt 1 (§9.9), and
  under per-episode re-seeding the gate changes 1 decision and moves rebuffering
  by 0 (§9.11). The seed-1 win was a coincidental trip/cascade alignment.
- `mode=safe-mode` over-corrects (115–261 trips) and fails everywhere;
  `conservative` also hurts hybrid k3 (+31 s) and is inert on repeat k3/k5.
- **The dominant effect is the seed lottery in the un-gated baseline**
  ([[TRAJECTORY_DIVERGENCE]]) — see §7.

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

## 7. Recommendation — **do not promote this; take the eval-harness fix instead**

**Do not promote the serve gate.** The one config that passed all four criteria
at seed 1 (`hybrid k5 + conservative + floor 5 s`, rebuffering 18.5 → 1.64 s) is
**not real**: seed {2,3,4} give help 1 / inert 2 / hurt 1 (DRAFTER_ABLATION
§9.9), and re-measured with per-episode re-seeding
(`abr_spec/reseed_per_episode.py`) the gate changes **one decision** and moves
rebuffering **by zero** (§9.11). The seed-1 4/4 was a coincidental alignment
between where the gate trips and where that RNG stream's pathological cascade
happened to land.

So §3's diff is **not worth taking**. If the team wants the wrapper-side
`--serve-buffer-floor` acknowledged as a research knob (like `--speculative-drafter`),
that is fine; a first-class flag adds nothing.

**Two things are worth doing instead:**

1. **[[NEEDS_UPSTREAM]] #6 — re-seed the eval RNG per episode** (`test.py`,
   ~1 line). `set_random_seed` currently runs once for all 100 traces, so any
   mid-run intervention contaminates later traces and the un-gated baseline is a
   seed lottery (hybrid k5 rebuffering 0.49 / 4.24 / 18.5 / 25.6 s across seeds).
   This blocks a clean read of *any* serve-time or draft-time A/B, not just this
   gate. It does not change a single-config result.
2. **The draft-time fix (a separate change request).** The root cause is that the
drafter enqueues actions it cannot stand behind once the buffer drains. A
principled fix: the drafter (or `sample_speculative`'s enqueue loop) should not
enqueue a queue entry whose **predicted** buffer trajectory (`rollout.
predicted_buffers`, already computed in `mpc_draft.simulate_actions`) dips below
a floor. That is a `plm_special/speculative/mpc_draft.py` +
`plm_special/models/rl_policy.py` change of similar size to §3, and it would
protect every drafter, not just hybrid k5. soyun will scope it as a separate
change request once this one's disposition is known.

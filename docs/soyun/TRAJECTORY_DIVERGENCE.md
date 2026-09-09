# TRAJECTORY_DIVERGENCE — the cost of a serve-time intervention is contamination, not latency

**Date:** 2026-09-09 · **Author:** soyun · **Branch:** `soyun/spec-abr`
**Inputs:** `results/soyun/serve_gate_20260909/` (g_hybrid_k5_f5, v_hybrid_k5_f5_cons,
v_hybrid_k5_f5_safe) vs `results/soyun/drafter_ab_20260908/m5_hybrid_k5` — **log
analysis only, no new runs**. 관련: [[SERVE_GATE_DIAGNOSIS]] · [[DRAFTER_ABLATION]] §9

---

## The observation this quantifies

[[DRAFTER_ABLATION]] §9.6: v1 (`fallback`) and v2 (`conservative`) fire on the
**same 3 queue-serve decisions**, both serve **action 0**, both leave those 3
chunks with **rebuffer 0** — yet total rebuffering is **7.00 s vs 1.64 s**. The
difference is entirely downstream. This doc measures how far downstream, and why.

## 1. The gate trip is not local — it shifts the whole evaluation

`m5_hybrid_k5` (no gate) rebuffers on **3 traces**: 52 (3.37 s), 64 (2.02 s),
**94 (13.11 s)**. Trace 94 is the cascade — the hybrid-k5 queue is stuck
repeating bitrate 1 while the buffer is pinned at 4.0 s (t=38–42, five chunks,
2.3–3.5 s rebuffer each), only recovering when a `draft_verify` at t=43 finally
picks 0.

| trace | m5_ctrl | v1 `fallback` | v2 `conservative` |
|---:|---:|---:|---:|
| 52 | 3.37 | 1.22 | 1.22 |
| 64 | 2.02 | 0.00 | 0.00 |
| **79** | **0.00** | **5.78** | 0.00 |
| **94** | **13.11** | 0.00 | **0.41** |
| **total** | **18.51** | **7.00** | **1.64** |

- **v2 fixes trace 94 structurally.** Its gate trip at exactly `(trace 94, t=38,
  buffer 4.0 s)` serves action 0 instead of the stale 1; the buffer recovers
  4.0 → 5.2 → 6.8 → 8.1 next chunks; **no cascade** (0.41 s is the one chunk at
  t=37, before the gate could act).
- **v1 "fixes" trace 94 by accident.** In v1, trace 94's buffer never drains at
  all (37.8 s at t=34, not 14.5) — its *entire trajectory* is different. The gate
  trips at traces 52/57/86 relocated trace 94. v1 got lucky there and **unlucky
  on trace 79**, which had zero rebuffering un-gated and now has a 5.78 s cascade.

## 2. Divergence metric — post-trip action-mismatch rate vs the un-gated run

Global decision index (traces 0–99 in order, t ascending). First gate trip at
global position **2482 / 4700**. For every later decision, does the served action
match `m5_hybrid_k5`? Rate, in 100-decision buckets:

```
offset from 1st trip   v1 fallback          v2 conservative
   0–199                24 % (sustained)      1–3 %  (burst)
 300–599                28 %                  13–45 %  <- one region (traces ~59–64)
 600–2218                12–57 %, NEVER 0      0 %  for the entire rest of the run
overall                 608/2218 = 27.4 %     88/2218 = 4.0 %
per intervention        ~203 decisions        ~22 decisions
traces touched          45 / 100              9 / 100
```

**v1's divergence never damps** — it holds 20–57 % mismatch for all 2218
remaining decisions. **v2's is a local burst** (traces 59–64) that re-converges
to the baseline trajectory and stays at 0 % for the last ~2000 decisions.

## 3. Root cause — the evaluation RNG is seeded once, not per episode

`plm_special/test.py:42` calls `set_random_seed(args.seed)` **once, before the
`while True` episode loop** (line 44). `clear_dq()` (line 89) resets the model
deques and the drafter, **but not `random` / `numpy`**. So the sampling RNG
stream (`rl_policy._sample → random.choices`) is **continuous across all 100
traces**.

Any intervention that changes the **number of RNG draws consumed** in trace *N*
shifts the stream for traces *N+1 … 99*:

| path | `_sample` draws |
|---|---:|
| queue serve (un-gated) | 0 |
| gate trip → `conservative` (v2): clear queue, `_append_observed_action` | **0** at the trip; but the queue is now empty, so the **next** chunk does a fresh `draft_and_verify` → `_actions_from_verification_logits` samples **k = 5** draws it would not have |
| gate trip → `fallback` (v1): clear queue, `_fallback_sample` → `self.sample()` | **1** at the trip **+** the same k=5 next-chunk re-draft **+** a full stochastic LLM decision whose action feeds back into the DT history |

v2's per-trip shift is ~5 draws in a short burst; the LoRA policy's 88 % action
autocorrelation absorbs it within ~5 traces. v1's is larger (~6 draws **plus** a
different DT history embedding from the LLM forward), stays above the absorption
threshold, and never re-converges.

**safe-mode** (`v_hybrid_k5_f5_safe`): 115 forced serves, each bypassing
`sample_speculative` — the decision_trace patch never sees them, so its
`decisions.jsonl` is **4585 rows, not 4700** (the 115 trips are missing) and its
jsonl rebuffer sum (6.9 s) is wrong; the truth is `selector_metrics.json` =
**39.83 s**. 96 / 100 traces diverge. Forcing every low-buffer decision maximises
both the RNG shift and the direct trajectory perturbation.

## 4. Implications

1. **The serve gate's cost is trajectory contamination, not the ~80 ms LLM
   latency** ([[SERVE_GATE_DIAGNOSIS]] already ruled out latency; this is the
   positive account). The right response minimises RNG-draw disturbance:
   `conservative` (0 draws at the trip) ≫ `fallback` (1 + LLM) ≫ `safe-mode`.
2. **`v_hybrid_k5_f5_cons`'s trace-94 fix is structural** (the gate trip lands on
   the exact drain chunk), but its −16.9 s total is partly the absence of an
   RNG-shift-induced *new* cascade like v1's trace 79. Seed robustness (Task 1)
   tests whether the structural part survives a different RNG stream.
3. **Upstream note:** `test.py` re-seeding per episode (`set_random_seed` inside
   the `while` loop, or a per-episode `random.Random(seed + ep)`) would make
   every A/B here a paired within-trace comparison and remove the cross-trace
   contamination entirely. Filed as [[NEEDS_UPSTREAM]] #6.

## 5. fig6

`results/soyun/figures/fig6_trajectory_divergence.png` — post-trip action-mismatch
rate vs downstream distance, v1 fallback vs v2 conservative, with the per-trace
rebuffer bars (m5_ctrl / v1 / v2) inset.

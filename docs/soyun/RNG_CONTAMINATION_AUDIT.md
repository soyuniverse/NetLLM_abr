# RNG_CONTAMINATION_AUDIT — which of this project's results are exposed

**Date:** 2026-09-09 · **Author:** soyun · **Branch:** `soyun/spec-abr`
**Companions:** [[TRAJECTORY_DIVERGENCE]] (mechanism + serve-gate case),
[[TEAM_ALERT_RNG_CONTAMINATION]] (team-facing), [[NEEDS_UPSTREAM]] #6 (fix),
[[DRAFTER_ABLATION]] §9.9–9.11, [[SWEEP_SPEC]] §12

This document classifies every result campaign in the speculative-ABR work by
its exposure to the seed-once contamination, and records the direct check on the
one result that matters most (the drafter ablation headline).

---

## 1. The exposure criterion

`plm_special/test.py` seeds `random`/`numpy`/`torch` **once** before the
100-trace loop; `clear_dq()` does not re-seed. The stochastic sampler
(`rl_policy._sample → random.choices`) therefore draws from **one stream shared
across all traces**. A comparison of run A vs run B is **contaminated** only when
**all three** hold:

- **C1 — stochastic decode.** The decision path calls `random.choices` at all,
  i.e. `--speculative-verification-mode sample` and/or the non-speculative
  `sample()` head. `greedy` (argmax) draws nothing → immune.
- **C2 — divergent per-trace draw count.** A and B consume a *different number*
  of draws within a trace, so their stream positions drift apart as the run
  progresses. Draw budget per decision:

  | decision path | `random.choices` draws |
  |---|---:|
  | non-speculative `sample()` (one per chunk) | 1 |
  | speculative queue serve | 0 |
  | speculative `draft_and_verify`, sample mode | k (one per drafted step) |
  | speculative fallback (`_fallback_sample → sample`) | 1 |

  Two non-speculative runs both spend exactly 1/chunk → **streams stay aligned
  trace-for-trace, C2 fails, comparison is clean.** Two speculative runs with
  different drafters/gates spend different mixes of {0, 1, k} → C2 holds.
- **C3 — many-trace aggregation of an outlier-sensitive metric.** The reported
  number is a sum/mean over 100 traces of something a few traces dominate
  (total rebuffering; QoE via its rebuffer term). Latency / speedup / `q` /
  acceptance are averaged over 4,700 decisions and are **not** outlier-driven →
  C3 fails for them, they are effectively RNG-insensitive.

**Contaminated ⇔ C1 ∧ C2 ∧ C3.**

## 2. Campaign-by-campaign audit

| Campaign / result | C1 decode | C2 draw-count differs | C3 outlier metric | Verdict | Basis |
|---|---|---|---|---|---|
| **BASELINE6** — 6 conditions × speedup | sample (E is greedy) | **No** — every non-spec condition draws 1/chunk; the one speculative condition is compared on *speedup*, not rebuffering | speedup only | **SAFE** | speedup is a 4,700-decision mean; non-spec streams aligned |
| BASELINE6 — QoE deltas between conditions | sample | partly (spec vs non-spec) | QoE | **LOW RISK** — deltas are ≤1 pp and the ranking (Temporal+Token best) is a latency/token-count result, not a rebuffer result | [[BASELINE6]] |
| **SWEEP_SPEC** — "parameters cannot reach parity" (exclusion result) | sample | Yes (k / tolerance vary the mix) | **No** — the verdict is `q < 10 %` and speedup 0.90–0.93×, both RNG-insensitive | **SAFE (verdict)** | [[SWEEP_SPEC]] §8–9; q and latency carry it |
| SWEEP_SPEC — per-run QoE / rebuffer columns | sample | Yes | Yes | **AT RISK (point values)** — treat each as a seed-1 point; the *substitution* finding (fig3) is a fallback-*count* result, RNG-insensitive | [[SWEEP_SPEC]] §5 |
| SWEEP_SPEC — btol substitution (fig3) | sample | Yes | **No** — counts of buffer vs state fallbacks | **SAFE** | fallback tallies, not rebuffer sums |
| **DRAFTER ABLATION** — "repeat-last clears 1.0× and 1.24×" (headline, claim 3) | sample | Yes | **No** — speedup + `q`; `q` is set by the policy's 92 % action autocorrelation, not by which action is sampled | **SAFE** | §3 below (direct check) |
| DRAFTER ABLATION — 1-step match %, accepted-prefix | sample | Yes | **No** — 4,700-decision means | **SAFE** | §3 |
| DRAFTER ABLATION — "conditional success: rebuffering 2.9–5.8× A1" (secondary framing) | sample | Yes | **Yes** — total rebuffering, 1–2 traces dominate each seed | **NOT ROBUST — sign flips under reseed (§3.2); needs a seed sweep (G1) before any paper statement** | §9.9 seed sweep + §3 reseed check |
| DRAFTER ABLATION — cost-model fit (claim 5) | sample | Yes | **No** — fits `q → speedup` | **SAFE** | [[SWEEP_SPEC]] §12 |
| **SERVE GATE** — "v_hybrid_k5_f5_cons passes 4/4" | sample | Yes (gate trips) | Yes | **CONTAMINATED — withdrawn** | [[TRAJECTORY_DIVERGENCE]] §6; [[CHANGE_REQUEST_SERVE_TIME_GATE]] |
| SERVE GATE — "fallback ≫ conservative on the same 3 trips" (mechanism, claim 7) | sample | Yes | Yes | **AT RISK as a number, SOUND as a mechanism** — the *direction* (an LLM fallback in a drained buffer is worse than a deterministic step-down) is decision-level and reproduces under reseed | §9.6, §9.11 |
| **DETERMINISM battery** (40/40) | both | **No** — same seed, same code both runs | — | **SAFE** (and *depends* on seed-once; do not "fix" without re-baselining it) | [[DRAFTER_ABLATION]] §1 |
| `breakeven.py`, cost-model algebra | n/a | n/a | n/a | **SAFE** — post-hoc math on measured `q` | — |
| `validate_ckpt.py`, `gpu_fp16_diagnostic.py`, checkpoint hashes | n/a | n/a | n/a | **SAFE** — not in the eval loop | [[ASSETS]] |

**Bottom line:** every *headline* result (the two exclusion results and the
"repeat-last breaks the speedup wall" result) rests on `q`, latency, or
event *counts*, all RNG-insensitive → **SAFE**. Contamination only touches
**rebuffering/QoE magnitudes** in speculative sample-mode runs, and it fully
explains the serve-gate mirage.

## 3. Direct check — is the drafter ablation verdict contamination-robust?

**Method.** Re-ran three phases of `drafter_ab_20260908` with per-episode
re-seeding (`abr_spec/reseed_per_episode.py`, `--probe`, `seed + trace_idx` at
each `clear_dq()`), seed 1, `abr_spec/run_rng_audit.sh`. Exec path byte-identical
to the ablation freeze `0d137ce` for speculative/decision_trace/drafter_select;
run_wrapped.py is +34 lines of additive argparse, no behaviour change at the
defaults (`git diff 0d137ce HEAD -- abr_spec/run_wrapped.py`). Manifests record
`git_commit` = `1744fa6` and `reseed_per_episode.json` = `{"reseeds": 100}`.
Results in `results/soyun/rng_audit_20260909/` (`a1_reseed`, `m1a_mpc_k3_reseed`,
`m2_repeat_k3_reseed`).

Absolute latency is ~6–13 % lower this session than in `drafter_ab_20260908`
(GPU less loaded) — **do not compare ms across the two campaigns**; use the
within-session ratio vs the same session's A1.

| phase | latency (ms) | speedup vs same-session A1 | q | 1-step | QoE | ΔQoE % vs A1 | rebuffer (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| **seed-once** (`drafter_ab_20260908`) | | | | | | | |
| A1 (non-spec) | 80.63 | 1.00× | — | — | 0.9487 | — | 6.39 |
| m1a mpc k3 | 82.77 | 0.97× | 7.4 % | 16.3 % | 0.9564 | **+0.8** | 7.48 |
| m2 repeat-last k3 | 56.81 | **1.42×** | 37.8 % | 88.0 % | 0.9342 | **−1.5** | 23.85 |
| **reseed/episode** (`rng_audit_20260909`) | | | | | | | |
| A1 (non-spec) | 77.36 | 1.00× | — | — | 0.9412 | — | 19.10 |
| m1a mpc k3 | 71.98 | 1.07× | 7.0 % | 16.6 % | 0.9274 | **−1.5** | 50.98 |
| m2 repeat-last k3 | 50.52 | **1.53×** | 38.3 % | 88.1 % | 0.9429 | **+0.2** | 13.87 |

within-session **m2 / m1a latency ratio**: seed-once 1.46×, reseed 1.43× — stable.

### 3.1 What is robust

- **The headline (claim 3): repeat-last clears the speedup wall, mpc does not.**
  m2 speedup 1.42× → 1.53×; m1a 0.97× → 1.07×; m2/m1a ratio 1.46× → 1.43×.
  Direction and magnitude both hold. **Contamination-robust — confirmed.**
- **`q` / acceptance / 1-step match.** m2: q 37.8 → 38.3 %, 1-step 88.0 → 88.1 %.
  m1a: q 7.4 → 7.0 %. Essentially unchanged — as predicted, these are set by the
  policy's action autocorrelation, not by which action the sampler draws.

### 3.2 What is NOT robust — the QoE / rebuffering cost

The **sign flips** on both drafters:

- m2 ΔQoE vs A1: **−1.5 % (seed-once) → +0.2 % (reseed)**.
- m2 rebuffering: **23.85 s (worse than A1) → 13.87 s (better than reseed A1's 19.10)**.
- m1a ΔQoE: +0.8 % → −1.5 %; m1a rebuffering 7.48 s → 50.98 s.

Cause — **single-trace domination** (`rebuffer_after_s` summed per trace):

| run | total | trace carrying it |
|---|---:|---|
| seed-once m1a | 7.48 | trace 53 (4.4) + 43 (3.0) |
| seed-once m2  | 23.85 | trace 36 (10.4) + 13 (8.7) + 91 (4.6) |
| reseed m1a | 50.98 | **trace 74 = 44.9** (88 %) |
| reseed m2  | 13.87 | **trace 74 = 12.7** (92 %) |

Under reseed, both speculative runs blow up on **trace 74** (its seed is now
`1 + 74 = 75`); mpc handles that one trace far worse (44.9 s) than repeat-last
(12.7 s). Under seed-once, entirely different traces were the unlucky ones. This
is the [[DRAFTER_ABLATION]] §9.9 seed lottery: rebuffering totals — and the QoE
penalty, which is mostly the rebuffer term — are **dominated by 1–2 traces whose
identity the RNG stream picks**, and the across-seed σ (§9.9: 10.2 s on a 12.2 s
mean) exceeds every drafter-level difference. **A single seed cannot measure the
QoE/rebuffering cost, and its sign is not even stable.**

### 3.3 Verdict

**The drafter ablation's primary result is contamination-robust.** "Replacing the
drafter with repeat-last clears speedup 1.0× and 1.24×, driven by the policy's
action autocorrelation" survives per-episode re-seeding unchanged (claim 3, 4, 5,
and the 1-step / prefix / q evidence).

**The secondary "conditional success — at a QoE/rebuffering cost" framing does
NOT survive** and must not be stated from one seed: reseeding flips m2's ΔQoE
from −1.5 % to +0.2 % and its rebuffering from +17 s to −5 s vs A1, purely
because a different trace becomes the unlucky one. The honest statement is:
*"repeat-last trades ~0 mean latency-per-decision for a large speedup; its effect
on rebuffering/QoE is within the seed-to-seed noise and requires a seed sweep
(≥3 seeds, mean±σ) to characterise — see G1."* This does **not** mean
"repeat-last has no QoE cost" (reseed is just one more lottery draw); it means
the cost is unmeasured at n=1.

**No re-interpretation of the speedup conclusion is needed. The rebuffering/QoE
numbers throughout [[DRAFTER_ABLATION]] and [[PAPER_ASSETS_ABR]] should carry a
"seed-1 point, sign not stable" caveat until G1 runs.**

## 4. Recommended follow-ups (priority order)

1. **[[NEEDS_UPSTREAM]] #6** — re-seed per episode in `test.py`. One line; owned
   by the eval-harness maintainer; re-baseline the determinism battery in the
   same commit. Removes the confound for everyone, permanently.
2. **Drafter ablation seed sweep** (G1 in [[PAPER_ASSETS_ABR]] §5) — m2/m3/m4/m5/M6
   at seeds 2–4, report rebuffering/QoE as mean±std. ~75 min GPU. Needed before
   any paper states a rebuffering magnitude.
3. Keep `reseed_per_episode.py` as the standard overlay for every future
   serve-/draft-time A/B until #1 lands.

# SERVE_GATE_DIAGNOSIS — why the demote-to-LLM serve gate backfires

**Date:** 2026-09-09 · **Author:** soyun · **Branch:** `soyun/spec-abr`
**Inputs:** `results/soyun/serve_gate_20260909/` batch 1 (8 runs) +
`results/soyun/drafter_ab_20260908/` controls — **no new runs**, log analysis only.
관련: [[DRAFTER_ABLATION]] §S, §9 · [[CHANGE_REQUEST_SERVE_TIME_GATE]]

---

## Working hypothesis (soyun)

> demote-to-LLM is the cause. In a drained buffer the gate forces the slowest
> path (an LLM call); during that latency the buffer drains further. m5 improved
> because its unprotected loss (1.46 s/chunk) exceeded the LLM latency cost; the
> other conditions lost because loss (~0.3 s) < latency cost.

## Verdict — **PARTIALLY SUPPORTED, mechanism corrected**

- ✅ **demote-to-LLM *is* the cause.** Every serve gate that actually fires makes
  total rebuffering worse, except the one config (hybrid k5) whose unprotected
  loss is large.
- ✅ **m5 improved because unprotected loss > cost.** Its `< 5 s` queue serves
  directly caused **10.23 s** of rebuffering (of 18.5 s total); no other config's
  exceeded 1.7 s.
- ❌ **The cost is NOT LLM latency.** The gate barely changes the LLM-call count
  (repeat k3 **−4**, repeat k5 **−10**, hybrid k3 +11, hybrid k5 +32), and one
  inference is ~80 ms — three orders of magnitude below a multi-second rebuffer.
  The cost is two other things (below).

## Evidence

### 1. LLM-call count and the "latency drain" claim

| cond | ctrl LLM calls | gated LLM calls | Δ | gate trips |
|---|---:|---:|---:|---:|
| repeat k3 | 2925 | 2921 | **−4** | 4 |
| hybrid k3 | 2948 | 2959 | +11 | 3 |
| repeat k5 | 2730 | 2720 | **−10** | 5 |
| hybrid k5 | 2733 | 2765 | +32 | 3 |

Only **3–5 decisions per run** are demoted. The gate does not add a wave of LLM
calls, and 3–5 × 80 ms of extra inference cannot produce the +27…+31 s
rebuffering swings seen below. **The latency-drain mechanism is rejected.**

### 2. What the LLM actually serves at a gate trip

`decisions.jsonl`, the gate-trip chunks (`stage=fallback`, `reason=buffer`,
buffer < 5 s) vs the control's `< 5 s` queue serves:

| cond | ctrl `<5s` queue-serve actions | ctrl rebuf (s) | gate-trip LLM actions | gate-trip rebuf (s) |
|---|---|---|---|---|
| repeat k3 | `[0,0,0,1,0]` | `[0,0,0,1.7,0]` | `[1,1,0,0]` | **`[2.1,1.4,0,0]`** |
| repeat k5 | `[0,1]` | `[0,0.06]` | `[0,4,1,1,0]` | **`[0,12.6,2.9,1.7,0]`** |
| hybrid k3 | `[0,0,0]` | `[0,0,0]` | `[0,0,0]` | `[0,0,0]` |
| hybrid k5 | `[1,0,1,0,1,1,1]` | `[2.2,0,1.2,0,2.6,1.8,2.5]` | `[0,0,0]` | `[0,0,0]` |

**Mechanism (a): the LLM samples an unsafe (high) bitrate in a drained buffer.**
In `sample` mode the policy's action distribution at buffer ≈ 4 s still has mass
on mid/high levels. repeat k5's gate trips include an **action 4 at buffer 4.0 s
→ 12.6 s rebuffering** on that one chunk. The repeat-last queue, by contrast,
propagates the last executed action, which in an orderly drain is already 0–1.

hybrid k5 is the mirror image: its unprotected queue was **stuck repeating
bitrate 1** (`last_actions` all 1) from before the drain — that stale-high queue
is exactly what caused its 10.23 s of direct loss, and here the LLM's samples
(0, 0, 0) happened to be safer.

### 3. Loss removed vs harm added — same units (seconds of rebuffering)

| cond | A: unprotected loss removed | B: gate-trip direct harm | C: net Δrebuffer | divergence = C − (B − A) |
|---|---:|---:|---:|---:|
| repeat k3 | 1.70 | 3.52 | **+26.98** | **+25.16** |
| hybrid k3 | 0.00 | 0.00 | **+31.46** | **+31.46** |
| repeat k5 | 0.06 | 17.13 | +5.90 | −11.17 |
| hybrid k5 | 10.23 | 0.00 | **−11.51** | −1.27 |

**Mechanism (b): closed-loop trajectory divergence.** hybrid k3 changes **3**
decisions; none of them rebuffer (B = 0) and none of the removed serves were
harmful (A = 0), yet total rebuffering rises **+31 s** — entirely *elsewhere*.
An ABR control loop is chaotic: perturbing a handful of decisions relocates the
whole trajectory, and for hybrid k3 / repeat k3 it relocates it somewhere worse.
The only config where the gate helps (hybrid k5) is the one where the term it
*removes* (A = 10.23 s) dominates both the harm it adds and the divergence.

## Implication for v2

Both mechanisms point the same way: **do not hand a drained buffer to the
sampling LLM.** A gate that instead serves a **deterministic conservative
action** (one quality level down, or the floor) with **no LLM call**:

- eliminates mechanism (a) — the served action is safe by construction, never a
  high-bitrate sample;
- minimises mechanism (b) — the perturbation is deterministic and always toward
  the safe corner, not a random draw, so it should relocate the trajectory less
  and in a predictable direction;
- costs nothing in speedup — no PLM forward runs in the danger zone.

That is [[DRAFTER_ABLATION]] §9.6 (serve_gate v2, `mode=conservative` /
`mode=safe-mode`). The design principle: **in a buffer emergency what is needed
is a fast safe decision, not an accurate one.**

Whether v2 also beats the divergence term is empirical — §9.6 measures it. The
diagnosis only establishes that v2 is the right direction and that demote-to-LLM
(v1) is a dead end for every drafter except the one it accidentally rescues.

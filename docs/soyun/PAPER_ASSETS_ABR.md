# PAPER_ASSETS_ABR — Claims, Tables, Reproducibility, Gaps (2026-09-10)

**soyun / speculative inference for ABR (NetLLM fork), branch `soyun/spec-abr`.**
Companion to `results/soyun/figures/` (fig1–6 + captions), [[DRAFTER_ABLATION]],
[[SWEEP_SPEC]] §12, [[SERVE_GATE_DIAGNOSIS]], [[TRAJECTORY_DIVERGENCE]],
[[RNG_CONTAMINATION_AUDIT]]. This is the paper-writing entry point: what can be
claimed, with what evidence, plus what still can't.

**Instance / seed caveat up front.** Two classes of number:
- **Structural — speedup, `q` (call-reduction), draft/LLM agreement.** Robust.
  Confirmed across **4 seeds** ([[DRAFTER_ABLATION]] §9.13): `q` varies < 0.7 pp
  seed-to-seed. Speedup is a within-instance ratio (cross-session drift ~10 %,
  [[DRAFTER_ABLATION]] §9.4).
- **Outlier-driven — total rebuffering, QoE.** Every run's rebuffering is
  carried by 1–4 of the 100 traces (top-1 trace = 32–100 % of the total),
  **including the no-speculation A1 baseline** (6.4 / 15.2 / 12.7 / 33.3 s across
  seeds 1–4). These are reported as **4-seed mean ± std** (§9.13); a single seed
  cannot measure them, and the eval RNG being seeded once per 100-trace run
  (claim 8) is why. The earlier "rebuffering rises 2.9–5.8× A1" was a seed-1
  artifact — the 4-seed cost of a k=3 drafter is not distinguishable from zero.

---

## 1. Claim → Evidence Mapping

| # | Claim | Fig / Table | Key numbers | Statistical basis | Limitations / counterarguments |
|---|---|---|---|---|---|
| 1 | The speculative parameter space (draft length k, verification mode, buffer/state tolerance) **cannot reach latency parity** — it is an exclusion result. | Fig. 2; SWEEP_SPEC §8 | 11 runs, all q < 10 %, speedup 0.90–0.93×; break-even needs q = 14.63 %, optimistic sum of every axis = 11.9 % | 11 runs, 1 seed, single instance; each axis' best effect measured, interactions assumed sub-additive | Interactions could be super-additive (SWEEP_SPEC §9 argues not: each axis effect ~1 pp, need 1.5× the requirement); k capped at 5 by `run_plm.py` (NEEDS_UPSTREAM #5) |
| 2 | Loosening the buffer tolerance **substitutes** failures rather than fixing them — direct evidence that the *drafter*, not the acceptance gate, is the bottleneck. | Fig. 3 | btol 1→8 s: buffer fallbacks 236→43, state fallbacks 32→191, total 268→234 (82 % substitution; 100 % between btol 4 and 8); q saturates at 6.64 % | 4 tolerance points, 1 seed; `return_mismatch_fallbacks` = 0 in all 12 runs | 4 points only; the substitution is shown for mpc; a different drafter shifts *which* row catches the entry (claim 5 note) |
| 3 | **Replacing the drafter with "repeat the last action" clears speedup 1.0× and 1.24×** — the lines the parameter space could not. Root cause: the LoRA policy's action autocorrelation. | Fig. 1, Fig. 4; Table 1 | mpc draft/LLM 1-step match 16 %; repeat-last **88.5 ± 0.6 %** (4 seeds); accepted prefix 0.23 → 2.30/3; q 7.4 % → **38.2 ± 0.3 %**; speedup **1.49 ± 0.08×** (repeat-last k3, 4 seeds) | 4,700 decisions / 100 traces × **4 seeds** ([[DRAFTER_ABLATION]] §9.13); controlled (only the drafter changes); m1a reproduced SWEEP_SPEC s0 to the digit (freeze verified) | Speedup is a within-instance ratio; QoE/rebuffering cost is **not** part of this claim — see claim 3b |
| 3b | **At k=3 the speedup carries no QoE or rebuffering cost that is measurable at 4 seeds.** The "conditional success / rebuffering 2.9–5.8× A1" of the seed-1 write-up was an artifact of outlier-trace domination. | Table 1; [[DRAFTER_ABLATION]] §9.13 | repeat-last k3 ΔQoE **+0.4 ± 2.1 %**, Δrebuffering **+5 ± 23 s** vs same-seed A1; hybrid k3 −0.5 ± 2.5 % / +6 ± 12 s. A1's own rebuffering is 16.9 ± 11.6 s | 4 seeds, paired against same-seed A1; per-trace concentration checked (not trimmed) | Low statistical power (n=4, σ ≈ 20 s); the mean Δrebuffering is positive (+5–6 s) so a small cost cannot be excluded, only bounded below the seed noise. **k=5 is worse** (m4 Δrebuffering +15 ± 22 s). **M6 (selectors) has a real cost** — claim 9 |
| 4 | Speedup **decreases** from k=3 to k=5 for both zero-search drafters, and k=5 rebuffering is worse — the k axis peaks at k=3. | Table 1; NEEDS_UPSTREAM #5 | 4-seed speedup: repeat-last 1.49 (k3) → 1.46 (k5); hybrid 1.50 → 1.48. Δrebuffering: repeat-last +5 ± 23 (k3) → +15 ± 22 s (k5). q rises 4 pp (38 → 43 %) but `c_verify` grows 91 → 112 ms | 4 configs × 4 seeds ([[DRAFTER_ABLATION]] §9.13) | 2 k points; k=8 (the "$6^k$ wall" regime) untested — trend + cost model say it loses |
| 5 | The q→speedup **cost model survives a drafter swap and a serve-gate**, but its dominant term shifts: 2-bucket (verify/serve) at low fallback share → 3-bucket (+fallback) once the drafter is aggressive → 4-bucket (+forced-serve) under a safe-mode gate. | SWEEP_SPEC §12.2–12.5 | 2-bucket predicts k3 within 0.8 %, under-predicts k5 by 5–6 %; 3-bucket predicts all 6 drafter runs within 0.4 %, and the conservative-gate run within 0.3 % | 6 drafter runs + 4 gate runs, 1 seed each; model fit per run | Break-even q is an instance constant (old 14.63 %, new ~11 %) — the *form* is stable, the *parameters* are not |
| 6 | The drafter's rebuffering rise is caused by a **small number of queue entries that execute after the buffer drains** (the drafter cannot see the future drain), not by the queue serves being generally unsafe. | Fig. 5(right); DRAFTER_ABLATION §S.6 | queue-serve rebuffer-event incidence ≤ 0.97× the mpc control (incidence gate passes); ≥ 20 s buffer band (76 % of all queue serves) contributes 0 s; `< 5 s` band carries ~all of it | 4700 decisions, per-band, 1 seed | the "few entries" identity is seed-dependent (claim 8) — the *mechanism* is not |
| 7 | **A serve-time buffer gate does not work** — investigated as a case study (28 runs), it is inert once measured without the seed-once confound. Its one seed-1 "4/4" configuration was a coincidental trip/cascade alignment. The useful output of the investigation is claim 8. | Fig. 5, Fig. 6; [[DRAFTER_ABLATION]] §9.6–9.11; [[CHANGE_REQUEST_SERVE_TIME_GATE]] (withdrawn) | `fallback` (LLM handoff in a drained buffer) backfires; `conservative` (deterministic step-down) passed 4/4 at seed 1 (rebuf 18.5→1.6 s) but seeds {2,3,4} = help 1 / no-op 2 / hurt 1; per-episode reseed → gate changes 1 decision, 0 s effect | 22 seed-1 gate runs + 6 seed runs + a reseed A/B; controlled (trigger fixed, response varied) | this is a negative result presented as a methodology case study, not a proposed mechanism; the change request is **withdrawn** |
| 8 | **`test.py` seeds the evaluation RNG once for all 100 traces — a methodology defect this project found, verified, and worked around.** Consequences: (a) any mid-run intervention shifts the shared sampling stream and contaminates every later trace; (b) outlier-dominated metrics (rebuffering, QoE) are a per-run seed lottery. **Structural metrics (speedup, `q`, agreement) are unaffected — confirmed across 4 seeds.** The opt-in fix `abr_spec/reseed_per_episode.py` re-seeds per episode; the 1-line upstream fix is [[NEEDS_UPSTREAM]] #6. | Fig. 6; [[TRAJECTORY_DIVERGENCE]]; [[RNG_CONTAMINATION_AUDIT]]; [[DRAFTER_ABLATION]] §9.11–9.13 | 3 gate trips → 27 % sustained downstream action-mismatch (45/100 traces), LLM-call count Δ ≤ 10 → the cost is not latency. Un-contaminated re-measure: the serve gate changes **1 decision**, moves rebuffering **0 s**. Drafter ablation self-check: `q` 37.8→38.3 %, speedup 1.42→1.53× **unchanged**; ΔQoE sign flips −1.5→+0.2 % (outlier trace 74 = 88–92 % of the total) | seed-1 A/B for the gate; 4-seed sweep + a per-episode-reseed A/B for the drafter self-check; decision-level mismatch computed exhaustively over 4,700 decisions | `safe-mode`'s divergence not precisely measurable (115 forced serves bypass `decision_trace`); this is a defect report, not a large-sample study — its value is that it explains and bounds the noise, and confirms the headline survives it |
| 9 | **Adding the Temporal + Token selectors on top of the drafter (M6) doubles the speedup to ~2.0× but at a genuine QoE cost** — the one place in the ablation where the cost is 4-seed-significant. | Table 1; [[DRAFTER_ABLATION]] §9.13 | M6 speedup **2.03 ± 0.10×**, q 37.8 ± 0.2 %; ΔQoE **−3.0 ± 1.9 %** (negative at all 4 seeds), Δrebuffering **+38 ± 29 s** | repeat-last k3 + `event-aware` / `intra-timestep` selectors, 4 seeds | seed-2 is an outlier (rebuffering 96 s; traces 36/13/74 = 88 s) — reported, not trimmed; the QoE sign is consistent even so |

## 2. Table 1 — Main Ablation (LaTeX, booktabs)

```latex
\begin{table}[t]
  \centering
  \caption{ABR speculative-inference ablation. fcc-test 100 traces, video1,
  sample verification, one RTX 3090 (driver 570). Drafter rows are
  mean$\pm$std over \textbf{4 seeds} ($\{1,2,3,4\}$); $\Delta$QoE and
  $\Delta$Rebuf.\ are vs.\ the same-seed A1. $q$ = LLM-call-reduction share;
  "1-step" = fraction of decisions where the drafter's first action equals the
  LLM's. Speedup is a within-instance latency ratio; its std is dominated by
  cross-session drift, $q$ is not (\S9.13). The parameter-sweep row is from an
  earlier instance (\S9.4), seed 1.}
  \label{tab:abr-ablation}
  \begin{tabular}{llrrrrr}
    \toprule
    Stage & Config & $\Delta$QoE\% & Speedup & $q$ & 1-step & $\Delta$Rebuf.\ (s) \\
    \midrule
    baseline    & A1 (no speculation), rebuf.\ $16.9\pm11.6$ s & --- & 1.00$\times$ & --- & --- & --- \\
    \midrule
    parameters  & best sweep run (\S8), seed 1        & $+0.8$ & 0.93$\times$ & 10\% & 13\% & $+1.1$ \\
    \midrule
    drafter     & mpc, $k{=}3$ (seed 1 / reseed)      & $+0.8$ / $-1.5$ & $\sim$1.0$\times$ & 7\% & 16\% & $+1$ / $+32$ \\
                & repeat-last, $k{=}3$                & $+0.4\pm2.1$ & $\mathbf{1.49\pm0.08\times}$ & $38.2\pm0.3$\% & $\mathbf{88.5\pm0.6}$\% & $+5\pm23$ \\
                & hybrid, $k{=}3$                     & $-0.5\pm2.5$ & $1.50\pm0.08\times$ & $37.1\pm0.3$\% & $83.0\pm0.9$\% & $+6\pm12$ \\
                & repeat-last, $k{=}5$                & $-0.8\pm2.3$ & $1.46\pm0.12\times$ & $42.6\pm0.6$\% & $87.3\pm0.4$\% & $+15\pm22$ \\
                & hybrid, $k{=}5$                     & $+0.5\pm3.4$ & $1.48\pm0.11\times$ & $42.0\pm0.7$\% & $82.6\pm1.2$\% & $-5\pm22$ \\
                & repeat-last $k{=}3$ + selectors (M6) & $\mathbf{-3.0\pm1.9}$ & $\mathbf{2.03\pm0.10\times}$ & $37.8\pm0.2$\% & $86.1\pm0.5$\% & $\mathbf{+38\pm29}$ \\
    \bottomrule
  \end{tabular}
\end{table}
```

> **Superseded (seed-1 point values, [[DRAFTER_ABLATION]] §2 as first written).**
> repeat-last k3 QoE 0.9342 / $\Delta$QoE $-1.5$\% / rebuf 23.8 s; hybrid k3 0.9319
> / $-1.8$\% / 26.9 s; M6 0.9119 / $-3.9$\% / 30.4 s. These are one draw from the
> distributions above; the 4-seed rows replace them. Kept here for provenance.

## 3. Table 2 — Serve gate: response mode × floor, and seed robustness (LaTeX, booktabs)

```latex
\begin{table}[t]
  \centering
  \caption{Serve-time buffer gate case study --- \emph{why the seed-1 result was
  a mirage}. (a) Hybrid $k{=}5$, seed 1: rebuffering (s) by response mode and
  floor; \texttt{conservative}/floor 5\,s looks like a fix. (b) The same config
  re-measured: paired across seeds, and once with the eval RNG re-seeded per
  episode (\texttt{reseed}). $\Delta$ = gate $-$ control.}
  \label{tab:serve-gate}
  \begin{tabular}{lrrrr}
    \toprule
    \multicolumn{5}{l}{\textit{(a) rebuffering (s), hybrid $k{=}5$, seed 1}} \\
    \midrule
    Mode & floor 0 & floor 3 & floor 5 & floor 8 \\
    \midrule
    (control)      & 18.5 & 18.5 & 18.5 & 18.5 \\
    fallback       & ---  & ---  & 7.0  & ---  \\
    conservative   & ---  & 18.5 & \textbf{1.6} & 22.4 \\
    safe-mode      & ---  & ---  & 39.8 & 41.1 \\
    \midrule
    \multicolumn{5}{l}{\textit{(b) conservative + floor 5\,s, re-measured}} \\
    \midrule
    seeding & control rebuf & gated rebuf & $\Delta$ & note \\
    \midrule
    seed 1        & 18.51 & \textbf{1.64} & $-16.87$ & the mirage \\
    seed 2        & 4.24  & 4.24  & $0.00$ & no trip \\
    seed 3        & 25.59 & 29.87 & $+4.28$ & RNG shift $\to$ new cascade \\
    seed 4        & 0.49  & 0.49  & $0.00$ & no trip \\
    reseed/ep (s1)& 18.40 & 18.40 & $0.00$ & 1 trip, 1 decision changed \\
    \bottomrule
  \end{tabular}
\end{table}
```

Verdict: the gate is inert; [[CHANGE_REQUEST_SERVE_TIME_GATE]] is **withdrawn**.
The table earns its place as the evidence for claim 8 (the seed-once RNG defect),
not as a proposed mechanism.

## 4. Reproducibility Block (drop into Experimental Setup)

> **Model.** Llama-2-7B (base weights, fp16) + the official NetLLM ABR LoRA
> adapter ($r{=}128$, $\alpha{=}32$, targets `q_proj`/`v_proj`) and a 12-module
> non-PLM stack (state encoder, embedding heads, `action_head` $(6,4096)$).
> Checkpoint strict-load verified (`abr_spec/validate_ckpt.py` $\to$ ABR-compatible)
> and hash-pinned ([[ASSETS]] §3) before every session.
>
> **Data.** fcc-test, 100 traces, video1, `--fixed-order` (deterministic trace
> order, seed-independent). 47 chunks/trace $\to$ 4,700 decisions/run.
>
> **Decoding.** `--speculative-verification-mode sample` (`rl_policy._sample`
> $\to$ `random.choices`); tolerances buffer 1.0\,s / state 0.25 / return 0.01
> (SWEEP_SPEC §5 shows they do not help). Drafter is one of: `mpc` (Robust-MPC
> $6^k$ brute force, the NetLLM baseline), `repeat-last` (repeat the last executed
> bitrate $k$ times, zero CPU), `hybrid` (mpc when buffer $<5$\,s or throughput
> CV $\ge 0.30$, else repeat-last). Injected by monkeypatch
> (`abr_spec/drafter_select.py`) — `run_plm.py` is not modified.
>
> **Serve gate.** `abr_spec/serve_gate.py`, monkeypatch on
> `rl_policy.validate_speculative_observation`. `--serve-buffer-floor N` refuses a
> queued action when the buffer $< N$\,s; `--serve-gate-mode` $\in$
> \{`fallback` (one LLM call), `conservative` (serve $\max(0,\text{last}{-}1)$
> once, no LLM), `safe-mode` (force that for every low-buffer decision)\}.
>
> **Hardware / latency.** One RTX 3090 (24\,GB), driver 570.172.08, fp16. Absolute
> latency is not comparable across instances (BASELINE6/SWEEP ran on driver
> 595.58.03; cross-session drift up to ~10\% for identical behaviour) — every
> speedup is a **within-instance** ratio vs a same-instance A1
> (\texttt{a1\_all\_off}, 80.627\,ms).
>
> **Seeding.** Seeds $\{1,2,3,4\}$; the drafter ablation is reported as 4-seed
> mean$\pm$std ([[DRAFTER_ABLATION]] §9.13). NB `plm_special/test.py` seeds
> `random`/`numpy`/`torch` **once, before the 100-trace loop**; `clear_dq()` does
> not re-seed, so within one run the sample stream is shared across traces and
> any mid-run intervention that changes the RNG-draw count contaminates later
> traces (claim 8; [[TRAJECTORY_DIVERGENCE]]). The opt-in diagnostic
> `abr_spec/reseed_per_episode.py` (`--probe reseed_per_episode`) re-seeds with
> `seed + trace\_idx` at each episode boundary to make an A/B a paired
> within-trace comparison; it is not wired into the default pipeline (the
> determinism battery depends on the current behaviour) — [[NEEDS_UPSTREAM]] #6
> is the 1-line upstream fix.
>
> **Freeze.** drafter ablation + seed sweep: `0d137ce` exec path (`run_wrapped.py`
> $+34$ additive argparse lines); serve gate v1 `79095d4`, v2 `83704a6`. Every
> run records its commit in `manifest_phase.json`.
>
> **Determinism.** Each drafter, run twice at seed 1 (trace-num 5), is
> behaviour-bit-identical (`decisions.jsonl` SHA match with timing stripped);
> latency drifts +1.2–1.9 %.
>
> **Soyun-authored tooling (candidate artifacts).** `abr_spec/`:
> `drafter_select.py` (drafter monkeypatch), `serve_gate.py` (serve-gate
> monkeypatch), `decision_trace.py` (per-decision JSONL tracer),
> `reseed_per_episode.py` (the RNG-contamination diagnostic),
> `trajectory_divergence.py` + `run_wrapped.py` (provenance-stamped runner),
> `build_*_report.py`. None touch `run_plm.py` / `rl_policy.py` / `test.py`.

## 5. Gaps — priority, expected GPU cost

| # | Gap | Priority | Cost | Note |
|---|---|---|---|---|
| ~~G1~~ | **DONE 2026-09-10 ([[DRAFTER_ABLATION]] §9.13).** m2/m3/m4/m5/M6 run at seeds 2–4; ablation reported as 4-seed mean±std. Headline re-confirmed, cost part collapses to noise except M6. | — | done (`drafter_seed_sweep_20260910`, ~65 min) | Replaced "conditional success" with the claim-3b / claim-9 split |
| ~~G2~~ | **DONE ([[DRAFTER_ABLATION]] §9.11–9.12, [[RNG_CONTAMINATION_AUDIT]] §3).** Serve-gate A/B and the drafter anchors re-run with per-episode re-seed. Gate → 0 effect; drafter headline unchanged, ΔQoE sign flips. | — | done (`rng_audit_20260909`) | Confirms claim 8; the [[NEEDS_UPSTREAM]] #6 upstream fix remains open |
| G3 | **Draft-time drain-aware enqueue** (the general fix, if a rebuffering cost is later shown to be real). Skip enqueuing a queue entry whose `rollout.predicted_buffers` dips below a floor. Touches `mpc_draft.py` + `rl_policy.py`. | LOW (was MEDIUM — the 4-seed cost is not distinguishable from 0) | 4–8 runs ≈ 30–45 min + a change request | Would protect every drafter. Revisit only if a larger seed sample surfaces a real cost |
| G7 | **[[NEEDS_UPSTREAM]] #6 — re-seed the eval RNG per episode** in `test.py` (~1 line, eval-harness owner). Re-baseline the determinism battery in the same commit. | **MEDIUM** | not soyun's | Removes the confound for every future A/B, permanently. `abr_spec/reseed_per_episode.py` is the opt-in stand-in |
| G8 | **Larger seed sample** for the drafter cost (n=4 → n=8–10) if the paper needs to *bound* the QoE/rebuffering cost rather than say "not distinguishable from 0". | LOW | 4 config × 5 seed ≈ 100 min | Only if a reviewer presses on the cost |
| G4 | **k=8** for zero-search drafters (the "$6^k$ wall" regime). Blocked by `run_plm.py:298`. | LOW | 4 runs ≈ 20 min after a 1-line team change | Claim 4 + the cost model both predict it loses; only worth it if a reviewer asks |
| G5 | **Recent-token condition** (1 of BASELINE6's 6) still fails (fp16 all-NaN inside Llama). | LOW (not soyun's) | — | [[NEEDS_UPSTREAM]] #4 |
| G6 | **`c_recent_token` / M6 selector interaction with the gate** untested. | LOW | 2 runs ≈ 6 min | M6 (repeat-last + selectors) has the safest queue serves already (§4) |

## 6. Figures

`results/soyun/figures/` (300 dpi PNG + vector PDF, greyscale-safe, English
captions in `<name>.caption.txt`; binaries gitignored, `make_figures.py` +
`README.md` are the tracked record):
fig1 (6 conditions × QoE/speedup), fig2 (q vs speedup, sweep ceiling + drafter
points), fig3 (tolerance substitution), fig4 (drafter comparison + gate
before/after), fig5 (gate strength × mode tradeoff), fig6 (trajectory divergence
v1 vs v2).

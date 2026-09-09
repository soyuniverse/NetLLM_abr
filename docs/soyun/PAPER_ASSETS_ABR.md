# PAPER_ASSETS_ABR — Claims, Tables, Reproducibility, Gaps (2026-09-09)

**soyun / speculative inference for ABR (NetLLM fork), branch `soyun/spec-abr`.**
Companion to `results/soyun/figures/` (fig1–6 + captions), [[DRAFTER_ABLATION]],
[[SWEEP_SPEC]] §12, [[SERVE_GATE_DIAGNOSIS]], [[TRAJECTORY_DIVERGENCE]]. This is
the paper-writing entry point: what can be claimed, with what evidence, plus what
still can't.

**Instance / seed caveat up front.** All headline numbers are `--seed 1`,
`--fixed-order`, fcc-test 100 traces, video1, on one RTX 3090 (driver 570.172.08).
§9.9 shows **rebuffering is highly seed-sensitive** (hybrid k5: 0.49 / 4.24 /
18.5 / 25.6 s across seeds 1–4) because the eval RNG is seeded once for all 100
traces and rebuffering is dominated by 1–2 unlucky traces (claim 8). Speedup is a
within-instance ratio only (cross-session drift ~10 %, [[DRAFTER_ABLATION]] §9.4).

---

## 1. Claim → Evidence Mapping

| # | Claim | Fig / Table | Key numbers | Statistical basis | Limitations / counterarguments |
|---|---|---|---|---|---|
| 1 | The speculative parameter space (draft length k, verification mode, buffer/state tolerance) **cannot reach latency parity** — it is an exclusion result. | Fig. 2; SWEEP_SPEC §8 | 11 runs, all q < 10 %, speedup 0.90–0.93×; break-even needs q = 14.63 %, optimistic sum of every axis = 11.9 % | 11 runs, 1 seed, single instance; each axis' best effect measured, interactions assumed sub-additive | Interactions could be super-additive (SWEEP_SPEC §9 argues not: each axis effect ~1 pp, need 1.5× the requirement); k capped at 5 by `run_plm.py` (NEEDS_UPSTREAM #5) |
| 2 | Loosening the buffer tolerance **substitutes** failures rather than fixing them — direct evidence that the *drafter*, not the acceptance gate, is the bottleneck. | Fig. 3 | btol 1→8 s: buffer fallbacks 236→43, state fallbacks 32→191, total 268→234 (82 % substitution; 100 % between btol 4 and 8); q saturates at 6.64 % | 4 tolerance points, 1 seed; `return_mismatch_fallbacks` = 0 in all 12 runs | 4 points only; the substitution is shown for mpc; a different drafter shifts *which* row catches the entry (claim 5 note) |
| 3 | **Replacing the drafter with "repeat the last action" clears speedup 1.0× and 1.24×** — the lines the parameter space could not. Root cause: the LoRA policy's action autocorrelation. | Fig. 1, Fig. 4; Table 1 | mpc draft/LLM 1-step match 16.3 %; repeat-last **88.0 %**; accepted prefix 0.23 → **2.30 / 3**; q 7.4 % → 37.8 %; speedup **1.419×** (repeat-last k3) | 4700 decisions / 100 traces, 1 seed; controlled (only the drafter changes); m1a reproduced SWEEP_SPEC s0 to the digit (freeze verified) | Single seed (claim 8); QoE −1.5 % (not within the ±1 % target); the win is speed, at a QoE cost |
| 4 | Speedup **decreases** from k=3 to k=5 for both zero-search drafters — the k axis peaks at k=3. | Table 1; NEEDS_UPSTREAM #5 | repeat-last 1.419× (k3) → 1.306× (k5); hybrid 1.413× → 1.326×. q rises only 4 pp while `c_verify` grows 91→112 ms | 4 configs (2 drafters × 2 k), 1 seed | 2 k points only; k=8 (the "6^k wall" regime) untested — but the trend and the cost model both say it loses |
| 5 | The q→speedup **cost model survives a drafter swap and a serve-gate**, but its dominant term shifts: 2-bucket (verify/serve) at low fallback share → 3-bucket (+fallback) once the drafter is aggressive → 4-bucket (+forced-serve) under a safe-mode gate. | SWEEP_SPEC §12.2–12.5 | 2-bucket predicts k3 within 0.8 %, under-predicts k5 by 5–6 %; 3-bucket predicts all 6 drafter runs within 0.4 %, and the conservative-gate run within 0.3 % | 6 drafter runs + 4 gate runs, 1 seed each; model fit per run | Break-even q is an instance constant (old 14.63 %, new ~11 %) — the *form* is stable, the *parameters* are not |
| 6 | The drafter's rebuffering rise is caused by a **small number of queue entries that execute after the buffer drains** (the drafter cannot see the future drain), not by the queue serves being generally unsafe. | Fig. 5(right); DRAFTER_ABLATION §S.6 | queue-serve rebuffer-event incidence ≤ 0.97× the mpc control (incidence gate passes); ≥ 20 s buffer band (76 % of all queue serves) contributes 0 s; `< 5 s` band carries ~all of it | 4700 decisions, per-band, 1 seed | the "few entries" identity is seed-dependent (claim 8) — the *mechanism* is not |
| 7 | A serve-time buffer gate that hands the drained buffer to the **sampling LLM** (`fallback`) backfires; a **deterministic conservative serve** (`conservative`) is 4× better on the same trips — but only where the unprotected failure was a concentrated cascade. | Fig. 5, Fig. 6; DRAFTER_ABLATION §9.6–9.8 | same 3 trips: v1 fallback rebuf 7.0 s / QoE −1.3 %, v2 conservative **1.64 s / −0.05 %**; both hurt hybrid k3 (+31 s) and are inert on repeat k3/k5 | 22 gate runs (seed 1) + 6 seed runs; controlled (trigger fixed, response varied) | not a general fix; floor knife-edge (3 s no-op, 5 s helps, 8 s over-triggers); **not confirmed across seeds** (claim 8) |
| 8 | **The cost of any serve-time intervention is trajectory contamination, not the ~80 ms LLM latency**, because `test.py` seeds the eval RNG once for all 100 traces. 3 gate trips shift the RNG stream and produce a **27 % sustained downstream action-mismatch** for the fallback variant (45/100 traces); the conservative variant's shift is 4 % and re-converges (9/100 traces). This also makes the un-gated baseline a seed lottery. | Fig. 6; TRAJECTORY_DIVERGENCE; §9.9 | LLM-call count changes ≤ 10; per-intervention perturbation v1 ≈ 203 decisions, v2 ≈ 22; un-gated hybrid k5 rebuffering 0.49 / 4.24 / 18.5 / 25.6 s (seeds 1–4), std 10.2 | 4 seeds (paired ctrl/v1/v2), 1 instance; decision-level mismatch computed exhaustively over 4700 decisions | `safe-mode`'s divergence not precisely measurable (its 115 forced serves bypass `decision_trace` — jsonl 4585/4700 rows); the seed sweep is 4 seeds, not a large sample |

## 2. Table 1 — Main Ablation (LaTeX, booktabs)

```latex
\begin{table}[t]
  \centering
  \caption{ABR speculative-inference ablation. fcc-test 100 traces, video1,
  \texttt{--seed 1}, sample verification, one RTX 3090. Speedup is
  latency$_{\text{A1}}$/latency, measured within this session; the
  parameter-sweep rows are from an earlier instance and their speedup is a
  within-that-instance ratio (\S9.4). "1-step" = fraction of decisions where the
  drafter's first action equals the LLM's; "prefix" = mean accepted draft prefix
  length.}
  \label{tab:abr-ablation}
  \begin{tabular}{llrrrrrr}
    \toprule
    Stage & Config & QoE & $\Delta$QoE\% & Speedup & $q$ & 1-step & Rebuf.\ (s) \\
    \midrule
    baseline      & A1 (no speculation)          & 0.9487 & ---   & 1.00$\times$ & ---   & ---    & 6.39 \\
    \midrule
    parameters    & best sweep run (\S8)         & 0.9564 & $+0.8$ & 0.934$\times$ & 9.96\% & 12.8\% & 7.48 \\
    \midrule
    drafter       & mpc, $k{=}3$                 & 0.9564 & $+0.8$ & 0.974$\times$ & 7.4\%  & 16.3\% & 7.48 \\
                  & repeat-last, $k{=}3$         & 0.9342 & $-1.5$ & \textbf{1.419$\times$} & 37.8\% & \textbf{88.0\%} & 23.8 \\
                  & hybrid, $k{=}3$              & 0.9319 & $-1.8$ & 1.413$\times$ & 37.3\% & 83.2\% & 26.9 \\
                  & repeat-last $k{=}3$ + selectors (M6) & 0.9119 & $-3.9$ & \textbf{2.102$\times$} & 37.8\% & 86.2\% & 30.4 \\
    \midrule
    serve gate    & hybrid $k{=}5$, no gate      & 0.9300 & $-2.0$ & 1.326$\times$ & 41.9\% & 82.7\% & 18.5 \\
    (seed 1)      & \quad + conservative, floor 5\,s & \textbf{0.9482} & $\mathbf{-0.1}$ & 1.499$\times$ & 41.8\% & --- & \textbf{1.64} \\
    \bottomrule
  \end{tabular}
\end{table}
```

## 3. Table 2 — Serve gate: response mode × floor, and seed robustness (LaTeX, booktabs)

```latex
\begin{table}[t]
  \centering
  \caption{(a) Serve-time buffer gate on hybrid $k{=}5$, \texttt{--seed 1}:
  rebuffering (s) by response mode and buffer floor. (b) The seed-1 4/4 config
  (\texttt{conservative}, floor 5\,s) re-run at seeds 2--4, paired against the
  un-gated control. $\Delta$ = gate $-$ control.}
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
    \multicolumn{5}{l}{\textit{(b) conservative + floor 5\,s across seeds}} \\
    \midrule
    seed & control rebuf & gated rebuf & $\Delta$ & criteria met \\
    \midrule
    1 & 18.51 & \textbf{1.64} & $-16.87$ & 4/4 \\
    2 & 4.24  & 4.24  & $0.00$ (no trip) & 4/4 \\
    3 & 25.59 & 29.87 & $+4.28$ & 2/4 \\
    4 & 0.49  & 0.49  & $0.00$ (no trip) & 4/4 \\
    \bottomrule
  \end{tabular}
\end{table}
```

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
> **Seeding.** `--seed 1` throughout, per AGENTS.md. NB `plm_special/test.py:42`
> seeds `random`/`numpy`/`torch` **once, before the 100-trace loop**;
> `clear_dq()` does not re-seed. So the sample stream is shared across traces and
> any mid-run intervention that changes the RNG-draw count contaminates later
> traces (Table 1 seed rows; [[TRAJECTORY_DIVERGENCE]]).
>
> **Freeze.** drafter ablation: commit `0d137ce`; serve gate v1: `79095d4`;
> serve gate v2: `83704a6`. Every run records its commit in
> `manifest_phase.json`. Execution-path files unchanged within each campaign.
>
> **Determinism.** Each drafter, run twice at seed 1 (trace-num 5), is
> behaviour-bit-identical (`decisions.jsonl` SHA match with timing stripped);
> latency drifts +1.2–1.9 %.

## 5. Gaps — priority, expected GPU cost

| # | Gap | Priority | Cost | Note |
|---|---|---|---|---|
| G1 | **drafter ablation is seed-1 only.** m2/m3/m4/m5/M6 rebuffering & QoE need seed 2–4 to report mean±std, not a point. §9.9 shows the point is not representative. | **HIGH** | 5 config × 3 seed ≈ 75 min | Blocks the "conditional success" framing being a stable claim vs a seed draw |
| G2 | **Un-contaminated A/B.** Re-run the serve-gate A/Bs with per-episode re-seed (`abr_spec/reseed_per_episode.py`, opt-in) to get a paired within-trace comparison free of RNG-stream shift. | HIGH | 2–6 runs ≈ 15–30 min | The diagnostic exists; not yet wired into a campaign. Confirms/quantifies claim 8 cleanly |
| G3 | **Draft-time drain-aware enqueue** (the general fix for claim 6/7). Skip enqueuing a queue entry whose `rollout.predicted_buffers` dips below a floor. Touches `mpc_draft.py` + `rl_policy.py`. | MEDIUM | 4–8 runs ≈ 30–45 min + a change request | Would protect every drafter, not just hybrid k5. [[CHANGE_REQUEST_SERVE_TIME_GATE]] §7 |
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

# HANDOFF — read this file first

**soyun / speculative inference · branch `soyun/spec-abr` · last updated 2026-09-10**

If you are a new instance or a resumed session: **this file alone should restore
the context.** Everything referenced here is committed.

**TL;DR — the whole project in 3 lines** (senior-facing entry point:
[[SUBMISSION_SUMMARY]]):
1. **Deploy `--speculative-drafter repeat-last --speculative-draft-steps 3`, no serve gate** — ~1.5× fewer LLM calls (q ≈ 38 %, 4-seed σ < 0.3 pp), QoE/rebuffering cost not distinguishable from zero at 4 seeds. `hybrid` k3 is equivalent.
2. **M6** (drafter + `--temporal-selector event-aware --token-selector intra-timestep`) gets ~2.0× but costs −3.0 ± 1.9 % QoE — take it only if 2× matters more than 3 % QoE.
3. **Methodology finding:** `test.py` seeds the eval RNG once per 100-trace run, so rebuffering/QoE are a per-seed lottery (report as mean±std, ≥3 seeds); structural metrics (speedup, q) are unaffected. [[RNG_CONTAMINATION_AUDIT]], [[TEAM_ALERT_RNG_CONTAMINATION]].

**The drafter ablation is DONE (2026-09-08 run, 2026-09-10 4-seed confirmation).**
`repeat-last` / `hybrid` drafters clear speedup 1.0× and 1.24× — the lines the
parameter sweep could not reach. 4-seed: repeat-last k3 = **1.49 ± 0.08×** at
q **38.2 ± 0.3 %**, draft/LLM 1-step agreement **88.5 ± 0.6 %** (mpc ~1.0× / 16 %).
**No QoE or rebuffering cost distinguishable from zero at k=3** (§9.13 — the
earlier "conditional / rebuffering 2.9–5.8× A1" was a seed-1 artifact); **k=5 is
worse**; **M6 (drafter + selectors) = 2.03 ± 0.10× but a real −3.0 ± 1.9 % QoE
cost**. Full writeup [[DRAFTER_ABLATION]] §9.13, cost model [[SWEEP_SPEC]] §12.
Freeze `0d137ce`, results `drafter_ab_20260908/` + `drafter_seed_sweep_20260910/`.

**2026-09-09: serve-time safety gate investigated (§8–§9, `serve_gate_20260909/`,
22 runs, freeze `83704a6`).** Task 0 found all three §S.7 prescriptions are
doable from `abr_spec/` by monkeypatch — **no team file, no `speculative/`
edit** (`abr_spec/serve_gate.py`, same pattern as `--speculative-drafter`).
**Outcome: the serve-time gate does not work.** A seed-1 config passed all four
criteria (`v_hybrid_k5_f5_cons`, rebuffering 18.5 → 1.64 s) but seed {2,3,4} give
help 1 / inert 2 / hurt 1 (§9.9), and re-measured with per-episode RNG
re-seeding the gate changes **1 decision** and moves rebuffering by **0** (§9.11)
— the seed-1 win was a coincidental alignment between where the gate trips and
where that RNG stream's pathological cascade landed.

**The real finding — [[TRAJECTORY_DIVERGENCE]] / [[RNG_CONTAMINATION_AUDIT]].**
`test.py` seeds the eval RNG once for all 100 traces, so (a) any mid-run
intervention contaminates every later trace (3 gate trips → 27 % sustained
downstream action-mismatch, 45/100 traces) and (b) outlier-dominated metrics
(rebuffering, QoE) are a per-run seed lottery — even plain A1 rebuffers
6.4 / 15.2 / 12.7 / 33.3 s across seeds 1–4.

**2026-09-10: G1 seed sweep done (§9.13, `drafter_seed_sweep_20260910/`, 15 runs).**
The drafter ablation is now 4-seed mean±std. **Headline confirmed** (repeat-last
k3 speedup 1.49±0.08×, q 38.2±0.3 %, 1-step 88.5±0.6 % — σ tiny, RNG-independent).
**"Conditional success" retired:** the k=3 cost is not distinguishable from 0 at
4 seeds (ΔQoE +0.4±2.1 %, Δrebuffering +5±23 s vs same-seed A1). **k=5 is
strictly worse.** **Only M6 (drafter + Temporal/Token selectors) has a real
cost:** 2.03±0.10× speedup but ΔQoE −3.0±1.9 %. Deployment pick: repeat-last or
hybrid **k=3** for a QoE-neutral ~1.5×; M6 if 2× is worth ~3 % QoE.

Team-facing writeup of the RNG defect: [[TEAM_ALERT_RNG_CONTAMINATION]].
[[CHANGE_REQUEST_SERVE_TIME_GATE]] is **withdrawn**.
Still open: [[NEEDS_UPSTREAM]] #6 (1-line `test.py` reseed — eval-harness owner),
draft-time fix only if a larger seed sample later shows a real cost.
[[NEEDS_UPSTREAM]] #5 (k cap) low priority.

---

## 1. Where the work stands — five lines

1. **Checkpoint secured.** The official NetLLM ABR LoRA (r=128) is the correct,
   fork-compatible checkpoint; hashes pinned in [[ASSETS]] §0/§3, validated by
   `abr_spec/validate_ckpt.py` → *ABR 호환 확인*. The earlier "must retrain"
   conclusion was a stale *viewport* checkpoint, not a real incompatibility.
2. **GPU fp16 is a real failure mode, not a theory.** One instance's RTX 3090
   (driver 535.154.05) returned all-NaN for every cuda fp16 tensor while fp32
   worked. `abr_spec/gpu_fp16_diagnostic.py` reproduces it in seconds and is a
   **hard gate before any run** ([[PLUMBING_SMOKE]] §3, [[VASTAI_SETUP]] Step 1).
3. **BASELINE6** (README's 6 conditions × 100 traces): Temporal **1.750×**,
   Temporal+Token **1.845×**, All-three **1.649×**, Speculative **0.918×**.
   Recent-token **fails outright** (fp16 all-NaN inside Llama →
   [[NEEDS_UPSTREAM]] #4). The speculative loss is the longer verification
   context (+16.85 %/call), **not** the MPC rollout (0.26 % of latency).
4. **SWEEP_SPEC verdict: parameters cannot reach break-even.** Break-even needs a
   queue-serve share `q = 14.73 %`; the whole parameter space tops out at
   `q = 9.96 %` and 0.898×–0.934×. Loosening the buffer tolerance *substitutes*
   failures rather than fixing them (buffer fallbacks 236→43 while state
   fallbacks 32→191, total ~unchanged). BASELINE6's −3.13 % QoE turned out to be
   the **greedy** verification mode, not speculation (with `sample`: **+0.81 %**).
5. **Drafter replacement — RUN 2026-09-08 ([[DRAFTER_ABLATION]]).** `mpc` /
   `repeat-last` / `hybrid` behind `--speculative-drafter`. On a new instance
   (driver 570, own A1 = 80.627 ms): repeat-last k3 **1.419×** (q 37.8 %),
   hybrid k3 1.413×, k5 pair 1.31–1.33×, M6 (repeat-last + Temporal/Token
   selectors) **2.102×**. mpc still < 1.0×. The post-hoc `q ≈ 35 %` estimate
   held (measured 37.8 %). **Conditional success**: rebuffering rises to
   18–37 s (A1 6.4 s); the queue-serve safety metric's incidence gate passes
   but the total-rebuffer gate fails (DRAFTER_ABLATION §S). k=8 blocked by the
   read-only `run_plm.py:298` cap ([[NEEDS_UPSTREAM]] #5); ablation ran k∈{3,5}.

Why a different drafter should work, in one line: MPC's proposal matches the
LoRA policy's own next action **12.84 %** of the time; "repeat the last action"
matches **93.30 %** (the policy's action autocorrelation is 92.46 %), mean
accepted prefix 0.180 vs 1.457.

Reading order for detail: [[BASELINE6]] → [[SWEEP_SPEC]] → [[RECON_SPECULATIVE]].

---

## 2. Fixed experimental protocol — do not drift

### 2.1 Common arguments (identical in BASELINE6, SWEEP_SPEC and the ablation)

```bash
COMMON="--test --fp16 --seed 1 --plm-type llama --plm-size base --rank 128 \
  --plm-dir ../downloaded_plms/llama/base \
  --model-dir ../downloaded_plms/ft_plms/try_llama2_7b \
  --trace fcc-test --trace-num 100 --video video1 --fixed-order \
  --device cuda:0 --device-out cuda:0"
```

`--trace fcc-test --trace-num 100 --video video1 --fixed-order` pin the
evaluation set and its ordering; changing any of them invalidates every
cross-condition comparison made so far (AGENTS.md). `--model-dir` is
`downloaded_plms/ft_plms/` — **not** the README's `data/ft_plms/` ([[ASSETS]] §3).

### 2.2 `--speculative-verification-mode sample` is the default from now on

s0 (k=3, sample) scored QoE **0.95637 = A1 +0.81 %** at 0.926×; E (k=3, greedy)
scored 0.91904 = A1 −3.13 % at 0.918×. Decomposed: speculation contributes
**+0.00765**, the greedy argmax **−0.03733**. greedy truncates the action
distribution's tail and drifts to lower bitrates. `sample` is also `run_plm.py`'s
own default, and reproducibility is unaffected because sampling is seeded
(`--seed 1`; `rl_policy._sample` → `random.choices`, re-seeded per run by
`run_plm.set_random_seed` and `test.test_on_env`). Keep one greedy run per
campaign only for continuity with BASELINE6's E.

### 2.3 Tolerances stay at the defaults 1.0 / 0.25 / 0.01

SWEEP_SPEC §5: btol 1.0→8.0 moved buffer fallbacks 236→43 while state fallbacks
went 32→191 and the total only 268→234 — **82 % substitution, 100 % between btol
4 and 8** — with `q` saturating at 6.64 %. The queue entries were discarded
because the *drafted action* was wrong, so no threshold can help.
`return_mismatch_fallbacks` was **0 in all 12 runs**, so the return tolerance is
not a live axis either. Changing them also confounds any drafter comparison.

### 2.4 Latency is only ever a within-instance ratio

Absolute ms are not comparable across instances (different GPU/driver/clocks).
`run_wrapped.py` enforces this: it records the `nvidia-smi` string per phase,
stamps `instance_changed`, and refuses to compute a speedup unless the baseline
run's GPU string matches exactly. Always quote **speedup vs A1**, never raw ms.

Noise floor: A1 vs A2 (same config, 17 min apart) drifted **0.19 %**; the s2_k2
re-run (identical behaviour, 1 h 46 m apart) drifted **0.58 %**. So: within a
session treat <0.2 % as noise; across sessions treat <0.6 % as noise.

### 2.5 Write scope

`abr_spec/`, `results/soyun/`, `docs/soyun/`, and
`adaptive_bitrate_streaming/plm_special/speculative/` (opened by the team lead on
2026-09-02). Everything else — especially `plm_special/models/` and
`run_plm.py` — is **read-only**; hook `rl_policy` from `abr_spec/` via
monkeypatch instead (`decision_trace.py`, `drafter_select.py`, `nan_probe.py` are
the working examples). `.git/hooks/pre-commit` enforces this and is **not tracked
by git**, so run `bash abr_spec/hooks/install.sh` immediately after cloning.

---

## 3. Next actions, in order

### Actions 0–3 — DONE 2026-09-08 ([[DRAFTER_ABLATION]])

Instance bring-up, the 6-phase ablation, analysis + writeup, and M6 are all
complete. Freeze `0d137ce`. `m1a_mpc_k3_sample` reproduced `s0` exactly
(QoE 0.956366 / q 0.073617 / acceptance 0.079084). `run_wrapped.py` refused a
speedup against the old-instance A1, so a fresh `drafter_ab_20260908/a1_all_off`
(80.627 ms) is this campaign's reference; `d_temporal_token` is the selector-only
reference. Two frozen-path issues were found and fixed *before* the freeze
(DRAFTER_ABLATION §0): `decision_trace.py` did not instrument repeat-last/hybrid,
and k=8 is impossible without editing read-only `run_plm.py`.

### Action 4 — serve-gate investigation — DONE 2026-09-09 (§8–§9.11)

Prototyped from `abr_spec/` (monkeypatch, no team file). **Verdict: the gate is
inert under proper measurement — not recommended** ([[CHANGE_REQUEST_SERVE_TIME_GATE]]
§7). The valuable output is [[TRAJECTORY_DIVERGENCE]] and [[NEEDS_UPSTREAM]] #6.

### Action 5 — remaining, in priority order (GPU costs in [[PAPER_ASSETS_ABR]] §5)

1. **[[NEEDS_UPSTREAM]] #6 — re-seed the eval RNG per episode** (`test.py`, ~1 line,
   not soyun's; re-baseline the determinism battery in the same commit). Blocks a
   clean read of any serve-/draft-time A/B. `abr_spec/reseed_per_episode.py` is
   the opt-in stand-in.
2. ~~drafter ablation across seeds~~ **DONE 2026-09-10 (§9.13, G1).**
3. **Draft-time drain-aware enqueue** — now LOW: the 4-seed drafter cost is not
   distinguishable from 0, so there is no rebuffering problem to fix at k=3.
   Revisit only if [[PAPER_ASSETS_ABR]] G8 (n=8–10) surfaces a real cost.
4. **[[NEEDS_UPSTREAM]] #4** — `recent-timestep` fp16 NaN, not soyun's.
- **[[NEEDS_UPSTREAM]] #5** (k=8 cap) — LOW: speedup decreases k3→k5, k5 already worse.

### Scratchpad → committed file map (sessions 2026-09-08 … 09-10)

The session scratchpad (`/tmp/claude-0/.../scratchpad/`, ~0.6 MB, **not deleted**)
holds one-off drivers and logs that are superseded by committed files:

| scratchpad | superseded by (committed) |
|---|---|
| `run_ablation.sh`, `run_determinism.sh` | `abr_spec/run_drafter_ablation.sh`, `abr_spec/run_determinism_check.sh` |
| `run_batch3.sh`, `run_seeds.sh`, `run_v1_seeds.sh`, `run_reseed.sh` | phases folded into `abr_spec/run_serve_gate.sh` (batch 3) / documented in DRAFTER_ABLATION §9.9, §9.11 |
| `run_reseed_a1.sh` | `abr_spec/run_rng_audit.sh` (a1/m1a/m2 reseed A/B, §9.12 / [[RNG_CONTAMINATION_AUDIT]] §3) |
| `serve_gate_v2.py`, `serve_gate_v2_notes.md`, `fig5_snippet.py`, `gate_proto_test.py`, `patchtest*.py` | `abr_spec/serve_gate.py` (v2), `abr_spec/make_figures.py` (fig5/6) |
| `*.log` (ablation/determinism/serve_gate/seeds/reseed) | `results/soyun/*/logs/*.log` (gitignored) + the committed `manifest.json` / `summary.json` |
| `synth.jsonl`, `qs_test/` | throwaway test fixtures for `queue_safety.py` |
| `session5_plan.md`, `sweep_out.txt` | working notes for the 09-10 session; the report is committed at `drafter_seed_sweep_20260910/seed_sweep_report.md` |
| `fig_backup/` | literal copy of the pre-09-10 seed-1 fig1/fig4 renders, taken before regeneration; the tracked equivalent is `figures/archive/*_seed1.*` (regenerated by `make_figures.py`) |

New committed tooling (09-09/09-10): `abr_spec/reseed_per_episode.py`,
`abr_spec/trajectory_divergence.py`, `abr_spec/run_rng_audit.sh`,
`abr_spec/run_drafter_seed_sweep.sh`, `abr_spec/build_seed_sweep_report.py`.
New docs (09-10): `docs/soyun/SUBMISSION_SUMMARY.md` (senior-facing entry point),
`docs/soyun/RNG_CONTAMINATION_AUDIT.md`, `docs/soyun/TEAM_ALERT_RNG_CONTAMINATION.md`.
fig1/fig4 regenerated 4-seed; seed-1 versions in `figures/archive/`.

### Not planned unless asked

Cross-parameter runs (SWEEP_SPEC §9: unnecessary, the optimistic sum of every
axis still misses break-even) · repeating s0/A1 across seeds to measure sampling
variance (only needed if a conclusion ever hinges on it) · re-running s3_k4 to
settle its −5.9 % latency outlier (conclusions rest on `q`, a count, not on
timing).

---

## 4. What exists in the repo

| Path | What |
|---|---|
| `abr_spec/run_wrapped.py` | runs `run_plm.py` in-process with redirected output roots; flags `--decision-trace`, `--probe`, `--baseline-phase`, `--speculative-drafter`, `--speculative-hybrid-*`; cross-instance GPU guard; writes `manifest.json` / `summary.json` |
| `abr_spec/decision_trace.py` | one JSON line per ABR decision (monkeypatch; outside the CUDA-synced window). Patches `BaseDraftGenerator` since `0d137ce` so repeat-last/hybrid are instrumented too; records `drafter_class` + hybrid `draft_route` |
| `abr_spec/drafter_select.py` | redirects `run_plm.py`'s single drafter construction site without editing it; `mpc` installs no patch |
| `abr_spec/analyze_decisions.py` | post-hoc rates, buffer/CV cross-tabs, latency attribution |
| `abr_spec/breakeven.py` | required `q` for parity / 1.24×, drafter what-if scenarios; empty-verify / no-serve guarded since `0d137ce` |
| `abr_spec/queue_safety.py` | queue-serve window rebuffering — DRAFTER_ABLATION's safety gate (A direct / B lagged / C incidence × buffer band) |
| `abr_spec/build_sweep_report.py` | the parameter-sweep table (s0..s8 phase names only) |
| `abr_spec/build_drafter_ablation_report.py` | the drafter-ablation table (m-phase names; speedup vs the run's own a1_all_off) |
| `abr_spec/make_figures.py` | the four DRAFTER_ABLATION paper figures (PNG 300 dpi + PDF, gitignored; captions in `results/soyun/figures/README.md`) |
| `abr_spec/derive_decision_summary.py` | distils gitignored `decisions.jsonl` into tracked `results/soyun/derived/` |
| `abr_spec/nan_probe.py` | locates the decision where a PLM forward goes non-finite |
| `abr_spec/validate_ckpt.py`, `gpu_fp16_diagnostic.py` | the two pre-flight gates |
| `abr_spec/run_baseline6.sh`, `run_sweep_spec.sh`, `run_drafter_ablation.sh`, `run_determinism_check.sh` | the campaigns + the Task 0.2 determinism gate |
| `abr_spec/tests/test_drafters.py` | tests incl. a 60-case tolerance-0 regression battery vs the frozen pre-refactor generator (full suite → **40 passed**) |
| `results/soyun/derived/` | **the surviving record of every `decisions.jsonl`** — 65.9 MB of raw traces distilled to 107 KB, tracked. Raw `.jsonl` died with the old instance. |

Run `CUDA_VISIBLE_DEVICES="" .venv/bin/python -m pytest \
adaptive_bitrate_streaming/tests/test_mpc_draft.py \
adaptive_bitrate_streaming/tests/test_speculative_acceptance.py \
abr_spec/tests/test_drafters.py -q` → **40 passed**, no GPU needed.

---

## 5. Open items — [[NEEDS_UPSTREAM]]

| # | Item | Status |
|---|---|---|
| 1+2 | Official checkpoint "incompatible" | **RESOLVED — not a bug.** Stale viewport zip on the old instance. Cosmetic note left upstream: `prepare_models.checkpoint_ready()` skips the download on filename presence alone, with no rank/shape check, so a stale dir wins silently. |
| 3 | `trainer.py:37-42` — AMP `GradScaler` armed only under `--nbs-v19`, so plain `--fp16 --adapt` has no loss scaling | Open, low priority. Only matters if we ever retrain; we do not need to. |
| **4** | **`--token-selector recent-timestep` makes Llama fp16 emit an all-NaN hidden state** | **Open, blocking 1 of the 6 README conditions.** Deterministic: PLM call 2527/4700, trace 53 chunk 36, `[1,47,4096]` all NaN. Inputs are benign (fp32 absmax 5.179, fp16 finite, attention mask dense 47/47) and preceding hidden absmax is 50–70, far under fp16's 65504 — the NaN is produced *inside* the frozen Llama forward. Conditions B (26.6 tokens) and D (19.5 tokens) complete all 4,700 decisions on the same build/GPU/seed. Owner: `plm_special/models/selectors.py` / `selection_layout.py`. **Not soyun's to fix** — escalate. Repro command and full probe output in [[NEEDS_UPSTREAM]] #4 and `results/soyun/baseline6_20260902/c_recent_token_nanprobe/nan_probe.json`. |

Also worth raising with the team lead: `run_plm.py` builds the drafter at a
single hard-coded site (`run_plm.py:435-439`), which is why the drafter choice
has to be injected by monkeypatch. A `--speculative-drafter` flag upstream would
remove that indirection.

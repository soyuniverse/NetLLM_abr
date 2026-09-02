# HANDOFF — read this file first

**soyun / speculative inference · branch `soyun/spec-abr` · last updated 2026-09-02**

If you are a new instance or a resumed session: **this file alone should restore
the context.** Everything referenced here is committed. The previous instance was
released on 2026-09-02 after the parameter sweep; the drafter ablation is written,
dry-run verified, and **not yet executed** — that is the next job.

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
5. **Drafter replacement is implemented, unit-tested, and unrun.** `mpc` /
   `repeat-last` / `hybrid` behind `--speculative-drafter` (commit `3964752`,
   40 tests pass). Post-hoc estimate for repeat-last: `q ≈ 35 %` → **~1.31×**.
   `abr_spec/run_drafter_ablation.sh` is dry-run verified. **Run it.**

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

### Action 0 — bring up the instance (~25 min, mostly download)

Follow [[VASTAI_SETUP]] end to end. It is ordered so the fp16 check happens
**before** the 13 GB download, and it lists the hosts to avoid.

### Action 1 — run the drafter ablation (~21.5 min GPU, ~$0.08) ← **the job**

Execution path is frozen at commit `3964752`; do not edit
`plm_special/speculative/`, `run_wrapped.py`, `decision_trace.py` or
`drafter_select.py` until this finishes (SWEEP_SPEC §2 shows what a mid-run code
change costs in audit work).

```bash
cd /root/NetLLM_abr
bash abr_spec/run_drafter_ablation.sh --dry-run      # sanity: "0 uncommitted change(s)"
tmux new -s drafterab -d
tmux send-keys -t drafterab 'bash abr_spec/run_drafter_ablation.sh' C-m
```

Six runs: `m1a_mpc_k3_sample` (control, must reproduce s0 exactly) ·
`m1b_mpc_k3_greedy` · `m2_repeat_k3` · `m3_hybrid_k3` · `m4_repeat_k5` ·
`m5_hybrid_k5`. Resumable (`result.json` status ok ⇒ skipped), continues past a
failure, `--decision-trace` on every run.

**First thing to check when it finishes:** `m1a_mpc_k3_sample` must land on
s0's QoE **0.95637**, `q` **7.36 %**, acceptance **7.91 %**. Anything else means
the freeze was broken or the instance differs — investigate before believing M2–M5.

### Action 2 — analyse and write it up (~20 min, CPU only)

```bash
python abr_spec/build_sweep_report.py \
  --sweep-dir results/soyun/drafter_ab_<date> \
  --baseline-dir results/soyun/baseline6_20260902 \
  --out-dir results/soyun/drafter_ab_<date>/analysis
python abr_spec/derive_decision_summary.py            # preserve the new jsonl
for p in m1a_mpc_k3_sample m2_repeat_k3 m3_hybrid_k3 m4_repeat_k5 m5_hybrid_k5; do
  python abr_spec/analyze_decisions.py \
    results/soyun/drafter_ab_<date>/$p/decisions.jsonl \
    --out-dir results/soyun/drafter_ab_<date>/analysis --label $p
  python abr_spec/breakeven.py \
    results/soyun/drafter_ab_<date>/$p/decisions.jsonl \
    --baseline-latency-ms 50.329 \
    --out-dir results/soyun/drafter_ab_<date>/analysis --label $p
done
```
Write `docs/soyun/DRAFTER_AB.md` against the same yardsticks: A1 = 1.000×,
break-even `q` 14.73 %, 1.24× `q` 31.51 %, and the QoE decomposition
`QoE = bitrate − 4.3·rebuffer − smoothness`. Also report, from
`decisions.jsonl`, what fraction of **hybrid**'s decisions actually paid for an
MPC rollout (`mpc_rollout_cpu_ms` non-null) — that is the whole point of M3/M5.

### Action 3 — M6: best drafter + selectors (~2 min GPU)

Only once M2–M5 name a winner. Suggested rule: **highest speedup among settings
whose QoE is within 1 % of A1** (0.94872) — confirm with soyun before applying.

```bash
BEST_DRAFTER=repeat-last BEST_K=5 RUNS="m6_best_plus_selectors" \
  bash abr_spec/run_drafter_ablation.sh
```
Compare against BASELINE6's F (1.649×) and D (1.845×): the question is whether a
working drafter adds anything **on top of** the selectors, or whether the
selectors already took the available win.

### Action 4 — escalate the open upstream items (no GPU)

See §5. #4 blocks one of the six README conditions and is not soyun's to fix.

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
| `abr_spec/decision_trace.py` | one JSON line per ABR decision (monkeypatch; record assembly is outside the CUDA-synced timing window) |
| `abr_spec/drafter_select.py` | redirects `run_plm.py`'s single drafter construction site without editing it; `mpc` installs no patch |
| `abr_spec/analyze_decisions.py` | post-hoc rates, buffer/CV cross-tabs, latency attribution |
| `abr_spec/breakeven.py` | required `q` for parity / 1.24×, drafter what-if scenarios |
| `abr_spec/build_sweep_report.py` | the campaign table (CSV + markdown) |
| `abr_spec/derive_decision_summary.py` | distils gitignored `decisions.jsonl` into tracked `results/soyun/derived/` |
| `abr_spec/nan_probe.py` | locates the decision where a PLM forward goes non-finite |
| `abr_spec/validate_ckpt.py`, `gpu_fp16_diagnostic.py` | the two pre-flight gates |
| `abr_spec/run_baseline6.sh`, `run_sweep_spec.sh`, `run_drafter_ablation.sh` | the three campaigns |
| `abr_spec/tests/test_drafters.py` | 29 tests incl. a 60-case tolerance-0 regression battery vs the frozen pre-refactor generator |
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

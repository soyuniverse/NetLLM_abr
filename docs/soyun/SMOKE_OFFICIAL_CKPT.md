# SMOKE — official ABR checkpoint on the new instance (speculative inference)

**Date:** 2026-09-01 · **Author:** soyun · **Branch:** `soyun/spec-abr`
**Verdict: 통과 (PASS).** Both smoke conditions completed with no hard error and
condition (b)'s speculative counters are all non-zero.

Related: [[HANDOFF]] · [[CHECKPOINT_RECOVERY]] · [[RECON_SPECULATIVE]] ·
[[PLUMBING_SMOKE]] · `results/soyun/smoke_spec_a_20260901/` ·
`results/soyun/smoke_spec_b_20260901/`

---

## 0. Hygiene check

| item | result |
|---|---|
| `git status` clean | **now clean.** `NOTICE` (repo-root) was deleted in the working tree during the manual Llama-2 cleanup — the repo's own `NOTICE` had been *moved* into `downloaded_plms/llama/base/NOTICE` (byte-identical to `HEAD:NOTICE`). Restored with `git checkout -- NOTICE`; the stray copy under `downloaded_plms/` is gitignored and left as-is. |
| large untracked files | none. |
| `README.md` = repo original | **yes**, byte-identical to `HEAD:README.md` (Korean "NetLLM ABR 추론 가속" fork readme, 428 lines). Not overwritten by a Llama README. |
| `git ls-files` > 128 KB | exactly one: `adaptive_bitrate_streaming/artifacts/exp_pools/exp_pool.pkl` (4.78 MB). This is an upstream-committed asset (README lists the ABR experience pool as bundled), **not** debris from the Llama accident — left untouched. |
| `downloaded_plms/llama/base/` complete | **yes** — `config.json` (`meta-llama/Llama-2-7b-hf`, fp16, 32 layers, hidden 4096), `model-00001-of-00002.safetensors` (9,976,578,928 B) + `model-00002-of-00002.safetensors` (3,500,297,344 B), `model.safetensors.index.json` (323 weight keys, `total_size` 13,476,839,424), tokenizer set (`tokenizer.json`, `tokenizer.model`, `tokenizer_config.json`, `special_tokens_map.json`), plus `generation_config.json`, `LICENSE.txt`, and a harmless extra `pytorch_model.bin.index.json`. Shard byte-sizes exceed `index.total_size` by 36,848 B (safetensors headers) → both shards fully downloaded, not truncated. |

All fixes stayed inside `abr_spec/` / `results/soyun/` / `docs/soyun/` /
`downloaded_plms/` (plus the one-file `git checkout` that *reverts* an accidental
deletion to its committed state — no upstream content changed).

---

## 1. Asset confirmation

| check | result |
|---|---|
| `abr_spec/gpu_fp16_diagnostic.py` | **PASS.** GPU `NVIDIA GeForce RTX 3090`, driver **595.58.03**, cap (8,6), torch 2.2.0 / cu12.1. `fp16` & `bf16` cpu→cuda finite + roundtrip-match **True**; fp16 matmul finite **True**; fp32→fp16 cast on cuda finite **True**; Llama-2-7b input-embedding weights finite on **both** CPU and CUDA. (Old instance: all of these were NaN under driver 535.154.05 — infra defect, now gone.) |
| official ABR checkpoint | re-fetched via `python scripts/prepare_models.py --skip-base-model` (gdown `17UyXJ9…`, 288 MB zip). SHA-256 of the 3 files matches the 2026-09-01 CPU validation exactly (`adapter_model.bin` `f0f6f5db…`, `modules_except_plm.bin` `a66930dd…`, `adapter_config.json` `9b602d0d…`). Relocated to `downloaded_plms/ft_plms/try_llama2_7b/` (soyun-writable, gitignored) — **not** left under `adaptive_bitrate_streaming/data/`. |
| `abr_spec/validate_ckpt.py downloaded_plms/ft_plms/try_llama2_7b` | **VERDICT: ABR 호환 확인 (ABR-COMPATIBLE)**, exit 0. adapter `peft_type=LORA r=128 alpha=32 targets=[q_proj,v_proj] task_type=FEATURE_EXTRACTION`; 128 adapter keys, `lora_A (128,4096)`; `modules_except_plm` = 12 modules / 33 tensors, all shapes match the spec card, output head `11.weight` out_features **6**; all tensors finite; `load_state_dict(strict)` sim → PASS. (Not relying on `prepare_models.checkpoint_ready()`, which only checks filenames.) |
| `exp_pool` | `artifacts/exp_pools/exp_pool.pkl` loads as `ExperiencePool`, **19,928** transitions. |
| traces | `data/traces/test/fcc-test/` = **100** trace files (+ `mahimahi_ptrs.pkl`). |
| video | `data/videos/video1_sizes/` = `video_size_0..5` (**6** bitrate ladders). |
| `pytest` | `tests/test_mpc_draft.py` + `tests/test_speculative_acceptance.py` → **11 passed** in 0.14 s. |
| disk | `/` 100 G total, **86 G free** (15 % used; `downloaded_plms/` = 13 G). Ample. |

---

## 2. Wrapper hardening — `abr_spec/run_wrapped.py`

Added (upstream untouched; changes only in this soyun file):

1. **Cross-instance guard.** Before a run, scans every other
   `results/soyun/*/manifest.json` for its recorded GPU string. If any differs
   from this run's, prints a `!! INSTANCE CHANGED` warning to stderr listing the
   offending run(s) and stamps `"instance_changed": true` (+ `instance_change_note`,
   `current_gpu`, `prior_run_gpus`) on both the per-phase and the aggregate
   manifest. Rationale: `inference_latency` absolute values are only comparable
   within one instance.
   *This fired on both smoke runs* — the old-instance run
   `smoke_ckpt_1ep_20260831` recorded driver `535.154.05`, this instance is
   `595.58.03`.
2. **`--baseline-run-id` → `summary.json`.** Each invocation now writes
   `results/soyun/<run-id>/summary.json` (all phases so far: status, wall,
   parsed args, and a `metrics` block lifted from `selector_metrics.json`).
   With `--baseline-run-id RID` it adds a `baseline` block: per-phase latency
   mean/p50/p95 and `speedup_{mean,p50,p95} = baseline_latency / this_latency`.
3. **Prior-instance runs are refused as baselines.** The speedup is computed
   **only** when every GPU string recorded by the baseline run equals this run's
   GPU string exactly; otherwise `latency_speedup_mean: null` + a `note`. So a
   run made on the old (driver 535) instance can never serve as a latency
   baseline. (A baseline whose *manifest* is merely flagged `instance_changed`
   because some **third** run used another GPU is still accepted — its own
   per-phase GPU strings are what get checked.)
4. Each phase's `result.json` now carries a `metrics` block; the run console line
   prints `lat_mean_ms=… instance_changed=…`.

---

## 3. Smoke — `--trace-num 2`, fcc-test, video1, seed 1, `--fp16 --rank 128`

`$COMMON` = `--test --fp16 --seed 1 --plm-type llama --plm-size base --rank 128
--plm-dir ../downloaded_plms/llama/base --model-dir ../downloaded_plms/ft_plms/try_llama2_7b
--trace fcc-test --trace-num 2 --video video1 --fixed-order --device cuda:0 --device-out cuda:0`

- **(a)** `smoke_spec_a_20260901` · `+ --temporal-selector none --token-selector none --speculative-draft-steps 0`
- **(b)** `smoke_spec_b_20260901` · `+ --temporal-selector none --token-selector none --speculative-draft-steps 3 --speculative-verification-mode greedy` · `--baseline-run-id smoke_spec_a_20260901`

| metric | (a) k=0 baseline | (b) k=3 greedy |
|---|---:|---:|
| 완주 여부 (status) | **ok** | **ok** |
| QoE — `qoe_raw_mean` / `mean_reward` | 0.63511 | 0.64468 |
| &nbsp;&nbsp;mean bitrate (Mbps) | 0.65426 | 0.65904 |
| &nbsp;&nbsp;rebuffer (s/chunk · total) | 0.0 · 0.0 | 0.0 · 0.0 |
| &nbsp;&nbsp;smoothness (Mbps) | 0.01915 | 0.01436 |
| &nbsp;&nbsp;evaluated chunks | 94 | 94 |
| `inference_latency_mean_ms` | 51.501 | 57.810 |
| `inference_latency_p50_ms` | 56.688 | 66.314 |
| `inference_latency_p95_ms` | 58.330 | 67.023 |
| `inference_calls` | 94 | 94 |
| `target_plm_calls` | 94 | **90** |
| `llm_call_reduction_ratio` | 0.0 | **0.04255** |
| `acceptance_rate` | 0.0 | **0.01916** |
| `drafted_actions` | 0 | **261** |
| `accepted_actions` | 0 | **5** |
| `corrected_actions` | 0 | **89** |
| `draft_attempts` | 0 | 89 |
| `executed_speculative_actions` | 0 | 93 |
| `queued_actions_served` | 0 | **4** |
| `fallback_calls` | 0 | 1 |
| `state_mismatch_fallbacks` | 0 | 1 |
| &nbsp;&nbsp;`buffer_mismatch_fallbacks` | 0 | **1** |
| &nbsp;&nbsp;`feature_mismatch_fallbacks` | 0 | 0 |
| &nbsp;&nbsp;`return_mismatch_fallbacks` | 0 | 0 |
| `draft_generation_failures` | 0 | 0 |
| `throughput_predictor_updates` | 0 | 94 |
| wall / Test-time (s) | 7.67 / 4.864 | 8.29 / 5.457 |

`summary.json` baseline block (b vs a, **same GPU** `…595.58.03`):
`speedup_mean 0.891`, `speedup_p50 0.855`, `speedup_p95 0.870`.

### Reading of the smoke

- **PASS.** Neither run raised; every speculative counter in (b) is non-zero
  (drafts generated, verified, 5 accepted, 89 corrected, 4 queue-served, 1
  buffer-fallback).
- **QoE is essentially unchanged** (0.635 → 0.645, no rebuffering either way) —
  speculative decisions barely diverge from the plain policy here.
- **(b) is ~11 % slower than (a)** on this 2-trace smoke (`speedup 0.89×`, i.e.
  <1). Expected at this scale: greedy verification agrees with the MPC draft only
  ~2 % of the time (89/89 attempts needed a correction), so almost every step
  still pays one PLM forward — now over a **longer** context (mean 150 vs 131
  tokens, the k draft blocks are appended) plus the CPU MPC brute-force
  (6³ = 216 candidates). Only 4 of 94 calls were saved. Speedup from speculation
  needs either a higher acceptance rate or the token/temporal selectors trimming
  the verification context; a 2-trace smoke is a plumbing check, not a perf
  measurement.
- The old `NonFiniteInferenceError` / `load_state_dict` failures from
  [[PLUMBING_SMOKE]] are **gone** — fp16 datapath fixed, real r=128 ABR
  checkpoint loads clean.

---

## 4. 판정: 통과 — full-matrix estimate (execution pending team-lead approval)

**Basis:** measured CUDA-synced inference loop — (a) 4.864 s / 94 calls
(51.7 ms/call), (b) 5.457 s / 94 calls (58.1 ms/call); per-process overhead
(imports + 2-shard load + adapter load) ≈ 3–5 s.

At `--trace-num 100` each condition runs 100 traces × 48 chunks ≈ **4,800
decisions** (≈ 50.7× the smoke). Per condition:

| condition group | ms/call proxy | inference | + overhead | per run |
|---|---:|---:|---:|---:|
| 4 × non-speculative (Original, Temporal, Recent-token, Temporal+Token) | ~51.7 | ~4.1 min | ~5 s | **~4.2 min** |
| 2 × speculative k=3 (Speculative only, All three) | ~58.1 | ~4.6 min | ~5 s | **~4.8 min** |

- **Total GPU wall ≈ 4 × 4.2 + 2 × 4.8 ≈ 26–28 min ≈ 0.45 h.**
- Selector conditions add event-detection / token-scoring CPU work but also
  shorten the LLM context — net effect assumed within ±20 %.
- **Conservative ceiling (2× for cudnn autotune on varying context lengths,
  longer traces, cold FS cache): ~55 min ≈ 0.9 h.**

**Cost @ $0.228/hr:**

| | GPU time | cost |
|---|---:|---:|
| point estimate | ~0.45 h | **~$0.10** |
| conservative ceiling | ~0.9 h | **~$0.21** |

Budget **≤ $0.25** for the full README 6-condition × `--trace-num 100` matrix.
(Rate note: task-specified $0.228/hr; earlier docs used $0.162/hr.)

**Recommended launch** (one run-id, six phases, routed through `run_wrapped.py`;
first phase becomes the latency baseline for the rest — all six share this
instance so `speedup` will compute):

```bash
COMMON="--test --fp16 --seed 1 --plm-type llama --plm-size base --rank 128 \
  --plm-dir ../downloaded_plms/llama/base \
  --model-dir ../downloaded_plms/ft_plms/try_llama2_7b \
  --trace fcc-test --trace-num 100 --video video1 --fixed-order \
  --device cuda:0 --device-out cuda:0"

RID=matrix_official_$(date +%Y%m%d)
python abr_spec/run_wrapped.py --run-id $RID --phase c1_original     --ckpt-name official_abr_r128 -- $COMMON --temporal-selector none        --token-selector none            --speculative-draft-steps 0
python abr_spec/run_wrapped.py --run-id $RID --phase c2_temporal     --ckpt-name official_abr_r128 --baseline-run-id $RID -- $COMMON --temporal-selector event-aware --token-selector none            --speculative-draft-steps 0
python abr_spec/run_wrapped.py --run-id $RID --phase c3_recent_token --ckpt-name official_abr_r128 --baseline-run-id $RID -- $COMMON --temporal-selector none        --token-selector recent-timestep --selector-history-steps 5 --speculative-draft-steps 0
python abr_spec/run_wrapped.py --run-id $RID --phase c4_temporal_token --ckpt-name official_abr_r128 --baseline-run-id $RID -- $COMMON --temporal-selector event-aware --token-selector intra-timestep --speculative-draft-steps 0
python abr_spec/run_wrapped.py --run-id $RID --phase c5_speculative  --ckpt-name official_abr_r128 --baseline-run-id $RID -- $COMMON --temporal-selector none        --token-selector none            --speculative-draft-steps 3
python abr_spec/run_wrapped.py --run-id $RID --phase c6_all_three    --ckpt-name official_abr_r128 --baseline-run-id $RID -- $COMMON --temporal-selector event-aware --token-selector intra-timestep --speculative-draft-steps 3
```

⏸ **Not executed — awaiting approval.**

---

## 5. Record locations

```
results/soyun/smoke_spec_a_20260901/{manifest.json, summary.json, test_a/{result.json, manifest_phase.json, selector_metrics.json}}
results/soyun/smoke_spec_b_20260901/{manifest.json, summary.json, test_b/{result.json, manifest_phase.json, selector_metrics.json}}
```
`console.log` and `result_sim_abr_*` under each `test_*/raw/…` are git-ignored
(`results/soyun` tracks only `*.json` / `*.csv` / `*.md`).

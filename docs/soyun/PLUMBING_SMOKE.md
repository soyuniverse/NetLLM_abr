# PLUMBING_SMOKE — 1-epoch adapt→save→load→test pipeline check

**Date:** 2026-08-31 · **Author:** soyun (speculative inference)
Related: [[CHECKPOINT_RECOVERY]] · [[NEEDS_UPSTREAM]] · [[abr-smoke-blocked-checkpoint-mismatch]]

## ⇒ VERDICT: **배관 검증 미완 — BLOCKED (infra, not code)**

The pipeline could not be exercised end-to-end. It failed with a **hard error on
the very first training forward** — `NonFiniteInferenceError` at `plm_hidden`
(all 655,360 values non-finite). Root cause, isolated to a minimal repro:
**this instance's GPU cannot do fp16/bf16** — copying an fp16 tensor to CUDA, or
casting fp32→fp16 on CUDA, corrupts the data to NaN. Llama-2-7b fp32 (~26 GB)
does not fit the 24 GB card. Neither the upstream code, the wrapper, nor the
(missing) checkpoint is at fault here — it is a broken half-precision datapath
(failing GPU memory / CUDA runtime). See §3.

The wrapper `abr_spec/run_wrapped.py` itself **is complete and verified working**
(§1): cfg-path override, manifest, in-process `runpy` execution of `run_plm.py`,
error capture, timing parse, output collection all confirmed against the one
attempt.

---

## 1. `abr_spec/run_wrapped.py`

One phase per process invocation (keeps CUDA state clean between phases). It
**never edits an upstream file and never subprocesses `run_plm.py`** — it imports
the shared `config` singleton, rewrites two attributes, sets `sys.argv`, and runs
`runpy.run_path("run_plm.py", run_name="__main__")` (the exact CLI path).

| Requirement | How | Verified |
|---|---|---|
| override `cfg.plm_ft_dir` → `results/soyun/checkpoints/<name>/` | `import config; config.cfg.plm_ft_dir = …` before `run_plm` imports it (same singleton object — confirmed `cfg is config.cfg`) | ✅ run_plm created `results/soyun/checkpoints/smoke_ckpt_1ep/llama_base/…/early_stop_-1_console.log` |
| override `cfg.results_dir` → `results/soyun/<run_id>/<phase>/raw/` | same | ✅ path in manifest `cfg_overrides` |
| manifest **before** run → `results/soyun/<run_id>/manifest.json` | written pre-`runpy`; per-phase copy in `<phase>/manifest_phase.json` | ✅ contains: git commit `3cf7f40…` + branch + porcelain status, full expanded `argv` (43 tokens), seed `666`, `torch 2.2.0 / transformers 4.34.1 / peft 0.6.2 / numpy 1.24.4 / accelerate 0.23.0`, python 3.10.13, GPU string, parsed flags |
| collect results into run_id folder | `raw_dir.rglob("selector_metrics.json")` → `<phase>/`; checkpoint files enumerated; `time/training`, `time/evaluation`, `Test time` grepped from console.log into `result.json` | ✅ mechanism ran (nothing to collect — crashed pre-output) |
| seed | extracted from passthrough `--seed`; `PYTHONHASHSEED` + best-effort `random/numpy/torch/torch.cuda` pre-seed; **not bitwise-deterministic** and manifest says so — `run_plm.py:501` sets `cudnn.benchmark=True` (upstream, unpatchable here); `run_plm.set_random_seed()` / `test_on_env()` re-seed from `--seed` at run start; test_a = seeded stochastic sampling, test_b = greedy/deterministic | ✅ recorded in `determinism_notes` |

Artifacts: `results/soyun/smoke_ckpt_1ep_20260831/manifest.json`,
`…/adapt/{console.log, manifest_phase.json, result.json}`.

## 2. Phase 2 — 1-epoch adapt (`smoke_ckpt_1ep`)

Command (per [[CHECKPOINT_RECOVERY]] §5, `--num-epochs 1`, eval minimized;
`--fp16` **required** — fp32 7B ≠ 24 GB):

```
python abr_spec/run_wrapped.py --run-id smoke_ckpt_1ep_20260831 --phase adapt \
  --ckpt-name smoke_ckpt_1ep -- \
  --adapt --grad-accum-steps 32 --seed 666 \
  --plm-type llama --plm-size base --rank 128 --fp16 \
  --plm-dir ../downloaded_plms/llama/base \
  --state-feature-dim 256 --w 20 --gamma 1. \
  --lr 0.0001 --warmup-steps 2000 --num-epochs 1 --eval-per-epoch 1 \
  --target-return-scale 1 --device cuda:0 --device-out cuda:0 \
  --trace fcc-test --trace-num 1 --video video1 --fixed-order
```

Result: **`status: error`, wall 19.4 s.**

```
Experience dataset info: Munch({... max_timestep: 46, max_action: 5 ...})   # exp_pool.pkl loaded OK
Loading checkpoint shards: 100%|██████| 2/2 [00:17<00:00, 8.74s/it]         # base model loaded (~17 s)
pad token is None, set to id 32000                                          # resize 32000->32001
Trainer.train_epoch -> train_step -> model.forward -> _run_plm
  -> _require_finite(hidden, 'plm_hidden')
  -> NonFiniteInferenceError: stage=plm_hidden dtype=float32 shape=[1,160,4096]
     finite_elements=0 / 655360     # the ENTIRE Llama hidden state is NaN
```

The fork's own NaN guard (`rl_policy.py:299`) fired correctly — it is doing its
job; the input was already garbage.

### Wall-clock captured (for recalibration)
| segment | measured |
|---|---|
| wrapper + imports | ~2 s |
| Llama-2-7b 2-shard load (fp16) | **~17 s** |
| first training forward → crash | — (never completed one step) |
| **per-step train time** | **not measurable** (crashed at step 1) |

## 3. Root cause — GPU cannot do fp16 (minimal repro)

`abr_spec/gpu_fp16_diagnostic.py + results/soyun/smoke_ckpt_1ep_20260831/gpu_fp16_diagnostic.log`:

```
torch 2.2.0  cuda 12.1  gpu NVIDIA GeForce RTX 3090  cap (8,6)  driver 535.154.05
torch.float32   cpu->cuda finite=True   roundtrip_match=True
torch.float16   cpu->cuda finite=False  roundtrip_match=False    <-- corrupts to NaN
torch.bfloat16  cpu->cuda finite=False  roundtrip_match=False
fp16 matmul on cuda            finite=False
fp32->fp16 cast ON cuda        finite=False   (reproducible)
Llama-2-7b embed weight  on CPU  finite=True  (absmean 0.0135 — correct)
Llama-2-7b embed weight  on CUDA finite=False (reproduced twice)
```

Nuance: *small* 1-D fp16 transfers (≤4096 elems) survive; large 2-D transfers /
on-device fp16 casts corrupt. Size-dependent, intermittent → consistent with a
**hardware fault (VRAM / fp16 datapath) or a broken container CUDA runtime**, not
a torch API misuse.

- The on-disk weights are **fine** — all 323 safetensors tensors verified finite
  (`safe_open` scan). `pytorch_model.bin.index.json` present but harmless
  (safetensors preferred).
- Not application-fixable. `cudnn.benchmark`, matmul-precision flags, etc. don't
  touch a plain memcpy/cast.
- fp32 works, but Llama-2-7b fp32 ≈ 26 GB > 24 GB VRAM.

### Options to unblock (need a decision / infra action)
1. **Different GPU instance** (or reseat/replace this card) — cleanest.
2. **Reinstall the CUDA stack** — try `torch==2.2.0+cu118` or a newer torch
   (~2.5 GB download, needs approval); ~30 % chance it's a runtime mismatch
   rather than silicon.
3. **CPU fp32 fallback** — `--device cpu --device-out cpu`. Functionally valid
   (CPU fp16/fp32 load verified finite) but ~20–50× slower: a 1-epoch adapt ≈
   1–3 h, a 2-trace test ≈ 10–30 min. Tolerable only for the plumbing check,
   not for anything timed.

## 4. Secondary observation (latent, would bite even on a good GPU)

`plm_special/trainer.py:37-42`: the AMP `GradScaler` is enabled **only when
`nbs_allocator is not None`** (i.e. `--nbs-v19`). A plain `--fp16 --adapt` run
(no NBS) therefore does fp16 `loss.backward()` with **no loss scaling**. The loss
itself is computed in fp32 (hidden `.float()` bridge + fp32 `action_head` +
`CrossEntropyLoss`), so it may be survivable, but it is an untested path — the
upstream adapt command in the ABR README has no `--fp16` at all. Logged as
[[NEEDS_UPSTREAM]] #3. Not the cause of today's failure.

## 5. Recalibrated full-retrain estimate (unvalidated — per-step time not measured)

Only the **base-model load (~17 s)** was measured before the crash; the training
step cost stays modeled from [[CHECKPOINT_RECOVERY]] §5.

- dataset: 996 samples/epoch (`⌈(19928−20+1)/20⌉`), batch 1, 32 optim steps/epoch
  → **79,680 fwd+bwd** for 80 epochs.
- per step: 7B fp16, seq 160 tok, LoRA-only grads → **0.15–0.30 s/step (est.)**.
- **training ≈ 3.3–6.6 h.**
- eval: `--eval-per-epoch 2 --trace-num 100` → 40 rollouts × ~4800 fwd ≈ **+2–3.5 h**;
  lean (`--eval-per-epoch 20 --trace-num 10`) → **+minutes**.

### Cost @ **$0.162/h**

| scenario | wall | cost |
|---|---|---|
| 1-epoch plumbing smoke (adapt only) | ~5–10 min | **~$0.02** |
| full 80-epoch, lean eval | ~3.5–6.5 h | **~$0.57–$1.05** |
| full 80-epoch, default eval (`--trace-num 100`, `--eval-per-epoch 2`) | ~5.5–10 h | **~$0.89–$1.62** |
| 6-condition ablation test pass (100 traces each, post-train) | ~30–60 min | **~$0.08–$0.16** |
| **end-to-end (full lean train + 6-cond ablation)** | ~4–7 h | **~$0.65–$1.20** |

⚠ All contingent on a **working fp16 GPU**. On CPU fp32 the full retrain is
~days and not worth costing.

---

## Recommendation

1. **Infra first:** get a GPU where `torch.randn(4096,4096,dtype=torch.float16).cuda()`
   stays finite (run `abr_spec/gpu_fp16_diagnostic.py`
   to check). Options in §3.
2. Then re-run: `abr_spec/run_wrapped.py … --phase adapt` (1 epoch) → the two
   `--phase test_a/test_b` calls from task step 3. The wrapper is ready; only the
   GPU is blocking.
3. Independently escalate to team lead: (a) the missing fork-compatible ABR
   checkpoint ([[CHECKPOINT_RECOVERY]]), (b) whether `--fp16 --adapt` without NBS
   is intended ([[NEEDS_UPSTREAM]] #3).

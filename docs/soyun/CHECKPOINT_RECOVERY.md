# CHECKPOINT_RECOVERY — fork-compatible ABR checkpoint

**Date:** 2026-08-31, **resolved 2026-09-01** · **Author:** soyun (speculative inference)

Related: [[NEEDS_UPSTREAM]] · [[RECON_SPECULATIVE]] · [[abr-smoke-blocked-checkpoint-mismatch]]
· [[ASSETS]] §3 · `results/soyun/ckpt_validation_20260901/`

---

## ⇒ CONCLUSION: **[해결: 원본 ABR 링크로 확보]** — the fork IS compatible with the official ABR checkpoint

**2026-09-01.** Team lead said "use the trained LoRA from the upstream NetLLM
GitHub". Followed up: the upstream ABR README's Google-Drive id
`17UyXJ9rGc0wKUkAhQ4wMrYDEbRPRjil0` (the same id the fork's
`scripts/prepare_models.py:16` already uses) serves a **288 MB** zip
(sha256 `27b3b72b…`) that is a genuine **rank-128 ABR** checkpoint:
`modules_except_plm.bin` = 33 tensors / 12 modules / `action_head (6,4096)`,
matching this fork's `OfflineRLPolicy` exactly. `abr_spec/validate_ckpt.py`
verdict: **ABR 호환 확인**; CPU `load_model` simulation: **PASS**.

**Why the earlier "retrain required" was wrong:** the old instance had a
*different*, 77 MB file pre-staged as `/root/try_llama2_7b.zip`
(sha256 `57062c71…`, r=32, `task_head` out=3) — a **viewport-prediction**
checkpoint left over from the sibling `/root/NetLLM` VP project. Both upstream
READMEs (ABR and VP) tell you to unzip into a folder literally named
`try_llama2_7b`, so the stale VP zip looked like "the ABR checkpoint" and the
whole §3 spec-card mismatch flowed from inspecting the wrong file. The fork's
`prepare_models.py` id was **correct all along**; nothing in the fork is wrong
here. Retraining (§5) is retained below only as a fallback / for a from-scratch
reproduction.

**Placement + the one real caveat** (a stale checkpoint dir makes
`prepare_models.checkpoint_ready()` silently skip the download): [[ASSETS]] §3.

---

> ## ⚠ Sections 1–6 below are the 2026-08-31 investigation, written while the
> stale **VP** `try_llama2_7b.zip` (sha `57062c71…`) was mistaken for the ABR
> checkpoint. Kept for the audit trail. Corrections:
> - **§3c / §4** — "the official Drive `17UyXJ9…` = `/root/try_llama2_7b.zip`
>   (sha `57062c71`)" is **false**. `17UyXJ9…` actually serves a 288 MB zip
>   (sha `27b3b72b…`), r=128, ABR-compatible. `/root/try_llama2_7b.zip` was an
>   unrelated pre-staged VP file.
> - **§4 "No usable one"** → **superseded**: the id downloads fine and validates
>   ABR-compatible (`abr_spec/validate_ckpt.py`, `results/soyun/ckpt_validation_20260901/`).
> - **§3a/§3b spec card is still correct** and is exactly what the real ABR
>   checkpoint matches.
> - **§5 retrain estimate** stays valid as a *fallback* only.

## 1. Commit `3cf7f40` "Document upstream ABR data restoration"

`git show 3cf7f40 --stat`: touches **`.gitignore`, `README.md`, `scripts/validate_release.py`** only. **No checkpoint procedure.**

Content = README §"ABR 데이터 범위와 원본 전체 데이터 복원": the shipped
`data/` is a subset (fcc-test + video1_sizes + exp_pool.pkl); to get
`traces/train`, `traces/valid`, `videos/video2_sizes`, `all_models` you sparse-
clone `github.com/duowuyms/NetLLM`. `validate_release.py` gains
`--allow-upstream-data`. Purpose of those extra files (per the doc): LoRA/policy
**re-training**, video2 eval, Genet/UDR baselines. **The doc never mentions a
checkpoint download** — it assumes you either use the "공식 LoRA" (the broken
link) or retrain.

→ Nothing here recovers a checkpoint.

## 2. Every checkpoint reference in the repo

| Location | Says |
|---|---|
| `scripts/prepare_models.py:16` | `OFFICIAL_LORA_FILE_ID = '17UyXJ9rGc0wKUkAhQ4wMrYDEbRPRjil0'` → gdown → unzip → `data/ft_plms/try_llama2_7b/` |
| `README.md:118,219,239` | "공식 rank-128 LoRA", `--rank 128`, `--model-dir data/ft_plms/try_llama2_7b` |
| fork's original ABR README (`git show 2d15822:adaptive_bitrate_streaming/README.md:110`) — verbatim upstream text | *"We offer the model checkpoint of the finetuned Llama2-7b here: https://drive.google.com/file/d/17UyXJ9rGc0wKUkAhQ4wMrYDEbRPRjil0/view … store it in `data/ft_plms/try_llama2_7b` … `--rank 128`"* |
| `analysis/run_official_lora_ablation.py:33-55` `validate_official_checkpoint` | requires files `adapter_config.json` + `modules_except_plm.bin` + (`adapter_model.bin` or `.safetensors`); `peft_type == "LORA"`; **`config["r"] == --rank` (default 128)** |
| `scripts/check_installation.py:50`, `scripts/validate_release.py`, `analysis/smoke_test_inference_features.py` | same 3-file contract; smoke script names them `VP_CHECKPOINT_CANDIDATES` / "VP adapter" |

**There is exactly one checkpoint URL in the entire repo, and it is `17UyXJ9…`.**
`git log -S17UyXJ9…` → introduced in `f4be263` ("Prepare public ABR inference
release"); it is a copy of the upstream ABR README's link.

### What `validate_official_checkpoint` actually accepts

Only a *file-existence + `peft_type` + `r == rank`* check. It does **not** look
inside `modules_except_plm.bin`. So a checkpoint "passes validation" iff:
`adapter_config.json` has `peft_type=LORA` and `r == 128`, and the 3 files exist.
The real constraint (module **shapes**) is only enforced later by
`run_plm.load_model` → `load_state_dict`.

## 3. Required checkpoint spec card

Base model: `meta-llama/Llama-2-7b-hf`, fp16, `hidden_size = 4096`, 32 layers.
Policy hyperparams from `$COMMON` + `exp_pool.pkl`: `state_feature_dim = 256`,
`w = 20`, `conv_size = 4` (default), `bitrate_levels = 6`,
`max_ep_len = max_timestep(46) + 1 = 47` → `embed_timestep = Embedding(48, 4096)`.

### 3a. LoRA adapter (`adapter_model.bin` + `adapter_config.json`)

| field | required value | source |
|---|---|---|
| `peft_type` | `LORA` | `low_rank.peft_model` non-NBS branch, `low_rank.py:142` |
| `r` | **128** (to satisfy `--rank 128` / `validate_official_checkpoint`) | `low_rank.py:143` `r=rank` |
| `lora_alpha` | 32 | `low_rank.py:144` (hard-coded) |
| `lora_dropout` | 0.05 | (peft default used in training) |
| `target_modules` | `["q_proj", "v_proj"]` | `low_rank.py:135` `TARGET_MODULES['llama']` |
| `task_type` | `FEATURE_EXTRACTION` | LoRA on a bare `LlamaModel` |
| key count | **128** = 32 layers × {q_proj,v_proj} × {lora_A,lora_B} | |
| per-key shapes | `…q_proj.lora_A.weight [128,4096]`, `…q_proj.lora_B.weight [4096,128]` (same for v_proj) | r=128 |

### 3b. `modules_except_plm.bin` — 12 sub-modules, **33 tensors** (built & dumped from `rl_policy.py:168`)

| idx | module (`rl_policy.py`) | tensors (shape) |
|---:|---|---|
| 0 | `state_encoder` (`EncoderNetwork`, embed_dim=256) | `0.fc1.0.weight [256,1]` `0.fc1.0.bias [256]` · `0.fc2.0.*` · `0.conv3.0.weight [256,1,4]` `0.conv3.0.bias [256]` · `0.conv4.0.*` · `0.conv5.0.weight [256,1,6]` `0.conv5.0.bias [256]` · `0.fc6.0.*` |
| 1 | `embed_timestep` `Embedding(48,4096)` | `1.weight [48,4096]` |
| 2 | `embed_return` `Linear(1,4096)` | `2.weight [4096,1]` `2.bias [4096]` |
| 3 | `embed_action` `Linear(1,4096)` | `3.weight [4096,1]` `3.bias [4096]` |
| 4 | `embed_ln` `LayerNorm(4096)` | `4.weight [4096]` `4.bias [4096]` |
| 5 | `embed_state1` `Linear(256,4096)` | `5.weight [4096,256]` `5.bias [4096]` |
| 6 | `embed_state2` `Linear(256,4096)` | `6.weight [4096,256]` `6.bias [4096]` |
| 7 | `embed_state3` `Linear(768,4096)` (`256×(6−4+1)`) | `7.weight [4096,768]` `7.bias [4096]` |
| 8 | `embed_state4` `Linear(768,4096)` | `8.weight [4096,768]` `8.bias [4096]` |
| 9 | `embed_state5` `Linear(256,4096)` | `9.weight [4096,256]` `9.bias [4096]` |
| 10 | `embed_state6` `Linear(256,4096)` | `10.weight [4096,256]` `10.bias [4096]` |
| 11 | **`action_head` `Linear(4096, 6)`** | `11.weight [6,4096]` `11.bias [6]` ✅ out=6 |

`load_model` does a **strict** `load_state_dict` (`run_plm.py:105`) — every key
and shape must match exactly.

### 3c. diff table — required spec vs. the two checkpoints on this box

| aspect | **required (fork)** | (a) official Drive `17UyXJ9…` = `/root/try_llama2_7b.zip` (sha `57062c71`) | (b) local — same file (there is no separate "VP adapter"; (a) and (b) are one file) |
|---|---|---|---|
| task | ABR, 6 discrete bitrates | **viewport prediction, 3-D output** | ← |
| `adapter_config.r` | 128 | **32** | 32 |
| `lora_alpha` | 32 | 32 ✔ | 32 |
| `target_modules` | q_proj, v_proj | q_proj, v_proj ✔ | ✔ |
| adapter keys | 128 @ `[128,4096]`/`[4096,128]` | 128 @ **`[32,4096]`/`[4096,32]`** | ✔ 32 |
| `modules_except_plm.bin` tensors | **33** (12 modules) | **10** (5 modules) | ← |
| output head | `11` = `Linear(4096,6)` → `[6,4096]` | `4.task_head.0` = `Linear(4096,3)` → **`[3,4096]`** | ← |
| state path | `5–10` = six `Linear(256|768 → 4096)` | `0` `Linear(256→4096)` + `1` `Linear(**768**→4096)` only | ← |
| encoder conv | `0.conv3/4` k=4, `0.conv5` k=6 | `3.0` **`Conv1d(1,256,3)`** | ← |
| entry point | `run_plm.py` (rewritten) | upstream `run_old.py` @ commit `ee4d872` (per its own README, via `/root/NetLLM` `PROVENANCE.md`) | ← |
| companion data | ABR `exp_pool.pkl` / fcc traces | `data.zip` sha `9c3b700` = `data/{viewports/Jin2022/video1..27, images/Jin2022_images}` — **zero ABR content** | ← |

**Where it breaks:** every "←" / bold cell. The adapter alone loads if you pass
`--rank 32`; `modules_except_plm.bin` then fails hard (empirically reproduced —
[[RECON_SPECULATIVE]] follow-up run, log at
`results/soyun/20260831_124559_smoke_original_k0/console.log`). Even the fork's
**first** ABR commit `3213666` already has the 12-module / out-6 layout
(`git show 3213666:…/rl_policy.py`), so no tag of this fork was ever
checkpoint-compatible with `17UyXJ9…`.

## 4. Download procedure found?

**No usable one.** The single URL (`17UyXJ9…`) is the viewport checkpoint,
already on disk as `/root/try_llama2_7b.zip`. `gdown` would just re-fetch the
same sha `57062c71`. `/root/data.zip` = viewport data. Sparse-clone of upstream
`duowuyms/NetLLM` (README §복원) brings ABR **traces**, not a checkpoint —
upstream ships no ABR `try_llama2_7b` matching ABR code.

→ **즉시 다운로드 가능: 아니오.**

## 5. Retraining estimate (`run_plm.py --adapt`) — NOT executed

### Inputs — all present, nothing to download
- base: `downloaded_plms/llama/base/` (symlinks, set up earlier) ✔
- experience pool: `artifacts/exp_pools/exp_pool.pkl` — **19,928 transitions,
  424 episodes, state shape (6,6), actions 0–5** ✔ (real ABR data; verified by
  loading via `plm_special.data.exp_pool.ExperiencePool`)
- eval env during training: `fcc-test` (bundled) ✔
- **train/valid traces NOT needed** — `adapt()` trains from `exp_dataset`
  (the pool) and evaluates on `env_settings` = fcc-test (`run_plm.py:520-523`).
  The README's "재학습 needs traces/train" refers to regenerating a *new* pool
  via `generate_exp_pool.py`; reusing the shipped pool skips that.

### Command (from upstream ABR README / `run_plm.py:650`, adjusted)
```
cd adaptive_bitrate_streaming
../.venv/bin/python run_plm.py --adapt --test \
  --grad-accum-steps 32 --seed 666 \
  --plm-type llama --plm-size base --rank 128 \
  --plm-dir ../downloaded_plms/llama/base \
  --state-feature-dim 256 --w 20 --gamma 1. \
  --lr 0.0001 --warmup-steps 2000 --num-epochs 80 --eval-per-epoch 2 \
  --target-return-scale 1 --device cuda:0 --device-out cuda:0
```

### Output IS the fork-compatible format
`save_model` (`run_plm.py:62-73`), taken when `--rank > 0`:
`model.plm.save_pretrained(dir)` → `adapter_config.json` (**`r=128`**) +
`adapter_model.safetensors`; `torch.save(model.modules_except_plm.state_dict(),
"modules_except_plm.bin")` → the **exact 33-tensor / 12-module** dict from §3b.
Verified by building the ModuleList and dumping its `state_dict()`.
⚠ It lands under `cfg.plm_ft_dir` = `adaptive_bitrate_streaming/data/ft_plms/…/
early_stop_-1_best_model/` (`run_plm.py:457,489`) — **outside soyun's
write-allowed paths, no `--output-dir` flag.** Needs the team lead, or a
`cfg.plm_ft_dir` override, before an actual training run.

### Time on RTX 3090 24 GB
- dataset: 996 samples/epoch (`len = ⌈(19928−20+1)/20⌉`), batch 1, 32 optim
  steps/epoch → **79,680 fwd+bwd** over 80 epochs.
- per step: Llama-2-7b fp16, seq ≈ `w×8 = 160` tokens, LoRA-only grads
  (~67 M trainable) + tiny head; no gradient checkpointing
  (`llama.py:71`). Estimate **0.15–0.30 s/step**.
- **training ≈ 3.5–6.5 h.** Periodic eval `--eval-per-epoch 2` → 40 rollouts ×
  (~100 traces × ~48 chunks) ≈ **+2–3 h** at `--trace-num 100`.
  Lean (`--eval-per-epoch 20 --trace-num 10`) drops eval to minutes →
  **total ≈ 4–6 h.**
- VRAM: 12.8 GB base (measured) + AdamW on ~67 M params (~0.8 GB) + activations
  ≈ **15–18 GB.** Fits.
- **Minimal structurally-valid checkpoint:** `--num-epochs 1` (no/late eval) →
  **~4–8 min**, poor QoE — unblocks speculative *plumbing* smoke, not QoE
  comparison. Enough to prove blocker #2 is gone.

## 6. Speculative unit tests (`.venv`, no GPU)

```
pytest adaptive_bitrate_streaming/tests/test_mpc_draft.py \
       adaptive_bitrate_streaming/tests/test_speculative_acceptance.py -v
→ 11 passed in 0.35s
```
- `test_mpc_draft.py` (5): full state/action rollout, horizon clipped by
  remaining chunks, pre-observed bandwidth not double-counted, `reset()` clears
  predictor history, return/buffer transition feeds next draft state.
- `test_speculative_acceptance.py` (6): accept whole matching draft; first
  mismatch → 1-step target correction; stop at first mismatch; reject on
  buffer(sec)/throughput(relative)/return deviation.

→ The MPC-draft + acceptance logic in `plm_special/speculative/` is **sound in
isolation**; the blocker is purely the missing checkpoint for the end-to-end
`run_plm.py` path.

---

## Recommended next action

1. **Ask team lead (1 line):** does a fork-layout ABR checkpoint already exist
   (r=128, 33-tensor `modules_except_plm.bin`)? If yes → get it, drop into
   `data/ft_plms/try_llama2_7b/`, done.
2. **If no:** get approval to run `run_plm.py --adapt` (§5). Needs a decision on
   the output path (`cfg.plm_ft_dir` is outside soyun's write scope) and on
   epochs (1 = fast smoke-valid, 80 = paper-faithful reference).
3. Independently, upstream should be told the ABR README's Drive link
   (`17UyXJ9…`) serves a viewport checkpoint — logged in [[NEEDS_UPSTREAM]] #2.

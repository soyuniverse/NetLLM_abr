# NEEDS_UPSTREAM — changes required outside soyun's write-allowed paths

Anything that would require editing teammate code (especially
`adaptive_bitrate_streaming/plm_special/models/`) or other shared files is
**not** made directly. Log it here and raise it with the module owner / team
lead.

Format per entry:

- **Date:**
- **File / area:**
- **Why it's needed (speculative-inference context):**
- **Proposed change:**
- **Owner to contact:**
- **Status:** open / raised / resolved

---

## 1. Official ABR LoRA is rank 32, but README / `$COMMON` say `--rank 128`

- **Date:** 2026-08-31
- **File / area:** `README.md` (lines 4, 52, 139, 219, 239 `$COMMON`),
  `adaptive_bitrate_streaming/analysis/run_official_lora_ablation.py:33-55`
  (`validate_official_checkpoint`), `adaptive_bitrate_streaming/README.md`
- **Why it's needed (speculative-inference context):** I cannot run *any* smoke
  test (Original NetLLM baseline included, which is the reference the
  speculative runs are compared against) until the rank is consistent.
- **Evidence:** The bundled official checkpoint `/root/try_llama2_7b.zip`
  (77 MB, from the exact Google-Drive id in `scripts/prepare_models.py:16`,
  `OFFICIAL_LORA_FILE_ID = '17UyXJ9rGc0wKUkAhQ4wMrYDEbRPRjil0'`) contains
  `adapter_config.json` with `"r": 32`, `"lora_alpha": 32`,
  `target_modules = [v_proj, q_proj]`, `peft_type = LORA`, `PEFT 0.6.0`.
  `adapter_model.bin` is 67,155,338 bytes ≈ 16.78 M params × fp32 = exactly
  `r=32` for q+v over 32 layers. `base_model_name_or_path` in the config is the
  original authors' path (`/data/data1/wuduo/2023_prompt_learning/...`), so this
  *is* the genuine upstream checkpoint and it is genuinely rank 32.
- **What breaks:** `run_plm.py` builds `LoraConfig(r=args.rank=128)` via
  `low_rank.peft_model` (`plm_special/models/low_rank.py:142-145`), then
  `load_model` calls `model.plm.load_adapter(model_dir, adapter_name='default')`
  (`run_plm.py:99`). Since adapter `default` already exists, PEFT loads the
  r=32 weights into the r=128 structure → `load_state_dict` size mismatch
  (`[32, 4096]` vs `[128, 4096]`) → hard `RuntimeError`.
  `run_official_lora_ablation.py:51-54` *also* explicitly rejects it:
  `checkpoint rank does not match --rank: 32 != 128`.
- **Proposed change (pick one, upstream owner decides):**
  (a) Fix the docs: `$COMMON` and all "rank-128" prose → `--rank 32`, and
      `run_official_lora_ablation.py:228` default `--rank` 128 → 32; **or**
  (b) Replace the bundled/official checkpoint with a genuine rank-128
      fine-tune (not available anywhere I can see locally; the official
      Drive file is rank 32).
  Option (a) matches the asset that actually exists.
- **Owner to contact:** repo maintainer / team lead (README + ablation runner
  author).
- **Status:** open — reported to soyun 2026-08-31. `--rank 32` empirically
  clears the adapter-load step (adapter_model.bin has 128 keys, all r=32,
  loads clean). But the run then hits blocker #2 below, which is the real
  wall. See [[RECON_SPECULATIVE]] for the speculative-path context.

---

## 2. Bundled `modules_except_plm.bin` is structurally incompatible with this fork's `OfflineRLPolicy`

- **Date:** 2026-08-31
- **File / area:** `adaptive_bitrate_streaming/run_plm.py:96-123` (`load_model`),
  `adaptive_bitrate_streaming/plm_special/models/rl_policy.py:168-172`
  (`self.modules_except_plm` ModuleList),
  `adaptive_bitrate_streaming/plm_special/models/state_encoder.py`
  (`EncoderNetwork`), and the released checkpoint itself.
- **Why it's needed:** This is a **hard blocker for every smoke test**, not just
  speculative. `load_model` does
  `model.modules_except_plm.load_state_dict(modules_state)` with no remap, so a
  structural mismatch aborts the run before any inference.
- **Evidence — the run actually executed** (venv built, `--rank 32`,
  `--trace-num 2`): Llama base loaded (2 shards, ~13 s), LoRA adapter loaded
  clean, then:
  `RuntimeError: Error(s) in loading state_dict for ModuleList:` with dozens of
  missing/unexpected keys and `size mismatch for 1.weight: [4096, 768] vs
  [48, 4096]`, `size mismatch for 2.weight: [4096] vs [4096, 1]`.
- **The two layouts:**
  - **Checkpoint `modules_except_plm.bin`** (10 tensors, 5 sub-modules):
    `0` Linear(256→4096); `1` Linear(**768**→4096); `2` LayerNorm(4096);
    `3.0` Conv1d(1, 256, k=3); `4.task_head.0` Linear(4096→**3**).
  - **This fork's `modules_except_plm`** (12 sub-modules, indices 0–11):
    `0` = `EncoderNetwork` (`fc1,fc2,conv3,conv4,conv5,fc6`),
    `1` = `embed_timestep` Embedding(48, 4096),
    `2` = `embed_return` Linear(1→4096), `3` = `embed_action` Linear(1→4096),
    `4` = `embed_ln` LayerNorm, `5–10` = `embed_state1..6` Linear(...→4096),
    `11` = `action_head` Linear(4096→**6**).
- **Interpretation (updated 2026-08-31 after deeper dig — see
  [[CHECKPOINT_RECOVERY]]):** the checkpoint at `17UyXJ9…` is a
  **viewport-prediction checkpoint, not ABR at all.** Evidence: (1) its
  `modules_except_plm.bin` head is `4.task_head.0 = Linear(4096, 3)` — a 3-D
  viewport vector, not 6 bitrates; (2) the sibling repo `/root/NetLLM`
  (`third_party/netllm_upstream/PROVENANCE.md`) documents this exact checkpoint
  (same sha `57062c71`) as the upstream VP checkpoint whose own README names
  `run_old.py` @ upstream commit `ee4d872` and assembly
  `SimpleLinearTaskHead(output_dim=3)` → `EmbeddingForViewportPrediction`;
  (3) its companion `data.zip` (sha `9c3b700`) is 100 % viewport data
  (`viewports/Jin2022/video1..27`, `images/Jin2022_images/`), zero ABR content;
  (4) the fork's own `smoke_test_inference_features.py` calls it
  `VP_CHECKPOINT_CANDIDATES` / "VP adapter". Upstream `duowuyms/NetLLM`'s ABR
  README links this VP file as "the finetuned Llama2-7b checkpoint" — an
  upstream publishing error. **Even the fork's first ABR commit `3213666`
  already has the 12-module / 6-output layout**, so this is not a
  fork-introduced regression — there has simply never been an ABR checkpoint
  for this code path anywhere.
- **Consequence:** The rank-128, 12-module-layout checkpoint that this fork's
  code + `validate_official_checkpoint` (`r==128`) expect **does not exist in
  this environment** and is not on the official Google-Drive id (that serves the
  r=32 / old-layout file). It would have to be re-produced by fine-tuning the
  ABR policy on *this fork's* `run_plm.py --adapt` path, or obtained from
  whoever on the team has run the ablation before.
- **Proposed change (upstream owner decides):**
  (a) Publish / share the actual fork-compatible checkpoint
      (`adapter_model` r=128 + `modules_except_plm.bin` matching the 12-module
      list) and fix the README download instructions to point at it; **or**
  (b) Add a documented `--adapt` training recipe to regenerate it from
      `exp_pool.pkl`; **or**
  (c) If the official r=32 / old-layout checkpoint is meant to be usable, add a
      `modules_except_plm` compatibility shim in `load_model` and revert the
      encoder/head refactor's breaking rename — but that changes ABR semantics
      and is squarely a team-lead decision.
- **Owner to contact:** repo maintainer / whoever trained the current ABR
  `OfflineRLPolicy` layout.
- **Status:** open — reported to soyun 2026-08-31. **Smoke test cannot run**
  until a fork-compatible checkpoint is available. Nothing in soyun's
  write-allowed paths can fix this.

---

## 3. `--fp16 --adapt` (non-NBS) has no gradient loss-scaling

- **Date:** 2026-08-31
- **File / area:** `adaptive_bitrate_streaming/plm_special/trainer.py:37-42`
- **Why it's needed:** Retraining a fork-compatible ABR checkpoint
  ([[CHECKPOINT_RECOVERY]]) on a 24 GB GPU requires `--fp16` (fp32 7B ≈ 26 GB).
- **Detail:** `scaler_enabled = bool(self.nbs_allocator is not None and
  getattr(args, 'fp16', False) and …)` — the AMP `GradScaler` is armed **only
  under `--nbs-v19`**. A plain `--fp16 --adapt` run does fp16 `loss.backward()`
  with no loss scaling. Loss is computed in fp32 (hidden `.float()` bridge →
  fp32 `action_head` → `CrossEntropyLoss`) and non-finite batches are skipped
  (`trainer.py:304`, abort after 3 consecutive), so it may limp through — but it
  is untested (upstream ABR README's adapt command has no `--fp16`).
- **Proposed change:** arm `GradScaler(enabled = args.fp16 and cuda)` for the
  plain-LoRA path too, or document that `--fp16 --adapt` needs `--nbs-v19`, or
  provide an fp32/offload adapt recipe for ≤24 GB GPUs.
- **Owner to contact:** trainer / NBS author.
- **Status:** open, low priority — **not** the current blocker (that is a broken
  GPU fp16 datapath: infra, not code — see [[PLUMBING_SMOKE]] §3). Next thing to
  hit once a working fp16 GPU is available.

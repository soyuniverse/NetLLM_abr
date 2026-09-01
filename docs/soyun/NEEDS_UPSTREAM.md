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

## 1+2. [RESOLVED — not an upstream bug] "wrong rank / wrong-task checkpoint"

- **Date:** filed 2026-08-31, **closed 2026-09-01**
- **Original claim (WITHDRAWN):** the checkpoint at `scripts/prepare_models.py:16`
  `OFFICIAL_LORA_FILE_ID = '17UyXJ9rGc0wKUkAhQ4wMrYDEbRPRjil0'` was rank 32 with
  a viewport-shaped `modules_except_plm.bin` (`task_head` out=3), so the fork's
  `--rank 128` + 12-module `OfflineRLPolicy` could never load it.
- **What was actually wrong:** the *old instance* had an unrelated 77 MB file
  pre-staged as `/root/try_llama2_7b.zip` (sha `57062c71…`) — a viewport
  checkpoint from the sibling `/root/NetLLM` VP project. It was mistaken for the
  ABR checkpoint (both upstream READMEs unzip into a folder named
  `try_llama2_7b`). **The Drive id itself is correct.**
- **Verified 2026-09-01 (CPU only):** `gdown 17UyXJ9…` → 288 MB zip
  (sha256 `27b3b72b…`), unzips to r=128 LoRA + a 33-tensor / 12-module
  `modules_except_plm.bin` with `action_head (6,4096)`.
  `abr_spec/validate_ckpt.py` → **ABR 호환 확인**; CPU `load_model` sim → **PASS**;
  `run_official_lora_ablation.py::validate_official_checkpoint` (`r==128`) → pass.
  Full record: `results/soyun/ckpt_validation_20260901/`, [[CHECKPOINT_RECOVERY]],
  [[ASSETS]] §3.
- **Residual upstream note (minor, cosmetic):**
  `scripts/prepare_models.py::checkpoint_ready()` returns True as soon as the 3
  filenames exist in the target dir, so it will **silently skip the download**
  if a wrong/older `data/ft_plms/try_llama2_7b/` is already present. A content
  check (rank in `adapter_config.json`, or `modules_except_plm` tensor count)
  before skipping would prevent the exact confusion this investigation hit.
  Not blocking — a clean checkout is fine. Owner: `scripts/prepare_models.py`
  author.
- **Status:** RESOLVED. No fork code change needed. Speculative smoke unblocked
  once a working fp16 GPU is available (#3 / [[PLUMBING_SMOKE]]).

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

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

---

## 4. Condition C (`--token-selector recent-timestep`) makes Llama fp16 emit an all-NaN hidden state

- **Date:** 2026-09-02
- **File / area:** `adaptive_bitrate_streaming/plm_special/models/selectors.py`
  (`RecentTimestepSelector`, ~L101-176) and/or
  `plm_special/models/selection_layout.py::recent_timestep_window`.
  **Not modified** — teammate-owned, read-only for soyun (AGENTS.md).
- **Why it's needed:** it is one of the six README evaluation conditions
  ("Recent-token only"). It is the **only** condition of the six that cannot
  complete a `--trace-num 100` run, so the README matrix is 5/6.
- **Repro (deterministic, hit twice at the identical point):**

  ```bash
  python abr_spec/run_wrapped.py --run-id baseline6_20260902 \
    --phase c_recent_token_nanprobe --ckpt-name official_abr_r128 \
    --probe nan_probe -- --test --fp16 --seed 1 \
    --plm-type llama --plm-size base --rank 128 \
    --plm-dir ../downloaded_plms/llama/base \
    --model-dir ../downloaded_plms/ft_plms/try_llama2_7b \
    --trace fcc-test --trace-num 100 --video video1 --fixed-order \
    --device cuda:0 --device-out cuda:0 \
    --temporal-selector none --token-selector recent-timestep \
    --selector-history-steps 5 --speculative-draft-steps 0
  ```

  → `NonFiniteInferenceError: non-finite ABR inference tensor at plm_hidden:
  {'shape': [1, 47, 4096], 'finite_elements': 0, 'total_elements': 192512,
  'adalora_overflow_candidates': []}` at `rl_policy.py:299`, on PLM call
  **2527 / 4700** (trace_idx 53, chunk 36). Wall 82.6 s and 83.1 s on the two runs.

- **Detail (measured by `abr_spec/nan_probe.py`, output in
  `results/soyun/baseline6_20260902/c_recent_token_nanprobe/nan_probe.json`):**
  at the failing call the *inputs* are unremarkable — fp32 absmax **5.179**,
  after the fp16 bridge **5.180**, `fp16_input_all_finite: true` (so
  `_require_finite(plm_inputs, 'plm_inputs')` passes), attention mask dense
  **47/47** with no all-zero row, context 47 tokens (5 history blocks × 8 +
  current 7). The preceding calls' `last_hidden_state` absmax runs **50-70**,
  far under fp16's 65504. The NaN is produced **inside** the frozen Llama-2-7B
  fp16 forward, and it takes out every one of the 192,512 output elements
  (single `inf` → attention softmax → whole sequence), not just the new tokens.
  Conditions B (`event-aware`, 26.6 tokens mean) and D (`event-aware +
  intra-timestep`, 19.5 tokens mean) complete all 4,700 decisions on the same
  build, GPU and seed — the failure is specific to the window
  `recent-timestep --selector-history-steps 5` retains.
- **Proposed change (owner's call):** likely an activation-outlier / fp16 range
  issue triggered by the retained window rather than a logic bug in the slice.
  Candidates: (a) run the PLM in bf16 (RTX 3090 supports it; verified finite in
  `abr_spec/gpu_fp16_diagnostic.py`) instead of fp16 for this path; (b) add the
  same `_require_finite` guard *per Llama layer* so the offending layer is
  identified; (c) re-check that `recent_timestep_window` cannot drop the
  positional/anchor token the block structure assumes. soyun did not attempt any
  of these — out of write scope.
- **Owner to contact:** `plm_special/models/selectors.py` /
  `selection_layout.py` author (Token selector module owner).
- **Status:** open. **Blocks 1 of the 6 README conditions**; the other five are
  measured in [[BASELINE6]].

---

## 5. `--speculative-draft-steps` is capped at 5 in read-only `run_plm.py`

- **Date:** 2026-09-08
- **File / area:** `adaptive_bitrate_streaming/run_plm.py:298-299`
  `if not 0 <= args.speculative_draft_steps <= 5: raise ValueError(...)`.
  **Read-only for soyun** (team-owned, HANDOFF §2.5). A second cap
  `1 <= max_horizon <= 5` sits in `plm_special/speculative/mpc_draft.py:190`
  (`BaseDraftGenerator.__init__`) — soyun-owned but frozen for the drafter
  ablation.
- **Why it's needed (speculative-inference context):** DRAFTER_ABLATION's stated
  core is testing draft length `k` past the point where MPC's `6^k` brute force
  becomes the budget (SWEEP_SPEC §4: MPC CPU is already 1.90 % of latency at
  k=5, extrapolated ≈ 39 ms at k=8, i.e. ≈ one LLM call). The zero-search
  drafters (`repeat-last`, `hybrid`'s repeat branch) have **no** `6^k` cost, so
  k=8 is exactly the regime where a working drafter should pull ahead — but the
  `run_plm.py` guard refuses `--speculative-draft-steps 8` before the wrapper
  can act, and it cannot be lifted without editing a team file.
- **Proposed change:** raise the `run_plm.py` ceiling (e.g. to 10, or make it
  configurable) and correspondingly relax `BaseDraftGenerator.__init__`'s
  `max_horizon` check. Guard against `6^k` blow-up for the `mpc` drafter
  specifically (cap mpc's own horizon, or switch mpc to beam search) rather than
  capping every drafter at 5.
- **Owner to contact:** `run_plm.py` / speculative-CLI owner (team lead opened
  `plm_special/speculative/` to soyun on 2026-09-02; the `run_plm.py` guard was
  not part of that).
- **Status:** open. **DRAFTER_ABLATION runs k ∈ {3, 5} only** — k=5 is the hard
  ceiling of the current execution path. k=8 deferred to this item.

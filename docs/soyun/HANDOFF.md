# HANDOFF — resume point (soyun / speculative inference)

**As of 2026-08-31, branch `soyun/spec-abr`.** Instance being replaced (GPU fp16
defect). Everything needed is committed; follow the steps below on the new box.

## Confirmed facts (3)

1. **No fork-compatible ABR checkpoint exists.** The one URL the repo references
   (`scripts/prepare_models.py` gdrive id `17UyXJ9…` = local `try_llama2_7b.zip`)
   is a **viewport-prediction** checkpoint (`task_head` out=3, r=32, 5-module
   `modules_except_plm.bin`). This fork's `OfflineRLPolicy` needs r=128 + a
   33-tensor / 12-module `modules_except_plm.bin` with `action_head` out=6.
   Mismatch is not fork-introduced — even the first ABR commit `3213666` has the
   new layout. → [[CHECKPOINT_RECOVERY]].
2. **This instance's GPU cannot do fp16/bf16** — `torch.randn(4096,4096,
   dtype=float16).cuda()` → all-NaN; fp32→fp16 cast on CUDA → NaN. fp32 works but
   Llama-2-7b fp32 (~26 GB) > 24 GB VRAM. On-disk weights verified finite. →
   [[PLUMBING_SMOKE]] §3, repro `abr_spec/gpu_fp16_diagnostic.py`.
3. **Speculative logic is sound in isolation** — `pytest
   adaptive_bitrate_streaming/tests/test_mpc_draft.py
   adaptive_bitrate_streaming/tests/test_speculative_acceptance.py` → **11
   passed**. The blocker is purely the end-to-end `run_plm.py` checkpoint path.

## First steps on the new server

```bash
git clone <remote> && cd NetLLM_abr && git checkout soyun/spec-abr
bash abr_spec/hooks/install.sh
python -m venv .venv --system-site-packages
.venv/bin/pip install -U pip && .venv/bin/pip install -r abr_spec/requirements-soyun.txt
# sanity: GPU must survive fp16
.venv/bin/python abr_spec/gpu_fp16_diagnostic.py    # every 'finite' must be True
# re-fetch base weights (see docs/soyun/ASSETS.md §1)
huggingface-cli login
huggingface-cli download meta-llama/Llama-2-7b-hf --local-dir downloaded_plms/llama/base --local-dir-use-symlinks False
# re-confirm speculative units
.venv/bin/python -m pytest adaptive_bitrate_streaming/tests/test_mpc_draft.py adaptive_bitrate_streaming/tests/test_speculative_acceptance.py -q
```

## Action branches

### Branch A — team lead provides a fork-compatible checkpoint
Drop its 3 files into `adaptive_bitrate_streaming/data/ft_plms/try_llama2_7b/`
(or anywhere, use `--model-dir`). First command — the cheapest smoke:
```bash
cd adaptive_bitrate_streaming
../.venv/bin/python run_plm.py --test --fp16 --seed 1 \
  --plm-type llama --plm-size base --rank 128 \
  --plm-dir ../downloaded_plms/llama/base \
  --model-dir <checkpoint dir> \
  --trace fcc-test --trace-num 2 --video video1 --fixed-order \
  --device cuda:0 --device-out cuda:0 \
  --temporal-selector none --token-selector none --speculative-draft-steps 0
```
Then the 6-condition matrix from README (`$COMMON`), routed through
`abr_spec/run_wrapped.py` so outputs land under `results/soyun/`.

### Branch B — retrain approved
```bash
python abr_spec/run_wrapped.py --run-id smoke_ckpt_1ep_<date> --phase adapt \
  --ckpt-name smoke_ckpt_1ep -- \
  --adapt --grad-accum-steps 32 --seed 666 \
  --plm-type llama --plm-size base --rank 128 --fp16 \
  --plm-dir ../downloaded_plms/llama/base \
  --state-feature-dim 256 --w 20 --gamma 1. \
  --lr 0.0001 --warmup-steps 2000 --num-epochs 1 --eval-per-epoch 1 \
  --target-return-scale 1 --device cuda:0 --device-out cuda:0 \
  --trace fcc-test --trace-num 1 --video video1 --fixed-order
```
If it completes: glob `results/soyun/checkpoints/smoke_ckpt_1ep/**/early_stop_-1_best_model/`
for the checkpoint, then run `--phase test_a` / `--phase test_b` (task step 3:
`--trace-num 2`, one with `--speculative-draft-steps 0`, one with
`--speculative-draft-steps 3 --speculative-verification-mode greedy`).
Full-retrain estimate + cost: [[CHECKPOINT_RECOVERY]] §5 / [[PLUMBING_SMOKE]] §5
(~$0.65–1.20 end-to-end at $0.162/h, contingent on a working fp16 GPU).
`run_wrapped.py` already redirects `cfg.plm_ft_dir` → `results/soyun/checkpoints/`
and `cfg.results_dir` → `results/soyun/<run_id>/<phase>/raw/`.

## Open items — NEEDS_UPSTREAM ([[NEEDS_UPSTREAM]])

- **#1** README/`$COMMON` say `--rank 128`; the (wrong) bundled checkpoint is
  r=32. `run_official_lora_ablation.validate_official_checkpoint` enforces
  `r == --rank`. Real fix rides on #2.
- **#2** Bundled `modules_except_plm.bin` is viewport-shaped, not ABR — the ABR
  README's gdrive link serves a VP checkpoint (upstream publishing error). No
  ABR checkpoint for this code path exists → retrain or lead provides one.
- **#3** `trainer.py:37-42` — AMP `GradScaler` armed only under `--nbs-v19`, so
  plain `--fp16 --adapt` has no loss scaling. Latent; would bite after the GPU
  is fixed. Not today's blocker.

All three are upstream-file changes → **not** to be made by soyun; escalate to
the repo maintainer / whoever trained the current `OfflineRLPolicy` layout.

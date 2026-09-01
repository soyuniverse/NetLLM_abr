# HANDOFF — resume point (soyun / speculative inference)

**As of 2026-09-01, branch `soyun/spec-abr`.** Old instance replaced (GPU fp16
defect). Everything needed is committed; follow the steps below on the new box.

## Confirmed facts (3)

1. **The official ABR checkpoint exists and is fork-compatible** (resolved
   2026-09-01). Upstream ABR README's Drive id
   `17UyXJ9rGc0wKUkAhQ4wMrYDEbRPRjil0` (= `scripts/prepare_models.py:16`) serves
   a **288 MB** zip (sha `27b3b72b…`): r=128 LoRA + 33-tensor / 12-module
   `modules_except_plm.bin`, `action_head (6,4096)`. `abr_spec/validate_ckpt.py`
   → **ABR 호환 확인**, CPU `load_model` sim → **PASS**. The earlier "must
   retrain" was caused by a stale *viewport* zip pre-staged on the old instance
   (`/root/try_llama2_7b.zip`, sha `57062c71`). → [[CHECKPOINT_RECOVERY]],
   [[ASSETS]] §3, `results/soyun/ckpt_validation_20260901/`.
2. **The old instance's GPU could not do fp16/bf16** — `torch.randn(4096,4096,
   dtype=float16).cuda()` → all-NaN. fp32 worked but 7B fp32 (~26 GB) > 24 GB.
   → [[PLUMBING_SMOKE]] §3, repro `abr_spec/gpu_fp16_diagnostic.py`. **Run this
   first on the new GPU.**
3. **Speculative logic is sound in isolation** — `pytest
   adaptive_bitrate_streaming/tests/test_mpc_draft.py
   adaptive_bitrate_streaming/tests/test_speculative_acceptance.py` → **11
   passed**. The only remaining blocker was the GPU.

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

### Branch A — use the official ABR checkpoint (DEFAULT — team lead's instruction)
```bash
# fetch + place (see docs/soyun/ASSETS.md §3 for the checkpoint_ready() gotcha)
python scripts/prepare_models.py         # -> adaptive_bitrate_streaming/data/ft_plms/try_llama2_7b/
.venv/bin/python abr_spec/validate_ckpt.py adaptive_bitrate_streaming/data/ft_plms/try_llama2_7b
# expect: VERDICT: ABR 호환 확인   (if VP 재확인 -> a stale dir was there; delete + re-fetch)

# cheapest smoke:
cd adaptive_bitrate_streaming
../.venv/bin/python run_plm.py --test --fp16 --seed 1 \
  --plm-type llama --plm-size base --rank 128 \
  --plm-dir ../downloaded_plms/llama/base \
  --model-dir data/ft_plms/try_llama2_7b \
  --trace fcc-test --trace-num 2 --video video1 --fixed-order \
  --device cuda:0 --device-out cuda:0 \
  --temporal-selector none --token-selector none --speculative-draft-steps 0
```
Then the 6-condition matrix from README (`$COMMON`), routed through
`abr_spec/run_wrapped.py` so outputs land under `results/soyun/`.
CPU pre-checks already done (`load_model` sim PASS); the only unknown left is
GPU forward numerics — hence fact #2's `gpu_fp16_diagnostic.py` gate.

### Branch B — retrain (fallback only, if the official checkpoint ever fails on GPU)
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

- **#1+#2 — RESOLVED (not a bug).** The Drive id is correct; the r=32/head-3
  file was a stale *viewport* zip pre-staged on the old instance. Official ABR
  checkpoint validated ABR-compatible. Minor cosmetic note left for upstream:
  `prepare_models.checkpoint_ready()` skips download on filename presence alone
  (no rank/shape check) → a stale dir can silently win.
- **#3** `trainer.py:37-42` — AMP `GradScaler` armed only under `--nbs-v19`, so
  plain `--fp16 --adapt` has no loss scaling. Latent; only relevant to Branch B
  (retrain). Not needed for Branch A.

Escalate #3 (and the #1+#2 cosmetic note) to the repo maintainer; **not** to be
changed by soyun.

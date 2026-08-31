# Smoke run 20260831_124559_smoke_original_k0 — FAILED (blocked)

**Goal:** cheapest smoke — README "Original NetLLM" condition, `--trace-num 2`.

## Command (from `adaptive_bitrate_streaming/`)

```
../.venv/bin/python run_plm.py --test \
  --fp16 --seed 1 --plm-type llama --plm-size base --rank 32 \
  --plm-dir ../downloaded_plms/llama/base \
  --model-dir ../downloaded_plms/ft_plms/try_llama2_7b \
  --trace fcc-test --trace-num 2 --video video1 --fixed-order \
  --device cuda:0 --device-out cuda:0 \
  --temporal-selector none --token-selector none --speculative-draft-steps 0
```

Deviations from README `$COMMON`:
- `--rank 128` → `--rank 32` (bundled checkpoint is r=32; see NEEDS_UPSTREAM #1)
- `--model-dir data/ft_plms/try_llama2_7b` → `../downloaded_plms/ft_plms/try_llama2_7b`
  (soyun cannot write under `adaptive_bitrate_streaming/data/`; LoRA was
  extracted into the authorized `downloaded_plms/` area instead)
- `--trace-num 100` → `2` (as instructed)

## Result: RuntimeError before any inference

- venv OK, Llama-2-7b base loaded (2 safetensors shards, ~13 s)
- LoRA adapter (`adapter_model.bin`, r=32, 128 keys) loaded clean
- **`model.modules_except_plm.load_state_dict(...)` raised** — the checkpoint's
  encoder/head layout (5 sub-modules, 768-dim concat projection, 3-output
  `task_head`) does not match this fork's 12-module `OfflineRLPolicy`
  (`EncoderNetwork` + 6×`embed_stateN` + 6-output `action_head`).
- wall: 10 s. GPU peak (whole-GPU `nvidia-smi`): 12,768 MiB (base model load).

Full stderr in `console.log`. Root cause + options: `docs/soyun/NEEDS_UPSTREAM.md` #2.

## What worked / is now in place

- `/root/NetLLM_abr/.venv` (system-site-packages; torch 2.2.0 inherited,
  numpy 1.24.4 + transformers 4.34.1 + peft 0.6.2 + accelerate 0.23.0 installed
  into venv only — base conda env untouched)
- `downloaded_plms/llama/base/` → 9 symlinks to the loose Llama-2-7b snapshot in `/root/`
- `downloaded_plms/ft_plms/try_llama2_7b/` → extracted from `/root/try_llama2_7b.zip`
  (adapter_config.json, adapter_model.bin, modules_except_plm.bin, README.md)

No re-downloads were performed.

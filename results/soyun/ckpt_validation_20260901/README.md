# ckpt_validation_20260901 — official ABR checkpoint located & CPU-validated

**Result: the fork IS compatible with the official NetLLM ABR checkpoint.**
The earlier "must retrain" conclusion was wrong — it was based on a stale
viewport-prediction zip that happened to be pre-staged as `/root/try_llama2_7b.zip`
on the (now-discarded) instance. The real ABR checkpoint is a different, larger
file at the *same* Google-Drive id the fork already uses.

## What was downloaded (this instance, CPU only — GPU untouched)

| | value |
|---|---|
| source | upstream ABR README: `https://drive.google.com/file/d/17UyXJ9rGc0wKUkAhQ4wMrYDEbRPRjil0/view` (= `scripts/prepare_models.py:16` `OFFICIAL_LORA_FILE_ID`) |
| zip | `abr_17UyXJ9.zip`  288,470,767 B  sha256 `27b3b72bc897086980bcce83ffec74ad6671f4c98b19aefcf7e225e34f7596ef` |
| zip layout | `try_llama2_7b/{adapter_config.json, adapter_model.bin, modules_except_plm.bin, README.md}` (single nesting) |
| extracted to | `downloaded_plms/ft_plms/try_llama2_7b_abr_official/` (298 MB) |
| adapter_model.bin | 268,481,162 B  sha256 `f0f6f5dbe025d404a1b5ea79c9709357520c1f5c4bb728fcaec403f7cda9dad8` |
| modules_except_plm.bin | 43,059,402 B  sha256 `a66930dd60d02f66fd30ddab41acf3752548b3e12517ef49c74b775127c92323` |
| adapter_config.json | sha256 `9b602d0dea7d6f505f3413dff50b931aa28e3909b007293eb9ff533b233c2fd5` |

The pre-staged VP zip (`sha 57062c71…`, 77 MB, r=32, head=3) is kept at
`downloaded_plms/ft_plms/try_llama2_7b/` for contrast — **not** for ABR use.

## CPU validation — `abr_spec/validate_ckpt.py`

Full output: `validate_output.txt`. Summary:

| dir | adapter r | top-level modules | tensors | head out | strict load_state_dict | verdict |
|---|---:|---:|---:|---:|---|---|
| `try_llama2_7b_abr_official` | **128** | **12** | **33** | **6** | **PASS** | **ABR 호환 확인** |
| `try_llama2_7b` (VP, pre-staged) | 32 | 5 | 10 | 3 | FAIL (30 missing / 7 unexpected keys) | VP 재확인 |

Official checkpoint, item by item vs `docs/soyun/CHECKPOINT_RECOVERY.md` §3b:
- `adapter_config.json`: `peft_type=LORA`, `r=128`, `lora_alpha=32`,
  `target_modules=[q_proj,v_proj]`, `task_type=FEATURE_EXTRACTION` — all match.
- `adapter_model.bin`: 128 keys, `lora_A (128,4096)` / `lora_B (4096,128)`,
  key path `base_model.model.layers.N.self_attn.{q,v}_proj.lora_{A,B}.weight`
  (single `model` → the fork's bare custom `LlamaModel`, not HF's
  `LlamaForCausalLM`). All finite.
- `modules_except_plm.bin`: 33 tensors, 12 sub-modules
  (`state_encoder` + `embed_timestep` + `embed_return/action/ln` +
  `embed_state1..6` + `action_head`), every shape matches the spec card,
  `action_head` = `(6, 4096)` → **6 bitrates, ABR**. All finite.
- `run_plm.load_model` simulation (CPU): `modules_except_plm.load_state_dict`
  strict → **PASS**; `plm.load_adapter` → PASS (128 keys, r == `--rank 128`).
- `analysis/run_official_lora_ablation.py::validate_official_checkpoint` would
  also pass now (`r == 128`).

## Next-server placement

`scripts/prepare_models.py` downloads this id into
`adaptive_bitrate_streaming/data/ft_plms/try_llama2_7b/` (README's default path).
**Gotcha:** `prepare_models.checkpoint_ready()` skips the download if that dir
already holds the 3 filenames — so if a VP `try_llama2_7b/` is pre-staged there,
delete it first or pass `--force`. Details in `docs/soyun/ASSETS.md`.

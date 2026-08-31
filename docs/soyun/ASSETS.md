# ASSETS — what to re-fetch on the next server

The instance is being replaced (GPU fp16 defect — see [[PLUMBING_SMOKE]] §3).
Everything below that is **not** in git must be re-acquired. This table is the
checklist.

| Asset | In git on clone? | Re-fetch on next server? | Where it lives / how to get it |
|---|---|---|---|
| **Repo code + AGENTS/docs/abr_spec** | ✅ yes | **N** | `git clone` + `git checkout soyun/spec-abr`, then `bash abr_spec/hooks/install.sh` |
| **ABR `exp_pool.pkl`** | ✅ yes (tracked since commit `3213666`) | **N** | `adaptive_bitrate_streaming/artifacts/exp_pools/exp_pool.pkl` — 4.6 MB, arrives with the clone. 19,928 transitions / 424 episodes, real ABR data. |
| **fcc-test traces** | ✅ yes (101 files tracked) | **N** | `adaptive_bitrate_streaming/data/traces/test/fcc-test/` — 100 traces + `mahimahi_ptrs.pkl`, arrives with the clone. |
| **video1 chunk sizes** | ✅ yes (6 files tracked) | **N** | `adaptive_bitrate_streaming/data/videos/video1_sizes/video_size_0..5`, arrives with the clone. |
| **Python venv (.venv)** | ❌ no (.gitignored) | **Y** | Rebuild: `python -m venv .venv --system-site-packages` → `.venv/bin/pip install -U pip` → `.venv/bin/pip install -r abr_spec/requirements-soyun.txt`. ~25 MB of wheels, ~1–2 min. `pytest` from base env (or `pip install pytest`). |
| **Llama-2-7B base weights** | ❌ no (`*.safetensors` gitignored; dir is symlinks) | **Y** | HF repo **`meta-llama/Llama-2-7b-hf`** (gated — accept Meta license + `huggingface-cli login` first). ~13 GB, ~5–15 min. See §1. |
| **`try_llama2_7b.zip`** (77 MB, sha `57062c71…`) | ❌ no | **N — do NOT re-fetch** | This is the **viewport-prediction** checkpoint mislinked from upstream's ABR README (`task_head` out=3; companion data is Jin2022 viewport). **Unusable for ABR.** See [[CHECKPOINT_RECOVERY]] §3. |
| **fork-compatible ABR checkpoint** (r=128 LoRA + 33-tensor `modules_except_plm.bin`) | ❌ does not exist anywhere | **Y (blocking)** | Not downloadable. Either the team lead provides one, or retrain via `run_plm.py --adapt` (needs only exp_pool.pkl + base weights, both above). Spec + estimate in [[CHECKPOINT_RECOVERY]] §3, §5. |
| **`/root/data.zip`** (3 GB, sha `9c3b700…`) | ❌ no | **N** | Viewport-prediction dataset (Jin2022 viewports/images). Zero ABR content. Ignore. |
| smoke run logs / manifests | ✅ partial (`*.json`/`*.md` under `results/soyun/`) | **N** | `results/soyun/smoke_ckpt_1ep_20260831/` — `.log` files are gitignored but their content is quoted in [[PLUMBING_SMOKE]] and `result.json`. |

## 1. Llama-2-7B base — exact restore

Target layout expected by `run_plm.py --plm-dir ../downloaded_plms/llama/base`
(repo-root-relative), i.e. `downloaded_plms/llama/base/` must contain
`config.json`, `generation_config.json`, `model.safetensors.index.json`,
`model-0000{1,2}-of-00002.safetensors`, `tokenizer.json`, `tokenizer.model`,
`tokenizer_config.json`, `special_tokens_map.json`.

**Canonical (do this on the new server):**
```bash
huggingface-cli login                         # needs Meta-approved HF account
mkdir -p downloaded_plms/llama
huggingface-cli download meta-llama/Llama-2-7b-hf \
  --local-dir downloaded_plms/llama/base --local-dir-use-symlinks False
# or:  python scripts/prepare_models.py   (repo's own helper, same repo id)
```
Size ~13 GB (2 fp16 safetensors shards: 9.3 GB + 3.3 GB). Verify finite before
trusting the GPU: `.venv/bin/python abr_spec/gpu_fp16_diagnostic.py`.

**What existed on the OLD instance (for context only — not reproducible):**
the 9 files sat loose in `/root/` (a stray earlier `hf download` had been
mis-pointed at a dir, per `/root/NetLLM/docs/.../GATE_A_VERIFICATION.md`), and
`downloaded_plms/llama/base/` was 9 **symlinks** into `/root/`. On-disk weights
were byte-valid (all 323 tensors finite via `safe_open`); only the GPU's fp16
copy corrupted them. On the new server just download normally into the dir — no
symlinks needed.

## 2. Upstream data restore (only if training / video2 / baselines needed)

`README.md` §"ABR 데이터 범위와 원본 전체 데이터 복원": sparse-clone
`github.com/duowuyms/NetLLM`, copy `traces/train`, `traces/valid`,
`videos/video2_sizes`, `all_models`. **Not needed** for `run_plm.py --adapt`
from the bundled `exp_pool.pkl`, nor for the 6-condition fcc-test/video1
ablation. Paths are already in `.gitignore`.

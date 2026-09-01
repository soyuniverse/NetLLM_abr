# ASSETS — what to re-fetch on the next server

The instance is being replaced (GPU fp16 defect — see [[PLUMBING_SMOKE]] §3).
Everything below that is **not** in git must be re-acquired. This table is the
checklist.

> **2026-09-01 update:** the fork-compatible **official ABR checkpoint has been
> located and CPU-validated** (`abr_spec/validate_ckpt.py` → ABR 호환 확인).
> See the two rows below + §3. Retraining is no longer needed.

| Asset | In git on clone? | Re-fetch on next server? | Where it lives / how to get it |
|---|---|---|---|
| **Repo code + AGENTS/docs/abr_spec** | ✅ yes | **N** | `git clone` + `git checkout soyun/spec-abr`, then `bash abr_spec/hooks/install.sh` |
| **ABR `exp_pool.pkl`** | ✅ yes (tracked since commit `3213666`) | **N** | `adaptive_bitrate_streaming/artifacts/exp_pools/exp_pool.pkl` — 4.6 MB, arrives with the clone. 19,928 transitions / 424 episodes, real ABR data. |
| **fcc-test traces** | ✅ yes (101 files tracked) | **N** | `adaptive_bitrate_streaming/data/traces/test/fcc-test/` — 100 traces + `mahimahi_ptrs.pkl`, arrives with the clone. |
| **video1 chunk sizes** | ✅ yes (6 files tracked) | **N** | `adaptive_bitrate_streaming/data/videos/video1_sizes/video_size_0..5`, arrives with the clone. |
| **Python venv (.venv)** | ❌ no (.gitignored) | **Y** | Rebuild: `python -m venv .venv --system-site-packages` → `.venv/bin/pip install -U pip` → `.venv/bin/pip install -r abr_spec/requirements-soyun.txt`. ~25 MB of wheels, ~1–2 min. `pytest` from base env (or `pip install pytest`). |
| **Llama-2-7B base weights** | ❌ no (`*.safetensors` gitignored; dir is symlinks) | **Y** | HF repo **`meta-llama/Llama-2-7b-hf`** (gated — accept Meta license + `huggingface-cli login` first). ~13 GB, ~5–15 min. See §1. |
| **Official ABR LoRA checkpoint** (r=128, ABR-compatible) | ❌ no (`*.bin` gitignored) | **Y** | Google-Drive id **`17UyXJ9rGc0wKUkAhQ4wMrYDEbRPRjil0`** (upstream ABR README + `scripts/prepare_models.py:16`). **288 MB** zip, sha256 `27b3b72bc897086980bcce83ffec74ad6671f4c98b19aefcf7e225e34f7596ef`. See §3 for placement + the `checkpoint_ready()` gotcha. Validated ABR-compatible on 2026-09-01. |
| stale **VP `try_llama2_7b.zip`** (77 MB, sha `57062c71…`) | ❌ no | **N — do NOT re-fetch** | Viewport-prediction checkpoint (`task_head` out=3, r=32). It was pre-staged on the *old* instance as `/root/try_llama2_7b.zip` and misled the first investigation. It is **not** what upstream's ABR link serves — that link's real payload is the 288 MB r=128 file above. Companion `/root/data.zip` (3 GB, sha `9c3b700…`) is Jin2022 viewport data — also ignore. |
| smoke run logs / manifests | ✅ partial (`*.json`/`*.md` under `results/soyun/`) | **N** | `results/soyun/smoke_ckpt_1ep_20260831/` + `results/soyun/ckpt_validation_20260901/` — `.log`/`.txt` are gitignored but their content is quoted in the folder `README.md` / [[PLUMBING_SMOKE]]. |

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
`videos/video2_sizes`, `all_models`. **Not needed** for the 6-condition
fcc-test/video1 ablation. Paths are already in `.gitignore`.

## 3. Official ABR LoRA checkpoint — exact restore

**Source:** upstream ABR README (`duowuyms/NetLLM/adaptive_bitrate_streaming/
README.md`) → `https://drive.google.com/file/d/17UyXJ9rGc0wKUkAhQ4wMrYDEbRPRjil0/view`.
Same id as `scripts/prepare_models.py:16`.

| | value (observed 2026-09-01) |
|---|---|
| zip | 288,470,767 B · sha256 `27b3b72bc897086980bcce83ffec74ad6671f4c98b19aefcf7e225e34f7596ef` |
| unzips to | `try_llama2_7b/{adapter_config.json, adapter_model.bin (268 MB), modules_except_plm.bin (43 MB), README.md}` (single nesting) |
| adapter_model.bin | sha256 `f0f6f5dbe025d404a1b5ea79c9709357520c1f5c4bb728fcaec403f7cda9dad8` |
| modules_except_plm.bin | sha256 `a66930dd60d02f66fd30ddab41acf3752548b3e12517ef49c74b775127c92323` |
| adapter_config.json | sha256 `9b602d0dea7d6f505f3413dff50b931aa28e3909b007293eb9ff533b233c2fd5` |
| structure | LoRA r=128, alpha 32, q/v; `modules_except_plm` 33 tensors / 12 modules, `action_head (6,4096)` — **ABR-compatible** (`abr_spec/validate_ckpt.py`) |

**Restore on the new server** (into the README's default path):
```bash
python scripts/prepare_models.py            # fetches this id -> adaptive_bitrate_streaming/data/ft_plms/try_llama2_7b/
# or manually:
.venv/bin/python -m gdown "https://drive.google.com/uc?id=17UyXJ9rGc0wKUkAhQ4wMrYDEbRPRjil0" -O /tmp/abr.zip
mkdir -p adaptive_bitrate_streaming/data/ft_plms/try_llama2_7b
cd adaptive_bitrate_streaming/data/ft_plms/try_llama2_7b && unzip -j /tmp/abr.zip
# validate before trusting it:
.venv/bin/python abr_spec/validate_ckpt.py adaptive_bitrate_streaming/data/ft_plms/try_llama2_7b
```

**⚠ GOTCHA:** `scripts/prepare_models.py::checkpoint_ready()` **skips the
download** if `data/ft_plms/try_llama2_7b/` already contains
`adapter_config.json` + `adapter_model.bin` + `modules_except_plm.bin`. The old
instance had a *viewport* checkpoint sitting there (77 MB, r=32, head=3) — if
anything like that is pre-staged, delete the dir first (or `prepare_models.py
--force`), then re-validate. On a clean new server this is a non-issue.

# ASSETS — what to re-fetch on the next server

Everything not in git must be re-acquired on a fresh instance. This file is the
checklist; [[VASTAI_SETUP]] is the step-by-step that uses it.

> **Status 2026-09-02.** The official ABR checkpoint is located, hash-pinned and
> CPU-validated (`abr_spec/validate_ckpt.py` → ABR 호환 확인) — retraining is not
> needed. All BASELINE6 / SWEEP_SPEC runs used the assets hashed below; matching
> these hashes is what makes those results reproducible.

## 0. Full asset table

Every row: source, filename, sha256, placement path, size, wall time, and
whether the next server needs it.

| Asset | Source | Filename(s) | sha256 | Placement (repo-root relative) | Size | Fetch time | Needed next server? |
|---|---|---|---|---|---|---|---|
| **Llama-2-7B base** | HF `meta-llama/Llama-2-7b-hf` (gated: accept Meta licence + `huggingface-cli login`) | `model-00001-of-00002.safetensors`<br>`model-00002-of-00002.safetensors`<br>`model.safetensors.index.json`<br>`config.json`<br>`tokenizer.model`, `tokenizer.json`, `tokenizer_config.json`, `special_tokens_map.json`, `generation_config.json` | `4ec71fd53e99766de38f24753b30c9e8942630e9e576a1ba27b0ec531e87be41`<br>`41780b5dac322ac35598737e99208d90bdc632a1ba3389ebedbb46a1d8385a7f`<br>`217d527037a95cd5cd30384afb425987824373b94cc7206beb48ec0c9499c98f`<br>`9242e7db1bc2a17873e66084c3b1c6ed10883076e156b338fd6a7775748e2e3c`<br>`tokenizer.model` `9e556afd44213b6bd1be2b850ebbbd98f5481437a8021afaf58ee7fb1818d347`<br>`tokenizer.json` `bcd04f0eadf90287bd26e1a183ac487d8a141b09b06aecb7725bbdd343640f2e` | `downloaded_plms/llama/base/` | 9,976,578,928 B + 3,500,297,344 B; **dir total 13,479,286,454 B (13.48 GB)** | 5–15 min | **Y** |
| **Official ABR LoRA (r=128)** | Google Drive id `17UyXJ9rGc0wKUkAhQ4wMrYDEbRPRjil0` (upstream ABR README = `scripts/prepare_models.py:16`) | zip `try_llama2_7b.zip` →<br>`adapter_model.bin`<br>`modules_except_plm.bin`<br>`adapter_config.json`<br>`README.md` | zip `27b3b72bc897086980bcce83ffec74ad6671f4c98b19aefcf7e225e34f7596ef`<br>`f0f6f5dbe025d404a1b5ea79c9709357520c1f5c4bb728fcaec403f7cda9dad8`<br>`a66930dd60d02f66fd30ddab41acf3752548b3e12517ef49c74b775127c92323`<br>`9b602d0dea7d6f505f3413dff50b931aa28e3909b007293eb9ff533b233c2fd5`<br>`2387c18fc7ef2dc1defb4b3621d72b13fddbcc675f939b5b0807cce6bd6cabd1` | **`downloaded_plms/ft_plms/try_llama2_7b/`** ← this is the path every experiment used (`--model-dir ../downloaded_plms/ft_plms/try_llama2_7b`), **not** the README's `adaptive_bitrate_streaming/data/ft_plms/`. See §3. | zip 288,470,767 B; unpacked 268,481,162 + 43,059,402 + 543 + 6,161 B | 1–3 min | **Y** |
| **ABR `exp_pool.pkl`** | in this repo (tracked) | `exp_pool.pkl` | `4e558aedc451a2e492d35e0218d8a8732cc1140528d9ca1f6f7326e2c871b493` | `adaptive_bitrate_streaming/artifacts/exp_pools/exp_pool.pkl` | 4,782,488 B (19,928 transitions / 424 episodes) | arrives with `git clone` | **N** |
| **fcc-test traces** | in this repo (tracked); identical to upstream NetLLM | 100 trace files + `mahimahi_ptrs.pkl` (**101 files**) | manifest `b3df2e74b065cb52f5eb1dc82d61a96fedee6b5f003844b9c8c72dfcfd3e7146`\* | `adaptive_bitrate_streaming/data/traces/test/fcc-test/` | 205,345 B | arrives with `git clone` | **N** |
| **video1 chunk sizes** | in this repo (tracked); identical to upstream NetLLM | `video_size_0` … `video_size_5` (**6 files**) | manifest `650c8000b5d65b8cb4e55d59c0a38164acd42a2c0746c12472c438ee7bfc8c78`\* | `adaptive_bitrate_streaming/data/videos/video1_sizes/` | 2,162 B | arrives with `git clone` | **N** |
| **Repo code + `abr_spec/` + `docs/soyun/` + `results/soyun/**/*.{json,csv,md}`** | `git clone` + `git checkout soyun/spec-abr` | — | — | repo root | — | < 1 min | **Y** (then `bash abr_spec/hooks/install.sh`) |
| **Python venv** | `abr_spec/requirements-soyun.txt` | — | — | `.venv/` | ~25 MB of wheels | 1–2 min | **Y** |
| **`decisions.jsonl` raw traces** | produced by runs; **gitignored** | 13 files, 65.9 MB | see `results/soyun/derived/*_summary.json` → `source.sha256` | `results/soyun/*/*/decisions.jsonl` | 65.9 MB | — | **N** — distilled into `results/soyun/derived/` (tracked, 107 KB). Raw files are gone with the instance. |
| stale **VP `try_llama2_7b.zip`** | — | 77 MB, sha `57062c71…` | — | — | — | — | **N — do NOT fetch.** Viewport checkpoint (`task_head` out=3, r=32). It was pre-staged on the *old* instance and misled the first investigation. Upstream's ABR link serves the 288 MB r=128 file above. |

\* multi-file assets are pinned by a **manifest hash**: sha256 over the sorted
`"<filename>  <sha256>\n"` listing. Recompute with:

```bash
python - <<'EOF'
import hashlib, pathlib
for d in ("adaptive_bitrate_streaming/data/traces/test/fcc-test",
          "adaptive_bitrate_streaming/data/videos/video1_sizes"):
    fs = sorted(p for p in pathlib.Path(d).glob("*") if p.is_file())
    man = "".join(f"{p.name}  {hashlib.sha256(p.read_bytes()).hexdigest()}\n" for p in fs)
    print(d, len(fs), sum(p.stat().st_size for p in fs),
          hashlib.sha256(man.encode()).hexdigest())
EOF
```

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

**Restore on the new server.** Place it at
`downloaded_plms/ft_plms/try_llama2_7b/` — **not** the README's
`adaptive_bitrate_streaming/data/ft_plms/`. Every BASELINE6 / SWEEP_SPEC /
ablation command passes `--model-dir ../downloaded_plms/ft_plms/try_llama2_7b`,
that path is soyun-writable and gitignored, and it keeps generated weights out
of the upstream tree.

```bash
.venv/bin/python -m gdown "https://drive.google.com/uc?id=17UyXJ9rGc0wKUkAhQ4wMrYDEbRPRjil0" -O /tmp/abr.zip
mkdir -p downloaded_plms/ft_plms/try_llama2_7b
cd downloaded_plms/ft_plms/try_llama2_7b && unzip -j /tmp/abr.zip && cd -

# ⚠ MANDATORY — never trust the checkpoint on filename presence alone:
.venv/bin/python abr_spec/validate_ckpt.py downloaded_plms/ft_plms/try_llama2_7b
# expect exactly:  VERDICT: ABR 호환 확인   (exit 0)
# anything else (e.g. "VP 재확인") means a wrong/stale checkpoint -> delete the
# dir and re-fetch. Do NOT start a run until this prints ABR 호환 확인.

# verify the bytes against the pinned hashes:
sha256sum downloaded_plms/ft_plms/try_llama2_7b/*.bin
#   adapter_model.bin        f0f6f5dbe025d404a1b5ea79c9709357520c1f5c4bb728fcaec403f7cda9dad8
#   modules_except_plm.bin   a66930dd60d02f66fd30ddab41acf3752548b3e12517ef49c74b775127c92323
```

`python scripts/prepare_models.py` fetches the same Drive id but drops it in the
README path; if you use it, move the directory afterwards **and still run
`validate_ckpt.py`**.

**⚠ GOTCHA — the download can be silently skipped.**
`scripts/prepare_models.py::checkpoint_ready()` decides the checkpoint is
already present by **filename existence alone** — it checks that
`data/ft_plms/try_llama2_7b/` contains `adapter_config.json` +
`adapter_model.bin` + `modules_except_plm.bin`, with **no rank, shape or hash
check**. A stale or wrong checkpoint therefore wins silently. That is exactly
what cost the first investigation: the old instance had a *viewport* checkpoint
(77 MB, r=32, `task_head` out=3) pre-staged there, and the tooling happily used
it, producing the false "the official checkpoint is incompatible, we must
retrain" conclusion ([[CHECKPOINT_RECOVERY]]).

**Therefore:** delete any pre-existing `try_llama2_7b/` before fetching, and
**always** finish with `abr_spec/validate_ckpt.py`, which checks rank, the
12-module / 33-tensor `modules_except_plm` structure, `action_head (6,4096)`,
tensor finiteness and a strict `load_state_dict` simulation. Filename presence
proves nothing. Reported upstream as a cosmetic issue in
[[NEEDS_UPSTREAM]] #1+#2.

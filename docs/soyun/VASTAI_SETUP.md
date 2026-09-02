# VASTAI_SETUP — bring up a fresh instance for the ABR speculative work

**soyun / speculative inference · updated 2026-09-02**

Ordered so the cheap, high-yield checks happen **before** the 13 GB download.
Two instances have already been thrown away for reasons this file now catches.
Companion: [[ASSETS]] (what to fetch, with hashes) · [[HANDOFF]] (what to do next).

Total: ~25 min, of which ~15 is the Llama download.

---

## Step 0 — choosing the instance (before you rent)

| Check | Why |
|---|---|
| **GPU ≥ 24 GB** | Llama-2-7B fp16 + runtime overhead. fp32 (~26 GB) does **not** fit in 24 GB, so a card that cannot do fp16 is useless here, not merely slow. |
| **Host disk free — look at the host's own free space, not just the container's** | An instance whose *host* was nearly full failed to pull the docker image at all: the container never came up and the rental was wasted. Vast shows host disk on the offer; leave headroom for the image plus ~20 GB of weights. |
| **Container disk ≥ 60 GB** | 13.5 GB weights + 0.3 GB checkpoint + image + ~1 GB of run outputs. 100 GB is comfortable. |
| **Driver ≥ 550 if you can pick** | See Step 1 — driver 535.154.05 on an RTX 3090 had a broken fp16 datapath. 595.58.03 on the same card model was fine. |

### Hosts to avoid

| Host | Symptom |
|---|---|
| **`host:102082`** | RTX 3090, driver 535.154.05 — **fp16/bf16 defect**: every cuda fp16 tensor comes back all-NaN, fp32 fine. Wasted a full session. |
| **`host:74292`** | **Host disk full** — docker image pull failed, instance never usable. |

---

## Step 1 — the fp16 check, immediately on first SSH, before anything else

Do this **before** cloning, installing, or downloading 13 GB. It costs ~20
seconds and it is the single check that would have saved a whole session.

```bash
python -c "
import torch
print('torch', torch.__version__, '| cuda', torch.version.cuda,
      '| device', torch.cuda.get_device_name(0),
      '| cap', torch.cuda.get_device_capability(0))
for dt in (torch.float16, torch.bfloat16, torch.float32):
    x = torch.randn(4096, 4096, dtype=dt)
    g = x.cuda()
    ok_finite = bool(torch.isfinite(g).all().item())
    ok_round  = bool(torch.allclose(g.cpu(), x, atol=0, rtol=0))
    mm = g @ g
    print(f'{str(dt):20s} finite={ok_finite} roundtrip={ok_round} '
          f'matmul_finite={bool(torch.isfinite(mm).all().item())}')
"
```

**Every `finite` and every `matmul_finite` must be `True` for float16.** If
float16 prints `finite=False` while float32 prints `True`, the card's fp16
datapath is broken — **destroy the instance and rent another one.** Do not try to
work around it; fp32 7B does not fit in 24 GB.

After the repo is cloned, the same check with more coverage (including reading
the real Llama embedding weights) is `abr_spec/gpu_fp16_diagnostic.py` — run it
again at the end of Step 5.

```bash
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
df -h /                      # container disk
```

---

## Step 2 — clone, and install the hook

```bash
cd /root
git clone https://github.com/soyuniverse/NetLLM_abr.git
cd NetLLM_abr
git checkout soyun/spec-abr

bash abr_spec/hooks/install.sh          # ← MANDATORY, see below
```

**`.git/hooks/` is not tracked by git.** A fresh clone therefore has **no**
write-scope guard, and it is easy to commit into a teammate's module by accident.
`abr_spec/hooks/pre-commit` is the tracked source of truth; `install.sh` copies
it into `.git/hooks/`, chmods it, and prints a verification. Do it before the
first commit, every clone, no exceptions.

Verify: `cmp abr_spec/hooks/pre-commit .git/hooks/pre-commit && echo "hook OK"`

---

## Step 3 — venv

```bash
cd /root/NetLLM_abr
python -m venv .venv --system-site-packages
.venv/bin/pip install -U pip
.venv/bin/pip install -r abr_spec/requirements-soyun.txt
.venv/bin/pip install pytest            # if the base env lacks it
```

`--system-site-packages` is deliberate: torch comes from the base conda env
(driver-matched, ~2.5 GB) and is **not** reinstalled into the venv.

**Always invoke `.venv/bin/python`**, or `source .venv/bin/activate` at the start
of the session. A bare `python` is the base conda env with numpy 1.26, which the
NetLLM code path does not expect (the venv shadows it with 1.24.4). Every
command in [[HANDOFF]] and every `run_*.sh` already uses `.venv/bin/python`; the
trap is interactive one-liners.

CPU-only sanity, no GPU needed — **40 tests must pass**:

```bash
CUDA_VISIBLE_DEVICES="" .venv/bin/python -m pytest \
  adaptive_bitrate_streaming/tests/test_mpc_draft.py \
  adaptive_bitrate_streaming/tests/test_speculative_acceptance.py \
  abr_spec/tests/test_drafters.py -q
```

---

## Step 4 — Llama-2-7B base (~13.5 GB, 5–15 min)

```bash
huggingface-cli login          # Meta licence must already be accepted on the account

mkdir -p /root/NetLLM_abr/downloaded_plms/llama
huggingface-cli download meta-llama/Llama-2-7b-hf \
  --local-dir /root/NetLLM_abr/downloaded_plms/llama/base \
  --local-dir-use-symlinks False
```

**⚠ Always write `--local-dir` out in full, as a literal path.** A previous
session used a shell variable that was empty, so `huggingface-cli` unpacked the
whole 13 GB model **into the repository root** — it scattered `config.json`,
`README.md`, `LICENSE.txt` and the shards over the working tree and overwrote the
repo's own files, and cleaning it up cost more than the download. Never let that
flag come from an unquoted or possibly-unset variable.

Verify placement and size:

```bash
ls -la downloaded_plms/llama/base/            # 2 shards + index + tokenizer set
du -sb downloaded_plms/llama/base             # expect 13,479,286,454 B
git status --porcelain | head                 # MUST be empty; if the repo root
                                              # is dirty, the download went wrong
```
Hashes for the individual files are in [[ASSETS]] §0.

---

## Step 5 — official ABR LoRA checkpoint (~288 MB, 1–3 min)

```bash
cd /root/NetLLM_abr
.venv/bin/python -m gdown \
  "https://drive.google.com/uc?id=17UyXJ9rGc0wKUkAhQ4wMrYDEbRPRjil0" -O /tmp/abr.zip
mkdir -p downloaded_plms/ft_plms/try_llama2_7b
cd downloaded_plms/ft_plms/try_llama2_7b && unzip -j /tmp/abr.zip && cd -

# ⚠ MANDATORY judgement — filename presence proves nothing:
.venv/bin/python abr_spec/validate_ckpt.py downloaded_plms/ft_plms/try_llama2_7b
# expect exactly:  VERDICT: ABR 호환 확인   (exit 0)
```

If it says anything else, you have the wrong checkpoint — delete the directory
and re-fetch. `scripts/prepare_models.py::checkpoint_ready()` decides "already
downloaded" from **filenames alone**, with no rank or shape check, so a stale
directory silently wins; that is exactly how a *viewport* checkpoint (r=32,
head=3) once produced a false "we must retrain" conclusion. Details in
[[ASSETS]] §3 and [[CHECKPOINT_RECOVERY]].

Note the path: `downloaded_plms/ft_plms/`, **not** the README's
`adaptive_bitrate_streaming/data/ft_plms/`. Every frozen run command passes
`--model-dir ../downloaded_plms/ft_plms/try_llama2_7b`.

Now re-run the full fp16 gate, which also reads the real Llama weights:

```bash
.venv/bin/python abr_spec/gpu_fp16_diagnostic.py   # every 'finite' must be True
```

---

## Step 6 — smoke, then the real work

```bash
cd /root/NetLLM_abr
.venv/bin/python abr_spec/run_wrapped.py \
  --run-id smoke_$(date +%Y%m%d) --phase spec_k3 --ckpt-name official_abr_r128 \
  --decision-trace -- \
  --test --fp16 --seed 1 --plm-type llama --plm-size base --rank 128 \
  --plm-dir ../downloaded_plms/llama/base \
  --model-dir ../downloaded_plms/ft_plms/try_llama2_7b \
  --trace fcc-test --trace-num 2 --video video1 --fixed-order \
  --device cuda:0 --device-out cuda:0 \
  --temporal-selector none --token-selector none \
  --speculative-draft-steps 3 --speculative-verification-mode sample
```
~10 s of GPU. `status=ok` and a non-zero `queued_actions_served` mean the whole
path works. Then go to [[HANDOFF]] §3 Action 1.

---

## Checklist

```
[ ] Step 0  GPU >= 24 GB, host disk has headroom, container disk >= 60 GB
[ ] Step 0  host is NOT host:102082 (fp16 defect) or host:74292 (host disk full)
[ ] Step 1  inline fp16 check on first SSH -- float16 finite == True
            (if False while float32 is True -> destroy the instance, rent another)
[ ] Step 2  git clone + git checkout soyun/spec-abr
[ ] Step 2  bash abr_spec/hooks/install.sh   (hooks are NOT tracked by git)
[ ] Step 2  cmp abr_spec/hooks/pre-commit .git/hooks/pre-commit
[ ] Step 3  python -m venv .venv --system-site-packages
[ ] Step 3  .venv/bin/pip install -r abr_spec/requirements-soyun.txt
[ ] Step 3  habit: always .venv/bin/python, never a bare python
[ ] Step 3  pytest -> 40 passed (CPU only)
[ ] Step 4  huggingface-cli download ... --local-dir <FULL LITERAL PATH>
[ ] Step 4  du -sb downloaded_plms/llama/base == 13,479,286,454
[ ] Step 4  git status --porcelain is EMPTY (nothing unpacked into the repo root)
[ ] Step 5  gdown checkpoint -> downloaded_plms/ft_plms/try_llama2_7b/
[ ] Step 5  validate_ckpt.py prints "VERDICT: ABR 호환 확인"
[ ] Step 5  gpu_fp16_diagnostic.py -- every 'finite' True
[ ] Step 6  2-trace smoke: status=ok, queued_actions_served > 0
[ ] ->      HANDOFF section 3, Action 1: run the drafter ablation
```

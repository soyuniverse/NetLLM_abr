# smoke_ckpt_1ep_20260831 — 1-epoch pipeline check (FAILED, infra)

Full analysis: [`docs/soyun/PLUMBING_SMOKE.md`](../../../docs/soyun/PLUMBING_SMOKE.md).
This folder is the run record. `.log` files here are git-ignored (results/soyun
tracks only `*.json` / `*.csv` / `*.md`), so their content is reproduced below.

## Files
| file | tracked | what |
|---|---|---|
| `manifest.json` | ✅ | pre-run manifest (git hash, expanded argv, seed, versions, GPU) + per-phase `result` |
| `adapt/manifest_phase.json` | ✅ | this phase's manifest slice |
| `adapt/result.json` | ✅ | status=error, wall 19.4 s, timing, collected files |
| `adapt/console.log` | ❌ (.log) | full stdout/stderr — tail below |
| `gpu_fp16_diagnostic.log` | ❌ (.log) | GPU fp16 probe output — below |

Reproduce the diagnostic: `.venv/bin/python abr_spec/gpu_fp16_diagnostic.py`

## adapt/console.log — crash tail
```
run_plm.py:520 run() -> adapt() -> trainer.train_epoch()
trainer.py:301 train_step -> trainer.py:474 self.model(states, actions, returns, timesteps)
rl_policy.py:371 forward -> _run_plm -> rl_policy.py:299 _require_finite(hidden,'plm_hidden')
plm_special.models.rl_policy.NonFiniteInferenceError: non-finite ABR inference tensor at plm_hidden:
  {'stage': 'plm_hidden', 'dtype': 'torch.float32', 'shape': [1, 160, 4096],
   'finite_elements': 0, 'total_elements': 655360, 'finite_absmax': None,
   'adalora_overflow_candidates': []}
```
Before the crash: `exp_pool.pkl` loaded, Llama-2-7b 2 shards loaded (~17 s),
pad token added (32000→32001). Crash on the **first** training forward.

## gpu_fp16_diagnostic.log
```
torch 2.2.0 cuda 12.1 gpu NVIDIA GeForce RTX 3090 cap (8, 6)   driver 535.154.05
torch.float32      cpu->cuda finite=True   roundtrip_match=True
torch.float16      cpu->cuda finite=False  roundtrip_match=False
torch.bfloat16     cpu->cuda finite=False  roundtrip_match=False
fp16 matmul on cuda            finite: False
fp32->fp16 cast on cuda        finite: False
Llama embed weight on CPU      finite: True
Llama embed weight on CUDA     finite: False
```
=> GPU fp16/bf16 datapath is broken. fp32 works but 7B fp32 (~26 GB) > 24 GB.
Infra blocker, not code. Replace the instance; re-run per
[`docs/soyun/HANDOFF.md`](../../../docs/soyun/HANDOFF.md).

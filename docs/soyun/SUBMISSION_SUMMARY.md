# SUBMISSION_SUMMARY — speculative inference for NetLLM ABR

**soyun · branch `soyun/spec-abr` · 2026-09-10 · single entry point for combining
this work with your own LoRA.**

Everything here is committed and reproducible. Deeper detail:
[[DRAFTER_ABLATION]] (the ablation, §9.13 = the 4-seed confirmation),
[[RNG_CONTAMINATION_AUDIT]] + [[TRAJECTORY_DIVERGENCE]] (the methodology finding),
[[SWEEP_SPEC]] §12 (cost model), [[HANDOFF]] (full status).

---

## 1. What this is

A **training-free** drop-in for the speculative-inference path of NetLLM ABR: a
different **drafter** (the module that proposes the next *k* bitrate decisions
for the LLM to verify in one call). NetLLM's stock drafter is Robust-MPC
(`6^k` brute-force rollout); it proposes what the LoRA policy would pick only
~13–16 % of the time, so almost every decision still costs an LLM call.
**"Repeat the last executed bitrate *k* times"** matches the policy ~88 % of the
time (the policy's action autocorrelation is ~92 %), so most decisions are served
from the verified queue with no LLM call.

Nothing in `run_plm.py` / `rl_policy.py` / `test.py` is modified — the drafter is
swapped by a monkeypatch on one construction site (`abr_spec/drafter_select.py`,
the same pattern NetLLM already uses).

## 2. Recommended configuration

**`drafter = repeat-last`, `k = 3`, no serve-time gate.**

| | 4-seed mean ± std (seeds 1–4) |
|---|---|
| LLM-call reduction `q` | **38.2 ± 0.3 %** (σ < 0.3 pp — seed-independent) |
| Latency speedup vs no-speculation A1 | **1.49 ± 0.08×** (within-instance ratio; std is cross-session latency drift, not behaviour) |
| draft/LLM 1-step agreement | 88.5 ± 0.6 % |
| ΔQoE vs same-seed A1 | **+0.4 ± 2.1 %** — not distinguishable from 0 |
| Δ total rebuffering vs same-seed A1 | **+5 ± 23 s** — inside A1's own seed spread (±12 s) |

`hybrid` (MPC when buffer < 5 s or throughput CV ≥ 0.30, else repeat-last) at
`k = 3` is **equivalent** (`q` 37.1 ± 0.3 %, speedup 1.50 ± 0.08×, ΔQoE
−0.5 ± 2.5 %) and slightly tighter on rebuffering variance — pick it if you want
a conservative fallback in low-buffer regimes.

**Do not use `k = 5`** — lower speedup, higher rebuffering (repeat-last k5
Δrebuffering +15 ± 22 s). **Do not add the serve-time buffer gate** — it was
investigated and withdrawn ([[CHANGE_REQUEST_SERVE_TIME_GATE]]): inert once
measured without the RNG confound.

### Run command

Through the provenance-stamped wrapper (recommended — records GPU, git commit,
manifest):

```bash
cd /path/to/NetLLM_abr
.venv/bin/python abr_spec/run_wrapped.py \
  --run-id my_run --phase repeat_k3 --ckpt-name <your_ckpt_dir_name> \
  --speculative-drafter repeat-last \
  -- --test --fp16 --seed 1 --plm-type llama --plm-size base --rank 128 \
     --plm-dir ../downloaded_plms/llama/base \
     --model-dir ../downloaded_plms/ft_plms/<your_lora> \
     --trace fcc-test --trace-num 100 --video video1 --fixed-order \
     --device cuda:0 --device-out cuda:0 \
     --temporal-selector none --token-selector none \
     --speculative-draft-steps 3 --speculative-verification-mode sample \
     --speculative-buffer-tolerance 1.0 --speculative-state-tolerance 0.25 \
     --speculative-return-tolerance 0.01
```

Or straight `run_plm.py` — install the drafter first, in the same process:

```python
import abr_spec.drafter_select as ds
ds.install("repeat-last")          # before run_plm builds the drafter
# ... then run run_plm.py --test ... --speculative-draft-steps 3 ...
```

Report QoE / rebuffering as **mean ± std over ≥ 3 seeds** (see §4).

## 3. The 2× option — M6 (drafter + selectors)

`repeat-last k3` **plus** NetLLM's Temporal + Token selectors
(`--temporal-selector event-aware --token-selector intra-timestep`):

| | 4-seed mean ± std |
|---|---|
| Speedup vs A1 | **2.03 ± 0.10×** |
| `q` | 37.8 ± 0.2 % |
| ΔQoE vs same-seed A1 | **−3.0 ± 1.9 %** (negative at all 4 seeds) |
| Δ total rebuffering | **+38 ± 29 s** |

M6 is the **only** ablation condition with a QoE cost that survives 4 seeds.
Take it only if a 2× LLM-call reduction is worth ~3 % QoE for your deployment.

## 4. Known constraints

| # | Constraint | Impact | Status |
|---|---|---|---|
| [[NEEDS_UPSTREAM]] #6 | `test.py` seeds the eval RNG **once** for all 100 traces (not per episode). QoE / total-rebuffering are therefore dominated by 1–4 outlier traces whose identity the seed picks — a per-run lottery (even plain A1 rebuffers 6.4 / 15.2 / 12.7 / 33.3 s across seeds 1–4). | **You must average QoE/rebuffering over ≥ 3 seeds.** Structural metrics (`q`, speedup, agreement) are unaffected. | Open. 1-line fix, owned by the eval-harness maintainer. Opt-in workaround committed: `abr_spec/reseed_per_episode.py` (`--probe reseed_per_episode`). Full write-up: [[RNG_CONTAMINATION_AUDIT]], team notice [[TEAM_ALERT_RNG_CONTAMINATION]]. |
| [[NEEDS_UPSTREAM]] #4 | `--token-selector recent-timestep` makes Llama fp16 emit an all-NaN hidden state → 1 of the README's 6 evaluation conditions (Recent-token) cannot run. | Does not affect the recommended config or M6 (neither uses `recent-timestep`). | Open, not soyun's. |
| [[NEEDS_UPSTREAM]] #5 | `--speculative-draft-steps` is capped at 5 in read-only `run_plm.py`. | `k = 8` untested — but k=5 is already worse than k=3, so low priority. | Open, low priority. |
| Instance / latency | Absolute latency is not comparable across GPUs/drivers/sessions (~10 % drift). Every speedup here is a **within-instance ratio** vs a same-instance no-speculation A1. `q` (call-reduction) is the portable number. | Re-measure A1 on your instance to get an absolute speedup; expect `q ≈ 38 %` regardless. | Inherent. |

## 5. Reference documents

- [[DRAFTER_ABLATION]] — the ablation; §9.13 = 4-seed confirmation table; §S = queue-safety metric.
- [[RNG_CONTAMINATION_AUDIT]] — per-campaign exposure table + the drafter self-check (§3).
- [[TRAJECTORY_DIVERGENCE]] — how one mid-run intervention contaminates 45/100 traces.
- [[TEAM_ALERT_RNG_CONTAMINATION]] — team-facing, with a 3-point self-diagnosis checklist.
- [[PAPER_ASSETS_ABR]] — claim→evidence map, LaTeX tables, gap list.
- [[SWEEP_SPEC]] §12 — the q→speedup cost model.
- [[CHANGE_REQUEST_SERVE_TIME_GATE]] — the serve gate, **withdrawn** (why not to use it).
- [[HANDOFF]] — full project status, freeze commits, scratchpad map.
- Figures: `results/soyun/figures/` (fig1 = QoE/speedup 4-seed, fig4 = rebuffering cost 4-seed; `archive/` = superseded seed-1 versions). `README.md` + `make_figures.py` are the tracked record.
- Data: `results/soyun/drafter_ab_20260908/` (seed 1, freeze `0d137ce`), `results/soyun/drafter_seed_sweep_20260910/` (seeds 2–4, same exec path).

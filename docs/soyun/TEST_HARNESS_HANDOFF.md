# TEST_HARNESS_HANDOFF — the eval RNG seeding fix for `test.py`

**soyun · branch `soyun/spec-abr` · 2026-09-10.**
If you searched for "test", "test.py", "seed", or "RNG" — this is the file.

Related: [[NEEDS_UPSTREAM]] #6 (the upstream ask), [[RNG_CONTAMINATION_AUDIT]]
(full analysis), [[TRAJECTORY_DIVERGENCE]] (the mechanism), [[TEAM_ALERT_RNG_CONTAMINATION]]
(team notice), [[SUBMISSION_SUMMARY]] (how to run the drafter).

---

## 1. The problem, in plain terms

`adaptive_bitrate_streaming/plm_special/test.py` runs your model over 100 network
traces, one after another, and averages the result. It sets the random seed
**once**, before the first trace — and never resets it between traces. The action
sampler (used whenever decoding is stochastic, which is the default) keeps
drawing from that one shared random sequence for all 100 traces.

Consequence: if a change you're testing makes trace #5 use a *different number*
of random draws than the baseline does (a fallback instead of a cached decision,
an extra sampled head, a different drafter), then trace #6 and every trace after
it land at a different point in the random sequence and make different
decisions — **not because your change reached those traces, but because the
shared randomness slid forward**. Your A/B "difference" is then partly real
effect and partly this slide. It does not average out with more traces.

It also makes the **plain baseline** unstable across seeds: with nothing changed
but `--seed`, the no-speculation model rebuffers **6.4 / 15.2 / 12.7 / 33.3 s**
at seeds 1/2/3/4 — one or two unlucky traces per run carry the whole number, and
which traces are unlucky is decided by the seed.

### The one measurement that shows it

A serve-time rule fired on exactly **3 decisions**, in two variants. Both
variants served the **same bitrate** on those 3 decisions and left those 3 chunks
with **zero rebuffering**. The 100-trace total came out **7.0 s** for one variant
and **1.6 s** for the other — a 4× difference produced entirely by downstream
traces reacting to the shifted random sequence (27 % of decisions changed across
45 of the 100 traces). Re-run with the RNG reset per trace, the same rule changes
**1 decision** and moves the total by **0 s**. ([[TRAJECTORY_DIVERGENCE]] §2, §6.)

**What is NOT affected:** structural metrics — LLM-call reduction `q`, latency
speedup, draft/LLM agreement. These are averaged over 4,700 decisions, don't
depend on *which* action is sampled, and were re-confirmed identical across 4
seeds ([[DRAFTER_ABLATION]] §9.13). Only the outlier-driven metrics
(rebuffering, QoE) are at risk.

## 2. Two ways to fix it

Both use the identical scheme — trace *k* starts from `args.seed + k` — so they
produce the same per-trace seeding. Pick by how long you'll be in this codebase.

| | **Option A — patch `test.py`** | **Option B — opt-in overlay** |
|---|---|---|
| What | `docs/soyun/patches/test_py_per_episode_reseed.patch` — moves the seed call into the trace loop | `abr_spec/reseed_per_episode.py` — monkeypatch installed per run via `--probe` |
| Touches team files | **Yes** (`test.py`); needs to be reviewed / merged by the eval-harness owner | **No**; nothing to merge |
| Scope | every run in this checkout, permanently | one run at a time, only when you pass the flag |
| Determinism battery | still **passes** (`run_determinism_check.sh` checks run-to-run *self-consistency* at a fixed seed, which the patch keeps). What changes: the committed campaign results (`drafter_ab_20260908/` etc.) are no longer bit-reproducible — a different seed sequence — so any before/after comparison must be re-run. The 40 unit tests are unaffected. | unaffected — you opt in per run |
| Apply | `git apply docs/soyun/patches/test_py_per_episode_reseed.patch` | add `--probe reseed_per_episode` to your `abr_spec/run_wrapped.py` command |
| Validated | `git apply --check` OK, `patch -p1 --dry-run` OK, post-patch `ast.parse` OK (2026-09-10, HEAD `08d56f5`) | in use since 2026-09-09 (`rng_audit_20260909/`) |

### Option A — apply command

```bash
cd /path/to/NetLLM_abr
git apply docs/soyun/patches/test_py_per_episode_reseed.patch
# sanity checks:
CUDA_VISIBLE_DEVICES="" .venv/bin/python -m pytest -q \
  adaptive_bitrate_streaming/tests/test_mpc_draft.py \
  adaptive_bitrate_streaming/tests/test_speculative_acceptance.py \
  abr_spec/tests/test_drafters.py               # 40/40, unchanged by the patch
bash abr_spec/run_determinism_check.sh          # still passes (a==b at fixed seed)
# NOTE: committed campaign results (drafter_ab_20260908/, etc.) used the old
# seeding -- re-run any A/B you need to compare against them.
```

### Option B — run command

```bash
.venv/bin/python abr_spec/run_wrapped.py \
  --run-id reseed_check --phase myrun --ckpt-name <your_ckpt_dir> \
  --probe reseed_per_episode \
  -- --test --fp16 --seed 1 --plm-type llama --plm-size base --rank 128 \
     --plm-dir ../downloaded_plms/llama/base \
     --model-dir ../downloaded_plms/ft_plms/<your_lora> \
     --trace fcc-test --trace-num 100 --video video1 --fixed-order \
     --device cuda:0 --device-out cuda:0 \
     --temporal-selector none --token-selector none \
     --speculative-draft-steps 3 --speculative-verification-mode sample
```

Check `results/soyun/reseed_check/myrun/reseed_per_episode.json` shows
`"reseeds": 100`.

## 3. Which one for you

| Your situation | Use |
|---|---|
| "I just want to verify my result once / sanity-check one A/B." | **Option B.** Run your comparison twice (with and without the probe); if the conclusion holds, contamination wasn't driving it. |
| "I'll keep running experiments in this environment (more drafters, more seeds, my own LoRA)." | **Option A.** Apply the patch once, re-baseline the determinism check, and every run after that is clean. |
| "I'm handing this to someone else / to CI." | **Option A**, and get the eval-harness owner to merge it upstream ([[NEEDS_UPSTREAM]] #6) so it's not a local diff. |

## 4. Regardless of which you use

**Report QoE and total rebuffering as mean ± std over ≥ 3 seeds.** Reseeding
makes each trace independent, but a single seed is still one draw of the
per-trace outcomes, and those outcomes are outlier-dominated. Structural metrics
(`q`, speedup, agreement) are fine at one seed. See [[SUBMISSION_SUMMARY]] §2 for
the recommended drafter config and its 4-seed numbers.

## 5. This is probably not just a speculative-inference problem

The same failure mode applies to any evaluation change that (a) alters the
policy's decisions or model-call count mid-run, (b) does so a different number of
times per trace between two conditions, and (c) is compared as a many-trace
average — e.g. an AdaLoRA rank schedule that changes compute per step, or a
patch-selection rule that fires conditionally. If that sounds like your module,
run the [[TEAM_ALERT_RNG_CONTAMINATION]] §2 checklist before trusting a
rebuffering / QoE delta.

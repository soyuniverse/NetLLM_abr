# TEAM ALERT — the evaluation RNG is seeded once for all 100 traces

**From:** soyun (speculative inference) · **Branch:** `soyun/spec-abr` · **Date:** 2026-09-10
**For:** 수현, 하영 — anyone running `test.py` / `run_plm.py --test` evaluations
**Read time:** 3 min · **Action needed:** check the §2 checklist against your own experiment
**Detail:** [[TRAJECTORY_DIVERGENCE]], [[RNG_CONTAMINATION_AUDIT]], [[NEEDS_UPSTREAM]] #6

> **Don't over-react.** I hit this in my own speculative-inference work and
> checked what it touched: the **headline result (the speedup / call-reduction
> numbers) was completely safe** — it survived a clean re-measurement unchanged.
> Only the **rebuffering / QoE cost numbers** needed re-running, because those
> are dominated by one or two outlier traces and were never measurable from a
> single seed. So the response is not "throw the campaign away" — it's "run the
> §2 checklist, and if you're in the risk group, re-measure the *outlier-driven*
> metrics with §4. Structural / count / latency metrics are almost certainly fine."

---

## 1. The problem, one paragraph

`plm_special/test.py` seeds Python's `random` / `numpy` / `torch` **once**, right
before the loop over the 100 evaluation traces. It never re-seeds between traces
(`clear_dq()` at the episode boundary resets the model deques but not the RNG).
So the stochastic action sampler (`rl_policy._sample → random.choices`, active
whenever verification/decoding is `sample`, which is the default) draws from
**one continuous random stream shared by all 100 traces**. If your change makes
trace *k* consume a different *number* of random draws than the baseline does,
then trace *k+1* and every trace after it sees a **shifted** stream and makes
different decisions — not because your change reached those traces, but because
the shared RNG moved. A/B differences measured as a 100-trace average then mix
your real effect with this stream-shift noise, and the noise does not shrink with
more traces.

## 2. Self-diagnosis — does this affect your experiment?

You are **at risk** if all three are true:

- **(a)** Your change alters the policy's state, decisions, or the number of
  model calls *during* evaluation — e.g. a serve-time gate, a different drafter,
  an early-exit, a caching layer, a fallback rule, an extra sampled head.
- **(b)** That alteration happens a **different number of times, or at different
  points, per trace** between your A and B conditions (so the cumulative
  random-draw count diverges as the run progresses).
- **(c)** You compare A vs B as an **average / sum over many traces** — QoE,
  total rebuffering, mean accuracy — rather than a strict per-trace paired diff
  under identical seeding.

You are **safe** if any one of these holds:

- Decoding is **greedy / argmax** everywhere (no `random` draws in the decision
  path). Deterministic-decode evals are unaffected.
- A and B consume the **same number of RNG draws per trace** (e.g. two
  non-speculative conditions: both draw exactly once per chunk, so the streams
  stay aligned trace-for-trace).
- Your metric is **not outlier-dominated** and your effect is large relative to
  the ~1–2 σ seed swing. (Latency / speedup are essentially RNG-insensitive.)
- You already **re-seed per trace** or run each trace as its own process.

## 3. The evidence

- **Same seed, same served action, 4× different result.** A serve-time gate
  fired on 3 decisions, each serving the identical action the baseline would have
  served at that step, each leaving those 3 chunks with zero rebuffering — yet
  the 100-trace total was 7.0 s (one gate variant) vs 1.6 s (another) vs 18.5 s
  (no gate). The entire spread is downstream traces reacting to the shifted RNG
  stream: a **27 % sustained action-mismatch across 45 of the 100 traces** for
  the worse variant (fig6, [[TRAJECTORY_DIVERGENCE]] §2).
- **De-contaminated, the effect is zero.** Re-running the same A/B with the RNG
  re-seeded per trace: the gate changes **1 decision** and moves total
  rebuffering by **0.0 s** ([[TRAJECTORY_DIVERGENCE]] §6). The seed-once result
  was an artefact.
- **The baseline itself is a lottery.** With nothing changed but `--seed`, the
  plain no-speculation model (A1) rebuffers **6.4 / 15.2 / 12.7 / 33.3 s** at
  seeds 1/2/3/4 — 1–4 traces out of 100 carry the whole total each time
  ([[DRAFTER_ABLATION]] §9.13). Any A/B whose "cost" is smaller than this ~12 s
  spread is measuring the seed, not the change.

## 4. What you can do right now (no pipeline change)

An opt-in diagnostic is committed: **`abr_spec/reseed_per_episode.py`**.

```bash
.venv/bin/python abr_spec/run_wrapped.py \
  --run-id <id> --phase <name> --ckpt-name <ckpt> \
  --probe reseed_per_episode \
  -- <your normal run_plm.py args>
```

It monkeypatches `test.set_random_seed` + `OfflineRLPolicy.clear_dq` to re-seed
with `seed + trace_index` at every episode boundary, so each trace is
independent and an A/B becomes a true paired per-trace comparison. It writes
`reseed_per_episode.json` (`{"reseeds": 100}`) to prove it ran.

**Do not wire it into the default pipeline.** The 40/40 determinism battery and
every committed result assume the current seed-once behaviour; a reseed run is
labelled in its manifest and is not comparable to a non-reseed run. It is a
diagnostic overlay, not a fix.

**The actual fix is one line in `test.py`** — re-seed inside the trace loop
(after `clear_dq()`), or give each episode its own `random.Random(seed + ep)`.
Filed as [[NEEDS_UPSTREAM]] #6. This is an eval-harness decision, not something
`abr_spec/` should own, because it changes every existing result's exact numbers
(directionally they should be unchanged — it removes noise, not signal).

## 5. What is / isn't affected in soyun's own work (worked example)

Full table in [[RNG_CONTAMINATION_AUDIT]]. Summary:

| Result | Affected? | Why |
|---|---|---|
| "Parameters cannot reach latency parity" (SWEEP_SPEC exclusion result) | **No** | the verdict is carried by `q` and latency, both RNG-insensitive; the QoE column is a seed-1 point but the sign (≈parity) is not in question |
| "repeat-last / hybrid drafter clears speedup 1.0× and 1.24×" (the headline) | **No — held, and re-confirmed** | speedup and `q` don't depend on which action is sampled. 4-seed: repeat-last k3 speedup **1.49 ± 0.08×**, q **38.2 ± 0.3 %** (σ < 0.3 pp) ([[DRAFTER_ABLATION]] §9.13) |
| "…at a QoE / rebuffering cost (was: 'conditional success', 2.9–5.8× A1)" | **Yes — was a seed-1 artifact; re-measured** | 4-seed: repeat-last k3 ΔQoE **+0.4 ± 2.1 %**, Δrebuffering **+5 ± 23 s** vs same-seed A1 — not distinguishable from 0. The A1 baseline's own rebuffering is 16.9 ± 11.6 s. One exception: **M6 (drafter + selectors) ΔQoE −3.0 ± 1.9 %** is a real cost |
| Serve-time buffer gate "4/4 config" | **Yes — withdrawn** | pure contamination artefact (reseed → gate changes 1 decision, 0 s effect); [[CHANGE_REQUEST_SERVE_TIME_GATE]] withdrawn |
| BASELINE6 six-condition speedups | **No** | non-speculative conditions draw a fixed 1×/chunk; streams stay aligned |
| 40/40 determinism battery | **No** | same seed both runs → byte-identical stream |

# RECON — Speculative inference (soyun)

Read-only investigation of the team lead's speculative implementation.
No behavior was changed. All line references are against the tree at branch
`soyun/spec-abr` (HEAD `3cf7f40`).

Scope read:
- `adaptive_bitrate_streaming/plm_special/speculative/` (all files)
- `adaptive_bitrate_streaming/plm_special/models/rl_policy.py` (speculative touchpoints only)
- `adaptive_bitrate_streaming/run_plm.py` (argparse + wiring)
- `adaptive_bitrate_streaming/plm_special/test.py` (eval loop + metrics, for F)

---

## A. `speculative/` file inventory

| File | Role (one line) |
|---|---|
| `__init__.py` | Re-exports `MPCDraftRollout`, `RobustMPCDraftGenerator`, `AcceptancePlan`, `ObservationValidation`, `build_acceptance_plan`, `validate_speculative_observation`. (`speculative/__init__.py:1-16`) |
| `mpc_draft.py` | Dependency-free Robust-MPC rollout. `RobustMPCDraftGenerator` forecasts throughput (harmonic mean / (1+max error)), brute-forces the best valid k-step bitrate sequence, and simulates the state/buffer/return trajectory. Returns `MPCDraftRollout`. No torch, no LLM. (`mpc_draft.py:1-268`) |
| `acceptance.py` | Pure helpers: `build_acceptance_plan` (prefix match + 1 correction), `validate_speculative_observation` (buffer/state/return tolerance check for queue reuse), plus `buffer_deviation_seconds`. No torch model calls. (`acceptance.py:1-124`) |

The heavy lifting (embedding draft blocks, running the PLM, filling/serving the
queue) lives in `rl_policy.py`, **not** in `speculative/`. `speculative/` is
purely the MPC math + acceptance predicates.

---

## B. Draft path

**Where:** `RobustMPCDraftGenerator.generate()` (`mpc_draft.py:175-268`), invoked
from `OfflineRLPolicy.draft_and_verify()` (`rl_policy.py:806-836`) →
`sample_speculative()` (`rl_policy.py:936-947`).

**Inputs the rollout drafts from** (`generate` signature `mpc_draft.py:175-186`):
- `state` — the `[6,6]` NetLLM state matrix. Row 2 (`state[2, -5:]`) = last 5
  throughput samples (kilobyte/ms ≈ MB/s), used for the bandwidth forecast
  (`mpc_draft.py:105-112`). Row 3 = download-time/delay history (not read by the
  forecaster, only rolled forward in `_transition`).
- `last_bitrate` — previous chosen quality index; constrains valid next
  sequences to `|Δindex| ≤ 1` (`_valid_sequences`, `mpc_draft.py:118-129`).
- `buffer_size` — seconds, drives the buffer-transition sim
  (`_transition`/`_sequence_score`, `mpc_draft.py:131-173`).
- `video_chunk_remain` → `chunk_index = TOTAL_VIDEO_CHUNK(48) - remain`
  (`mpc_draft.py:194`); indexes the per-quality chunk-size table
  `video_sizes[6, chunks]` loaded from `video1_sizes/video_size_0..5`
  (`load_video_sizes`, `mpc_draft.py:42-53`).
- `target_return` — seed for the simulated return trajectory; decremented by
  `reward_transform(reward)` each step (`mpc_draft.py:229,253`). `reward_transform`
  is `process_reward_fn` from `run_plm.process_reward` (`test.py:110`).
- `timestep` — only used to build `rollout.timesteps` for the timestep embedding.

**Chunk-size / throughput / delay / buffer** are all consumed. **Delay per se**
is only implicit (throughput row already folds in delay).

**k == `--speculative-draft-steps`?** Effectively yes, with clamping.
`run_plm.py:436-439` builds the generator with
`max_horizon=args.speculative_draft_steps`; `draft_and_verify` passes
`horizon=self.speculative_draft_steps` (`rl_policy.py:821-822`). Then
`rollout_length = min(requested, self.max_horizon, available)` where `available`
= chunks left in the video (`mpc_draft.py:195-199`). So near end-of-video the
draft is shorter than k. `run_plm.py:298-299` restricts `0 ≤ k ≤ 5`;
`RobustMPCDraftGenerator.__init__` further requires `1 ≤ max_horizon ≤ 5`
(`mpc_draft.py:65-70`) — k=0 just means the generator is never built
(`run_plm.py:436`).

**LLM forwards during draft: 0 — confirmed.** `generate()` is pure
numpy/itertools (`mpc_draft.py:203-268`). The only "model" is the harmonic-mean
throughput predictor. The brute force is `product(range(6), repeat=k)` filtered
to smoothness-valid sequences (`mpc_draft.py:119-129,213`) — 6^k candidates
(k=3 → 216).

Tie-break: `score >= best_score` keeps the **last** equal-scoring sequence
(`mpc_draft.py:217-219`); `product` order means ties favour the higher-bitrate
sequence. Comment says this preserves the NetLLM baseline's `reward >= max`
behaviour (`mpc_draft.py:210`).

---

## C. Verification path

**Where:** `OfflineRLPolicy.verify_mpc_draft()` (`rl_policy.py:777-804`).

**Forwards to score k actions: exactly 1.** Docstring and code:
"Verify all MPC bitrate decisions with exactly one PLM forward call"
(`rl_policy.py:778`). One `self._run_plm(...)` call (`rl_policy.py:785`) then
`self.speculative_stats["target_plm_calls"] += 1` (`rl_policy.py:786`).

**How k decisions come out of 1 forward:** `_embed_mpc_draft_blocks`
(`rl_policy.py:654-685`) embeds each drafted chunk as an 8-token
`[return, s1..s6, action]` block (`ABR_HISTORY_BLOCK_TOKENS = 2 + 6 = 8`,
`rl_policy.py:20`). These k blocks are appended to the real-history context by
`_build_selected_mpc_verification_context` (`rl_policy.py:687-775`). After the
forward, logits are read at each block's **state token** position
(`selected_history_tokens + i*8 + 6`, `rl_policy.py:788-795`) and pushed through
the action head → `action_logits` shape `[1, k, 6]` (`rl_policy.py:795`).

**KV cache: not used.** `_run_plm` calls
`self.plm(inputs_embeds=..., attention_mask=..., output_hidden_states=True,
stop_layer_idx=self.which_layer)` (`rl_policy.py:290-295`) — no `use_cache`, no
`past_key_values`, no incremental decoding. It is one full causal forward over
`[selected history] + [k draft blocks]`. (The lead-implemented dtype bridge
FP32→PLM-dtype→FP32 is here, `rl_policy.py:286-303`, and applies identically to
the normal `sample()` path.)

Temporal / Token selectors **are** applied to the history prefix during
verification (`_apply_temporal_selection` `rl_policy.py:700`, token selector
`rl_policy.py:742-750`); the k draft blocks are always protected
(`protected_suffix_tokens=draft_tokens`, `rl_policy.py:716-717`). This matches
the README "MPC draft → Temporal/Token → LLM verification" ordering.

**Prefix acceptance rule** (`build_acceptance_plan`, `acceptance.py:30-47`):
- Walk draft vs target actions left→right.
- **First** position where `draft[i] != target[i]`: stop. `accepted_count = i`,
  `actions = draft[:i] + (target[i],)` (accepted prefix + one target
  correction), `mismatch_index = i`. Everything after `i` is discarded.
- If all match: `accepted_count = k`, `mismatch_index = None`
  (`fully_accepted`).

**Discrete bitrate comparison: exact-value only, no tolerance.**
`acceptance.py:32-37` casts both to `int` and compares with `!=`. There is **no**
"close bitrate index also accepted" logic. Tolerance (§D) governs only *queue
reuse across future timesteps*, never the accept/reject of a drafted action.

**`target` action = sample or argmax** of the verification logits, per
`--speculative-verification-mode` (`_actions_from_verification_logits`,
`rl_policy.py:838-841`): `greedy` → `argmax`; `sample` (default) → stochastic
`self._sample` per position. So with the default mode the "target" is a *sample*,
making acceptance non-deterministic (seeded once per run at episode start,
`test.py:42`). ⚠ worth keeping in mind for acceptance-rate variance.

---

## D. Tolerance family

**Code location:** `validate_speculative_observation(...)` in
`acceptance.py:67-124`. Three thresholds:
- `buffer_tolerance_seconds` — `|observed_buffer - predicted_buffer|` in seconds
  (`buffer_deviation_seconds`, un-normalizes row 1 by `BUFFER_NORM_FACTOR=10`,
  `acceptance.py:50-64,102,112`).
- `state_tolerance` — `max` abs deviation over all state rows **except** buffer
  (row 1 zeroed, `acceptance.py:106`), with throughput row 2 measured
  *relatively* (`dev[2] /= max(|predicted[2]|, 1e-6)`, `acceptance.py:104-105`).
- `return_tolerance` — `|observed_return - predicted_return|`
  (`acceptance.py:109`).

First threshold exceeded sets `reason` in priority order buffer → state → return
(`acceptance.py:111-117`); any breach ⇒ `valid=False`.

**Defaults** (identical in both places):

| Param | Default | `rl_policy.OfflineRLPolicy.__init__` | `run_plm.py` argparse |
|---|---:|---|---|
| buffer tolerance | `1.0` s | `speculative_buffer_tolerance=1.0` (`rl_policy.py:56`) | `--speculative-buffer-tolerance` (`run_plm.py:614-615`) |
| state tolerance | `0.25` | `speculative_state_tolerance=0.25` (`rl_policy.py:57`) | `--speculative-state-tolerance` (`run_plm.py:616-617`) |
| return tolerance | `0.01` | `speculative_return_tolerance=0.01` (`rl_policy.py:58`) | `--speculative-return-tolerance` (`run_plm.py:618-619`) |

Negative values rejected in `__init__` (`rl_policy.py:123-128`), in
`run_plm.py:300-305`, and in `validate_speculative_observation`
(`acceptance.py:94-100`).

### Full list of speculative argparse args (`run_plm.py:610-619`)

| Flag | Type / choices | Default | Help string |
|---|---|---|---|
| `--speculative-draft-steps` | int (validated `0..5`, `run_plm.py:298`) | `0` | "MPC draft horizon; 0 disables speculative draft generation" |
| `--speculative-verification-mode` | `{greedy, sample}` | `sample` | "how target logits choose actions during draft verification" |
| `--speculative-buffer-tolerance` | float ≥ 0 | `1.0` | "maximum predicted/observed buffer error in seconds before fallback" |
| `--speculative-state-tolerance` | float ≥ 0 | `0.25` | "maximum normalized state-feature error before fallback" |
| `--speculative-return-tolerance` | float ≥ 0 | `0.01` | "maximum target-return error before fallback" |

Wiring: `run_plm.py:435-447` builds `RobustMPCDraftGenerator` (only if k>0) and
passes all five into `OfflineRLPolicy`. `test.py:102-111` routes to
`model.sample_speculative(...)` when `args.speculative_draft_steps > 0`, else
`model.sample(...)`.

The README "주요 파라미터" table (`--speculative-verification-mode` = `sample`,
tolerances `1.0 / 0.25 / 0.01`) **matches the code**.

---

## E. Queue

**Structure:** `self._speculative_queue = deque()` (`rl_policy.py:133`), entries
`{action, predicted_state, predicted_return, source}` (`rl_policy.py:962-970`).

**Fill:** after a draft+verify, `plan.actions` (accepted prefix + ≤1 correction,
so length `accepted_count` or `accepted_count+1`, always `≤ k`) is pushed
(`rl_policy.py:962-970`). Then the **first** entry is `popleft()` and executed as
the current step's bitrate (`rl_policy.py:971-974`). So the queue retains at most
`len(plan.actions) - 1` entries, i.e. **up to k-1 future steps** served without an
LLM call in the fully-accepted case; fewer (or zero) when the draft was
corrected.

**Reuse per step** (`sample_speculative`, `rl_policy.py:902-934`): if the queue
is non-empty, compare the *current real* state against `queue[0]["predicted_state"]`
via `validate_speculative_observation` with the three tolerances. If `valid`:
`popleft`, serve `queued["action"]`, commit only the real observed state/action
to history (`_append_observed_action`, `rl_policy.py:843-851`), **no PLM call**
(`last_selection_trace["target_model_called"] = False`, `rl_policy.py:917-922`).
Counters: `queued_actions_served`, `executed_speculative_actions`.

**Invalidate condition:** any single tolerance breach (buffer > 1.0 s, or max
non-buffer state deviation > 0.25 with throughput relative, or |return error| >
0.01). On breach the **entire queue is cleared** (`self._speculative_queue.clear()`,
`rl_policy.py:926`), `state_mismatch_fallbacks` +1, the reason-specific counter
(`buffer_mismatch_fallbacks` / `feature_mismatch_fallbacks` /
`return_mismatch_fallbacks`) +1 (`rl_policy.py:927-933`), and the step falls back
to normal `self.sample()` (one full LLM call, `_fallback_sample`
`rl_policy.py:876-878`).

Queue is also cleared on: throughput-predictor failure (`rl_policy.py:898`),
draft/verify exception (`rl_policy.py:948-950`), and every `clear_dq()` at
end-of-video (`rl_policy.py:1039`, which also calls `draft_generator.reset()`).

Note: re-validation compares against the **MPC-predicted** `rollout.states[index]`
(`rl_policy.py:965`), not a re-simulation from the actually-served action.

---

## F. Instrumentation status

**Already logged? Yes.** Written by `test_on_env` (`test.py:16-230`).

**Latency** (`test.py:99-118`):
- `torch.cuda.synchronize(args.device)` **before** `inference_start = perf_counter()`
  and **again after** the `sample_speculative`/`sample` call, then
  `inference_latencies_ms.append((perf_counter()-start)*1000)`. So measurement
  **is CUDA-synchronized on both ends** (guarded by
  `str(args.device).startswith('cuda') and torch.cuda.is_available()`).
- The timed region covers the *whole* decision: MPC rollout (CPU numpy + 6^k
  brute force) + embedding + the 1 verification forward, **or** a cheap
  queue-serve (no LLM), **or** a fallback (`sample_speculative` internally calls
  `sample`). All lumped into one series — **no per-path latency breakdown**, and
  the raw per-call list is not persisted (only mean / p50 / p95).
- Reported keys: `inference_latency_mean_ms`, `inference_latency_p50_ms`,
  `inference_latency_p95_ms`, `inference_calls` (`test.py:184-187`). Plus
  `test_log['time']` = episode wall time (`test.py:126`, not sync-bounded).

**LLM-call counting** (`get_speculative_metrics`, `rl_policy.py:976-983`; merged
in `test.py:205-227`):
- `target_plm_calls` — incremented in `verify_mpc_draft` (`rl_policy.py:786`) and
  in `sample()` (`rl_policy.py:1014`), so it counts verification forwards +
  normal forwards + fallback forwards. Each verification forward covers k drafts
  but counts once.
- `llm_call_reduction_ratio = 1 - target_plm_calls / inference_calls`
  (`test.py:222-225`).
- Also: `draft_attempts`, `drafted_actions`, `accepted_actions`,
  `corrected_actions`, `acceptance_rate` (= `accepted_actions/drafted_actions`,
  `rl_policy.py:978-981`), `executed_speculative_actions`, `queued_actions_served`,
  `fallback_calls`, `state_mismatch_fallbacks` +
  `buffer_/feature_/return_mismatch_fallbacks`, `draft_generation_failures`,
  `throughput_predictor_updates`, `pending_actions`.

**Token reduction:** `token_reduction_ratio`, `original_tokens_mean`,
`selected_tokens_mean` (`test.py:167-193`) — but only accumulated when
`last_selection_trace['target_model_called']` is truthy (`test.py:119-122`), so
queue-serve steps are excluded and verification steps *include* the k draft
tokens in `selected_length`.

**QoE:** `qoe_raw_mean`, `mean_bitrate_mbps`, `mean_rebuffer_s_per_chunk`,
`total_rebuffer_s`, `mean_smoothness_mbps`, `mean_reward` (`test.py:146-166`),
first chunk of each trace excluded (`skip_first_reward=True` / `[1:]` slices).

**Output format & location:**
- `os.path.join(results_dir, 'selector_metrics.json')` — single JSON,
  `json.dump(test_log, f, indent=2, sort_keys=True)` (`test.py:228-229`).
  ⚠ the file is named `selector_metrics.json` but holds the **entire** `test_log`
  including every speculative metric, latency, QoE and the arg echo.
- Per-trace plaintext `result_sim_abr_<trace>` files, tab-separated
  `time_stamp bit_rate buffer_size rebuf chunk_size download_time smoothness reward`
  (`test.py:131-145`).
- `results_dir` (`run_plm.py:486-487`) =
  `cfg.results_dir / '<trace>_<video>' / 'trace_num_<n>_fixed_<bool>' /
  '<plm>_<size>' / 'early_stop_..._seed_<seed>' / <selector_tag> / <speculative_tag>`.
  `cfg.results_dir = adaptive_bitrate_streaming/artifacts/results` (`config.py:19`)
  — **this path is git-ignored** (`.gitignore:17`). `speculative_tag` encodes k,
  mode and the three tolerances (`run_plm.py:482-485`).
  → For soyun's runs, outputs must be copied/redirected under
  `results/soyun/<run_id>/` (see [[AGENTS.md]] policy). `run_plm.py` has no CLI
  flag to relocate `cfg.results_dir`, and `config.py:19` hardcodes it with **no
  env-var override** (checked). Relocating soyun's outputs needs a wrapper that
  copies `selector_metrics.json` + `result_sim_abr_*` after the run, or a
  monkeypatch of `cfg.results_dir` before `run_plm` builds `results_dir`.

---

## G. Unfinished / suspicious / doc-vs-code

1. **Dead / reserved verifier path.** `build_speculative_verification_context`
   (`rl_policy.py:650-652`) and the `draft_blocks` parameter of
   `_build_selected_inference_context` (`rl_policy.py:530-648`) are **never
   called** by the live pipeline (the active path is
   `_build_selected_mpc_verification_context`, `rl_policy.py:687`). Docstrings say
   "reserved for a future MPC draft verifier". Two parallel context builders that
   differ in whether the *current* 7-token block is included:
   - live `_build_selected_mpc_verification_context` → history + k draft blocks
     only (no current block).
   - dead `_build_selected_inference_context(current_block, draft_blocks)` →
     history + current block + k draft blocks.
   Potential confusion / incomplete refactor. Not a bug in the executed path.

2. **Hardcoded chunk duration `+ 4.0` s** in the MPC buffer model
   (`mpc_draft.py:135,164`) and **no upper buffer cap**. The real `Environment`
   caps the buffer (Pensieve `BUFFER_THRESH`); the draft sim lets the buffer grow
   unbounded. For long high-bandwidth stretches the predicted buffer will drift
   above the real one → more `buffer` fallbacks than necessary. **확인 필요**
   (compare with `baseline_special/env.py` constants).

3. **`--speculative-verification-mode sample` is stochastic** (§C). The default
   makes the "target" a sampled action, so `acceptance_rate` and
   `corrected_actions` carry sampling noise on top of genuine draft error. RNG is
   seeded once per run (`test.py:42`), not per step. Consider `greedy` for
   apples-to-apples acceptance measurement — **확인 필요** with team lead whether
   `sample` is the intended default for the ablation table.

4. **Latency series is undifferentiated** (§F): queue-serve (~0 LLM), verify
   (1 LLM + MPC), and fallback (1 LLM) all land in one `inference_latencies_ms`
   list, and only mean/p50/p95 are persisted. Hard to attribute speedup to
   queue reuse vs shorter context without a per-path split or a raw dump.

5. **`target_plm_calls` conflates** verification forwards, baseline forwards and
   fallback forwards into one counter (§F). `llm_call_reduction_ratio` is still
   meaningful (calls per decision), but you can't separately see
   "verifications" vs "fallback LLM calls" without subtracting
   `fallback_calls` + `draft_attempts` yourself. **확인 필요** whether a
   dedicated `verification_forwards` counter is wanted.

6. **Output file misnomer:** `selector_metrics.json` holds all speculative +
   QoE + latency data, not just selector data (`test.py:228`). Cosmetic, but
   anyone grepping for a `speculative_metrics.json` will miss it.

7. **No `NotImplementedError` / `TODO` / `FIXME` / `stub` markers** anywhere in
   `speculative/`, the speculative parts of `rl_policy.py`, `run_plm.py`, or
   `test.py` (grep clean). Test coverage exists:
   `tests/test_mpc_draft.py`, `tests/test_speculative_acceptance.py`.

8. **README vs code — consistent** on: pipeline order (MPC → Temporal/Token →
   verify → queue), k = `--speculative-draft-steps`, defaults (mode `sample`,
   tol `1.0 / 0.25 / 0.01`), "one LLM call verifies k actions", dtype bridge on
   both paths, tolerance-gated queue reuse with fallback. No contradiction found;
   the README's prose is a faithful summary. The only gap is that the README
   does not mention (a) the exact-integer (no-tolerance) acceptance of drafted
   actions, (b) that a queue-invalidation clears the *whole* queue not just the
   stale head, or (c) the near-end-of-video horizon clamp.

---

### Quick reference — call chain

```
test.py:test_on_env loop
  └─ (k>0) OfflineRLPolicy.sample_speculative                 rl_policy.py:880
       ├─ draft_generator.observe(state)  -> predicted_bw     mpc_draft.py:95
       ├─ if queue: validate_speculative_observation          acceptance.py:67
       │     valid -> serve queue[0], NO LLM                   rl_policy.py:913-925
       │     invalid -> clear queue, fallback sample (1 LLM)   rl_policy.py:926-934
       └─ else: draft_and_verify                              rl_policy.py:806
            ├─ RobustMPCDraftGenerator.generate (0 LLM)       mpc_draft.py:175
            └─ verify_mpc_draft (exactly 1 LLM forward)       rl_policy.py:777
                 ├─ _embed_mpc_draft_blocks                    rl_policy.py:654
                 ├─ _build_selected_mpc_verification_context   rl_policy.py:687
                 │     (temporal + token selectors on history) rl_policy.py:700,742
                 └─ _run_plm  (no KV cache, full forward)      rl_policy.py:286
            then build_acceptance_plan (exact-int prefix)      acceptance.py:30
            fill queue, pop+execute first action               rl_policy.py:962-974
```

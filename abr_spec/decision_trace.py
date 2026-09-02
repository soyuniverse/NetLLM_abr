#!/usr/bin/env python3
"""abr_spec/decision_trace.py -- per-decision JSONL trace for ABR speculative runs.

soyun / speculative inference.  **No** upstream file is edited: this module
monkeypatches, at runtime and from soyun's own tree, four upstream call sites so
that every ABR bitrate decision emits one JSON line.

Patched (wrapper-only, original always called):

  ``plm_special.models.rl_policy.OfflineRLPolicy.sample_speculative``
      the decision itself -- times it (CUDA-synced) and snapshots the
      speculative counters before/after so the taken path and the fallback
      reason are recovered from counter deltas rather than guessed.
  ``...OfflineRLPolicy._actions_from_verification_logits``
      captures the LLM (target-model) action list for the k drafted steps.
  ``plm_special.speculative.mpc_draft.RobustMPCDraftGenerator.generate``
      captures the MPC draft actions and, separately, the **CPU time of the
      6^k brute-force rollout itself** -- this is the number that separates
      "latency lost to the MPC search" from "latency lost to a longer context".
  ``...RobustMPCDraftGenerator.observe``
      the robust-throughput predictor update (also pure CPU).
  ``baseline_special.env.Environment.get_video_chunk``
      the *outcome* of the previous decision (rebuffer / buffer / delay).  A
      record is held pending until the next chunk download reports back, then
      flushed, so ``rebuffer_after_s`` is the rebuffering actually caused by
      that decision.

Overhead is kept out of the measured window on purpose: inside the timed region
only ``perf_counter``/``process_time`` reads and one dict copy happen; the record
is assembled and written in the ``get_video_chunk`` wrapper, i.e. after the
latency measurement has already been taken.

Usage (from ``run_wrapped.py``, before ``runpy`` executes ``run_plm.py``)::

    import decision_trace
    decision_trace.install("/path/to/decisions.jsonl")
"""
import atexit
import json
import time

_COUNTER_KEYS = (
    "target_plm_calls", "draft_attempts", "drafted_actions", "accepted_actions",
    "corrected_actions", "executed_speculative_actions", "queued_actions_served",
    "fallback_calls", "state_mismatch_fallbacks", "buffer_mismatch_fallbacks",
    "feature_mismatch_fallbacks", "return_mismatch_fallbacks",
    "draft_generation_failures", "throughput_predictor_updates",
)


def _f(x):
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def _ilist(seq):
    if seq is None:
        return None
    return [int(v) for v in seq]


class _State:
    def __init__(self, path):
        self.fh = open(path, "w", buffering=1 << 20)
        self.path = path
        self.n_written = 0
        self.pending = None      # record waiting for its next-chunk outcome
        self.env_trace_idx = None
        self.env_chunk = 0
        self.reset_decision()

    # ---- per-decision slots, cleared at the start of every decision --------
    def reset_decision(self):
        self.mpc_actions = None
        self.mpc_cpu_s = None
        self.mpc_wall_s = None
        self.mpc_bandwidth = None
        self.observe_cpu_s = 0.0
        self.observe_wall_s = 0.0
        self.target_actions = None
        self.logits_wall_s = None

    def write(self, rec):
        self.fh.write(json.dumps(rec, sort_keys=True) + "\n")
        self.n_written += 1

    def flush_pending(self, outcome):
        if self.pending is None:
            return
        rec = self.pending
        self.pending = None
        rec.update(outcome)
        self.write(rec)

    def close(self):
        try:
            self.flush_pending({"rebuffer_after_s": None, "buffer_after_s": None,
                                "delay_after_ms": None, "end_of_video_after": None,
                                "outcome_missing": True})
            self.fh.close()
        except Exception:
            pass


_S = None
_INSTALLED = False


def install(jsonl_path):
    """Patch the upstream call sites and start writing ``jsonl_path``."""
    global _S, _INSTALLED
    if _INSTALLED:
        return _S
    import numpy as np
    import torch

    import baseline_special.env as env_mod
    import plm_special.models.rl_policy as rlp_mod
    import plm_special.speculative.mpc_draft as mpc_mod

    _S = _State(jsonl_path)
    atexit.register(_S.close)

    Policy = rlp_mod.OfflineRLPolicy
    Gen = mpc_mod.RobustMPCDraftGenerator
    Env = env_mod.Environment

    orig_sample_spec = Policy.sample_speculative
    orig_actions_from = Policy._actions_from_verification_logits
    orig_generate = Gen.generate
    orig_observe = Gen.observe
    orig_get_chunk = Env.get_video_chunk

    # ---- MPC brute-force rollout: isolate its CPU cost ---------------------
    def generate(self, *a, **kw):
        c0, w0 = time.process_time(), time.perf_counter()
        try:
            rollout = orig_generate(self, *a, **kw)
        finally:
            _S.mpc_cpu_s = time.process_time() - c0
            _S.mpc_wall_s = time.perf_counter() - w0
        _S.mpc_actions = _ilist(rollout.actions)
        _S.mpc_bandwidth = _f(rollout.predicted_bandwidth)
        return rollout

    def observe(self, *a, **kw):
        c0, w0 = time.process_time(), time.perf_counter()
        try:
            return orig_observe(self, *a, **kw)
        finally:
            _S.observe_cpu_s += time.process_time() - c0
            _S.observe_wall_s += time.perf_counter() - w0

    # ---- the LLM's own verified actions for the k drafted steps -----------
    def actions_from(self, action_logits):
        w0 = time.perf_counter()
        out = orig_actions_from(self, action_logits)
        _S.logits_wall_s = time.perf_counter() - w0
        _S.target_actions = _ilist(out)
        return out

    # ---- the decision -----------------------------------------------------
    def sample_speculative(self, state, target_return, timestep, last_bitrate,
                           buffer_size, video_chunk_remain, reward_transform=None):
        _S.reset_decision()
        before = {k: self.speculative_stats.get(k, 0) for k in _COUNTER_KEYS}
        cuda = torch.cuda.is_available()
        if cuda:
            torch.cuda.synchronize()
        c0, w0 = time.process_time(), time.perf_counter()
        action = orig_sample_spec(
            self, state=state, target_return=target_return, timestep=timestep,
            last_bitrate=last_bitrate, buffer_size=buffer_size,
            video_chunk_remain=video_chunk_remain, reward_transform=reward_transform,
        )
        if cuda:
            torch.cuda.synchronize()
        lat_ms = (time.perf_counter() - w0) * 1000.0
        cpu_ms = (time.process_time() - c0) * 1000.0
        # ---- everything below is OUTSIDE the measured window ----
        delta = {k: self.speculative_stats.get(k, 0) - before[k] for k in _COUNTER_KEYS}
        if delta["queued_actions_served"]:
            stage = "queue_serve"
        elif delta["fallback_calls"]:
            stage = "fallback"
        elif delta["draft_attempts"]:
            stage = "draft_verify"
        else:
            stage = "plain"
        reason = None
        for key, name in (("buffer_mismatch_fallbacks", "buffer"),
                          ("feature_mismatch_fallbacks", "state"),
                          ("return_mismatch_fallbacks", "return"),
                          ("draft_generation_failures", "draft_failure")):
            if delta[key]:
                reason = name
                break

        row = np.asarray(state.detach().cpu().numpy(), dtype=np.float64)
        while row.ndim > 2:
            row = row[0]
        thr = [float(v) for v in row[2]]
        trace = dict(getattr(self, "last_selection_trace", {}) or {})

        acc = delta["accepted_actions"]
        rec = {
            "trace_idx": _S.env_trace_idx,
            "chunk": _S.env_chunk,
            "t": int(timestep),
            "buffer": _f(buffer_size),
            "video_chunk_remain": _f(video_chunk_remain),
            "target_return": _f(target_return),
            "throughput_last": thr[-1],
            "throughput_recent": thr,
            "last_action": int(last_bitrate),
            "action": int(action),
            "stage": stage,
            "fallback_reason": reason,
            "mpc_draft_actions": _S.mpc_actions,
            "llm_target_action": (None if not _S.target_actions
                                  else int(_S.target_actions[0])),
            "llm_target_actions": _S.target_actions,
            "accepted_count": (int(acc) if delta["draft_attempts"] else None),
            "drafted_count": (int(delta["drafted_actions"])
                              if delta["draft_attempts"] else None),
            "corrected": bool(delta["corrected_actions"]),
            "target_plm_called": bool(delta["target_plm_calls"]),
            "predicted_bandwidth": _S.mpc_bandwidth,
            "latency_ms": lat_ms,
            "cpu_ms": cpu_ms,
            "mpc_rollout_cpu_ms": (None if _S.mpc_cpu_s is None
                                   else _S.mpc_cpu_s * 1000.0),
            "mpc_rollout_wall_ms": (None if _S.mpc_wall_s is None
                                    else _S.mpc_wall_s * 1000.0),
            "throughput_observe_cpu_ms": _S.observe_cpu_s * 1000.0,
            "verify_logits_wall_ms": (None if _S.logits_wall_s is None
                                      else _S.logits_wall_s * 1000.0),
            "context_original_tokens": trace.get("original_length"),
            "context_selected_tokens": trace.get("selected_length"),
            "selection_stage": trace.get("stage"),
        }
        _S.flush_pending({"rebuffer_after_s": None, "buffer_after_s": None,
                          "delay_after_ms": None, "end_of_video_after": None,
                          "outcome_missing": True})
        _S.pending = rec
        return action

    # ---- outcome of the previous decision ---------------------------------
    def get_video_chunk(self, quality):
        _S.env_trace_idx = int(getattr(self, "trace_idx", -1))
        out = orig_get_chunk(self, quality)
        delay, sleep_time, buffer_size, rebuf = out[0], out[1], out[2], out[3]
        end_of_video = out[6]
        _S.flush_pending({
            "rebuffer_after_s": _f(rebuf),
            "rebuffered": bool(float(rebuf) > 0.0),
            "buffer_after_s": _f(buffer_size),
            "delay_after_ms": _f(delay),
            "sleep_after_ms": _f(sleep_time),
            "end_of_video_after": bool(end_of_video),
            "outcome_missing": False,
        })
        _S.env_chunk = 0 if end_of_video else _S.env_chunk + 1
        return out

    Policy.sample_speculative = sample_speculative
    Policy._actions_from_verification_logits = actions_from
    Gen.generate = generate
    Gen.observe = observe
    Env.get_video_chunk = get_video_chunk
    _INSTALLED = True
    print(f"[decision_trace] installed -> {jsonl_path}")
    return _S


def written():
    return 0 if _S is None else _S.n_written

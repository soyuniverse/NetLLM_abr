#!/usr/bin/env python3
"""abr_spec/serve_gate.py -- constrain speculative behaviour when the buffer is low.

soyun / speculative inference.

DRAFTER_ABLATION.md section S.7: the drafter replacement clears speedup 1.24x but
fails the total-rebuffering gate.  Cause (section S.6): a few queue entries
execute after the buffer has drained below ~5 s -- drafted several chunks earlier
when the buffer was comfortable; the hybrid drafter's route-time buffer check
cannot see the future drain.

Installed by ``run_wrapped.py`` before ``run_plm.py`` runs -- the same monkeypatch
pattern as ``drafter_select.py`` / ``decision_trace.py`` / ``nan_probe.py``.  No
team file is edited.  ``floor_seconds = 0`` (the default) installs no patch.

Three responses (``mode``) to a decision whose buffer is below ``floor_seconds``:

``fallback``
    Refuse the queued entry (``valid=False, reason='buffer'``); ``rl_policy``
    clears the queue and calls the LLM once.  **Measured 2026-09-09
    (DRAFTER_ABLATION section 9): worse** -- handing a drained buffer to the
    sampling LLM destabilises the trajectory (total rebuffering ~doubles).  Kept
    for the A-B record.

``conservative``
    Refuse the queued entry, then serve ``max(0, last - step)`` directly (no LLM,
    no PLM forward) for that one decision; speculation resumes next chunk.

``safe-mode``
    While the *observed* buffer is below the floor, bypass speculation entirely:
    serve ``max(0, last - step)`` every decision, no drafter, no LLM.  Speculation
    resumes automatically once the buffer recovers above the floor.  This removes
    the LLM-at-low-buffer failure mode outright and, since no PLM runs in the
    danger zone, does not cost speedup.

``check_predicted`` (``fallback`` / ``conservative`` only): also trip when the
queued entry's own predicted buffer is below the floor.
"""

CHOICES = ("fallback", "conservative", "safe-mode")

_INSTALLED = None
_S = {"pending_conservative": False, "gate_trips": 0, "safe_serves": 0}


def _buf_seconds(state):
    import numpy as np
    from baseline_special.utils.constants import BUFFER_NORM_FACTOR
    if hasattr(state, "detach"):
        state = state.detach().cpu().numpy()
    arr = np.asarray(state, dtype=np.float64)
    while arr.ndim > 2 and arr.shape[0] == 1:
        arr = arr[0]
    if arr.shape != (6, 6):
        raise ValueError(f"state must resolve to [6,6], got {arr.shape}")
    return float(arr[1, -1]) * float(BUFFER_NORM_FACTOR)


def _conservative_bitrate(policy, last_bitrate, step):
    if last_bitrate is None:
        last_bitrate = (int(policy.raw_actions_dq[-1])
                        if len(policy.raw_actions_dq) else 0)
    return max(0, int(last_bitrate) - step)


def install(floor_seconds=0.0, check_predicted=False, mode="fallback", step=1):
    global _INSTALLED
    floor_seconds = float(floor_seconds)
    if floor_seconds < 0:
        raise ValueError("floor_seconds must be non-negative")
    if mode not in CHOICES:
        raise ValueError(f"mode must be one of {CHOICES}")
    step = int(step)
    if step < 1:
        raise ValueError("step must be a positive integer")

    info = {"gate": "serve-buffer-floor", "floor_seconds": floor_seconds,
            "check_predicted": bool(check_predicted), "mode": mode, "step": step,
            "patched": False}
    if floor_seconds == 0.0:
        print("[serve_gate] floor_seconds=0 -- no patch installed")
        _INSTALLED = info
        return info

    _S.update(pending_conservative=False, gate_trips=0, safe_serves=0)
    import plm_special.models.rl_policy as rlp_mod
    from plm_special.speculative.acceptance import ObservationValidation
    Policy = rlp_mod.OfflineRLPolicy

    if mode == "safe-mode":
        orig_ss = Policy.sample_speculative

        def sample_speculative(self, state, target_return, timestep, last_bitrate,
                               buffer_size, video_chunk_remain, reward_transform=None):
            try:
                low = float(buffer_size) < floor_seconds
            except (TypeError, ValueError):
                low = False
            if not low:
                return orig_ss(self, state, target_return, timestep, last_bitrate,
                               buffer_size, video_chunk_remain, reward_transform)
            self._speculative_queue.clear()
            _S["gate_trips"] += 1
            _S["safe_serves"] += 1
            bitrate = _conservative_bitrate(self, last_bitrate, step)
            self.speculative_stats["fallback_calls"] += 1
            self._append_observed_action(state, target_return, timestep, bitrate)
            self.last_selection_trace = {
                "target_model_called": False, "stage": "low_buffer_safe",
                "original_length": 0, "selected_length": 0,
            }
            return bitrate

        Policy.sample_speculative = sample_speculative
        info["patched"] = True
        print(f"[serve_gate] safe-mode: buffer < {floor_seconds:g} s -> step down "
              f"{step}, no LLM/drafter until recovered")
        _INSTALLED = info
        return info

    # fallback / conservative: wrap the validator
    orig_validate = rlp_mod.validate_speculative_observation

    def gated(observed_state, predicted_state, *a, **kw):
        result = orig_validate(observed_state, predicted_state, *a, **kw)
        if not result.valid:
            return result
        try:
            low = _buf_seconds(observed_state) < floor_seconds
            if not low and check_predicted:
                low = _buf_seconds(predicted_state) < floor_seconds
        except (ValueError, TypeError):
            return result
        if not low:
            return result
        _S["gate_trips"] += 1
        if mode == "conservative":
            _S["pending_conservative"] = True
        return ObservationValidation(
            valid=False, reason="buffer",
            buffer_deviation_seconds=result.buffer_deviation_seconds,
            state_deviation=result.state_deviation,
            return_deviation=result.return_deviation)

    rlp_mod.validate_speculative_observation = gated

    if mode == "conservative":
        orig_fb = Policy._fallback_sample

        def _fallback_sample(self, state, target_return, timestep):
            if not _S["pending_conservative"]:
                return orig_fb(self, state, target_return, timestep)
            _S["pending_conservative"] = False
            _S["safe_serves"] += 1
            bitrate = _conservative_bitrate(self, None, step)
            self.speculative_stats["fallback_calls"] += 1
            self._append_observed_action(state, target_return, timestep, bitrate)
            return bitrate

        Policy._fallback_sample = _fallback_sample

    info["patched"] = True
    print(f"[serve_gate] mode={mode} buffer < {floor_seconds:g} s"
          + (", observed or predicted" if check_predicted else ", observed")
          + (f" -> step down {step}" if mode == "conservative"
             else " -> LLM fallback"))
    _INSTALLED = info
    return info


def installed():
    return _INSTALLED


def counters():
    return {k: _S[k] for k in ("gate_trips", "safe_serves")}

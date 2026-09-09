#!/usr/bin/env python3
"""abr_spec/serve_gate.py -- refuse a queued speculative action when the buffer is low.

soyun / speculative inference.

DRAFTER_ABLATION.md section S.7: the drafter replacement clears speedup 1.24x but
fails the total-rebuffering gate.  The cause (section S.6) is a small number of
queue entries that *execute* after the buffer has drained below ~5 s -- the draft
was made several chunks earlier when the buffer was comfortable, and the
hybrid drafter's route-time buffer check cannot see the future drain.  Almost all
of the queue-serve rebuffering lands in the ``< 5 s`` buffer band; the ``>= 20 s``
band (76 % of all queue serves) contributes zero.

This module installs the **serve-time** fix that section S.7 (a)/(b) asks for,
without editing a team file.  ``rl_policy.sample_speculative`` decides whether to
reuse the head of ``self._speculative_queue`` by calling the module-global
``validate_speculative_observation`` (bound into ``rl_policy``'s namespace at
import).  We wrap that reference: if a queue entry would otherwise be accepted but

  * the **observed** buffer right now is below ``floor_seconds``, or
  * (with ``check_predicted``) the entry's own **predicted** buffer is below it,

we return ``valid=False, reason='buffer'``.  ``sample_speculative`` then does
exactly what it already does on a buffer-tolerance miss: clears the queue and
falls back to one real LLM call.  So a gated demotion is counted as a
``buffer_mismatch_fallback`` and shows up in ``decisions.jsonl`` as a ``fallback``
stage with ``fallback_reason='buffer'`` -- fully measurable.

``floor_seconds = 0`` (the default) installs no patch: the path is then
byte-for-byte the ablation-freeze path.

This is the same monkeypatch pattern as ``drafter_select.py`` /
``decision_trace.py`` / ``nan_probe.py``.  A first-class ``run_plm.py`` flag would
remove the indirection -- see docs/soyun/CHANGE_REQUEST_SERVE_TIME_GATE.md.
"""

_INSTALLED = None


def _resolve_buffer_seconds(state):
    """state[1, -1] * BUFFER_NORM_FACTOR -- the ABR buffer level in seconds."""
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


def install(floor_seconds=0.0, check_predicted=False):
    """Wrap rl_policy.validate_speculative_observation with a buffer floor.

    Returns a provenance dict (also retrievable via :func:`installed`).
    """
    global _INSTALLED
    floor_seconds = float(floor_seconds)
    if floor_seconds < 0:
        raise ValueError("floor_seconds must be non-negative")

    info = {
        "gate": "serve-buffer-floor",
        "floor_seconds": floor_seconds,
        "check_predicted": bool(check_predicted),
        "patched": False,
    }
    if floor_seconds == 0.0:
        print("[serve_gate] floor_seconds=0 -- no patch installed "
              "(serve path unchanged)")
        _INSTALLED = info
        return info

    import plm_special.models.rl_policy as rlp_mod
    from plm_special.speculative.acceptance import ObservationValidation

    original = rlp_mod.validate_speculative_observation

    def gated(observed_state, predicted_state, *args, **kwargs):
        result = original(observed_state, predicted_state, *args, **kwargs)
        if not result.valid:
            return result
        try:
            observed_buffer = _resolve_buffer_seconds(observed_state)
            low = observed_buffer < floor_seconds
            if not low and check_predicted:
                low = _resolve_buffer_seconds(predicted_state) < floor_seconds
        except (ValueError, TypeError):
            return result
        if not low:
            return result
        return ObservationValidation(
            valid=False,
            reason="buffer",
            buffer_deviation_seconds=result.buffer_deviation_seconds,
            state_deviation=result.state_deviation,
            return_deviation=result.return_deviation,
        )

    rlp_mod.validate_speculative_observation = gated
    info["patched"] = True
    print(f"[serve_gate] queue serve refused when buffer < {floor_seconds:g} s"
          + (" (observed or predicted)" if check_predicted else " (observed)"))
    _INSTALLED = info
    return info


def installed():
    return _INSTALLED

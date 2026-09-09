#!/usr/bin/env python3
"""abr_spec/reseed_per_episode.py -- OPT-IN diagnostic: re-seed the RNG per trace.

soyun / speculative inference.

[[TRAJECTORY_DIVERGENCE]] / [[NEEDS_UPSTREAM]] #6: ``plm_special/test.py:42`` calls
``set_random_seed(args.seed)`` ONCE, before the 100-trace loop; ``clear_dq()`` at
each episode boundary does not re-seed.  So the sampling RNG stream is shared
across all traces, and any mid-run intervention (the serve gate) that changes the
RNG-draw count contaminates every later trace.

This module, installed via ``run_wrapped.py --probe reseed_per_episode``,
monkeypatches two call sites so that every trace starts from ``seed + trace_i``:

  * ``plm_special.test.set_random_seed`` -- wrapped to record ``args.seed`` (the
    single pre-loop call) and, from then on, be a no-op recorder.
  * ``plm_special.models.rl_policy.OfflineRLPolicy.clear_dq`` -- wrapped to call
    ``set_random_seed(base_seed + episode_index)`` AFTER the original, i.e. right
    at the episode boundary in test.py.

**Do NOT wire this into the default pipeline.**  The 40/40 determinism battery
([[DRAFTER_ABLATION]] §1) and every committed result assume the current
seed-once behaviour.  This is a separate, opt-in execution path for A/B
diagnostics only; a run that uses it is labelled ``reseed_per_episode`` in its
manifest and is not comparable to a run that does not.
"""
import json

_STATE = {"installed": False, "base_seed": None, "episode": 0, "reseeds": 0}


def install(path):
    if _STATE["installed"]:
        return _STATE
    import plm_special.test as test_mod
    import plm_special.models.rl_policy as rlp_mod
    from plm_special.utils.utils import set_random_seed as _real_seed

    orig_clear_dq = rlp_mod.OfflineRLPolicy.clear_dq

    def recording_set_seed(seed):
        # the one pre-loop call in test.py carries args.seed
        if _STATE["base_seed"] is None:
            _STATE["base_seed"] = int(seed)
        _real_seed(seed)

    def clear_dq(self, *a, **kw):
        out = orig_clear_dq(self, *a, **kw)
        base = _STATE["base_seed"]
        if base is not None:
            _STATE["episode"] += 1
            _real_seed(base + _STATE["episode"])
            _STATE["reseeds"] += 1
        return out

    test_mod.set_random_seed = recording_set_seed
    rlp_mod.OfflineRLPolicy.clear_dq = clear_dq
    _STATE["installed"] = True
    _STATE["_path"] = path
    print("[reseed_per_episode] INSTALLED -- RNG re-seeded (seed + trace_i) at "
          "every episode boundary. NOT the default pipeline; diagnostic A/B only.")
    import atexit
    atexit.register(_dump, path)
    return _STATE


def _dump(path):
    try:
        json.dump({k: v for k, v in _STATE.items() if not k.startswith("_")},
                  open(path, "w"), indent=2)
    except Exception:
        pass

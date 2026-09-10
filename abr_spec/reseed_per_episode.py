#!/usr/bin/env python3
"""abr_spec/reseed_per_episode.py -- OPT-IN diagnostic: re-seed the RNG per trace.

soyun / speculative inference.


QUICK START (copy-paste, fill in the two <...> paths)
----------------------------------------------------
Run your evaluation with the diagnostic overlay installed -- nothing else
changes, and the wrapper touches no team file::

    cd /path/to/NetLLM_abr
    .venv/bin/python abr_spec/run_wrapped.py \\
      --run-id reseed_check --phase myrun --ckpt-name <your_ckpt_dir_name> \\
      --probe reseed_per_episode \\
      -- --test --fp16 --seed 1 --plm-type llama --plm-size base --rank 128 \\
         --plm-dir ../downloaded_plms/llama/base \\
         --model-dir ../downloaded_plms/ft_plms/<your_lora_dir> \\
         --trace fcc-test --trace-num 100 --video video1 --fixed-order \\
         --device cuda:0 --device-out cuda:0 \\
         --temporal-selector none --token-selector none \\
         --speculative-draft-steps 3 --speculative-verification-mode sample

``<your_ckpt_dir_name>`` is a directory under ``results/soyun/checkpoints/``;
``<your_lora_dir>`` is your fine-tuned adapter under
``downloaded_plms/ft_plms/``.  A confirmation line is printed at install time and
``results/soyun/reseed_check/myrun/reseed_per_episode.json`` records
``{"reseeds": 100}`` when it worked.  Run your baseline the same way (with and
without the intervention you are testing) and compare per trace.


THIS TOOL vs. THE test.py PATCH
------------------------------
* This tool (option B): a monkeypatch installed for one run via ``--probe``.
  No team file changes, nothing to merge -- use it to *check* whether RNG
  contamination is affecting a specific A/B, right now.
* ``docs/soyun/patches/test_py_per_episode_reseed.patch`` (option A): the same
  fix applied to ``test.py`` itself, so every future run in this checkout is
  clean by default.  Apply it if you will keep experimenting in this environment.

Both use the identical ``base_seed + episode_index`` scheme, so a run under this
probe and a run after the patch produce the same per-trace seeding.
Full comparison + guidance: ``docs/soyun/TEST_HARNESS_HANDOFF.md``.


HOW IT WORKS
------------
[[TRAJECTORY_DIVERGENCE]] / [[NEEDS_UPSTREAM]] #6: ``plm_special/test.py`` calls
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

**QoE / rebuffering are still a per-seed lottery under this tool** (each trace is
now independent, but a single seed still draws one outcome per trace).  Report
QoE / rebuffering as mean +- std over >= 3 seeds regardless -- see
``docs/soyun/SUBMISSION_SUMMARY.md``.
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

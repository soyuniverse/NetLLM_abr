#!/usr/bin/env python3
"""abr_spec/run_wrapped.py -- run NetLLM's run_plm.py in-process with cfg overrides.

soyun / speculative inference.  This wrapper NEVER edits an upstream file and never
calls ``run_plm.py`` as a subprocess.  It imports the shared ``config`` singleton,
rewrites two paths on it, sets ``sys.argv``, then executes ``run_plm.py`` via
``runpy`` under ``__name__ == "__main__"`` (i.e. the exact CLI path, just with
redirected output roots):

    config.cfg.plm_ft_dir   -> results/soyun/checkpoints/<ckpt-name>/
    config.cfg.results_dir  -> results/soyun/<run-id>/<phase>/raw/

Everything after ``--`` is forwarded verbatim to run_plm.py.  A manifest is
written to results/soyun/<run-id>/manifest.json *before* execution; result files
(selector_metrics.json) and per-segment wall-clock timing are collected after.

Run one phase per process invocation (keeps CUDA state clean between phases):

    python abr_spec/run_wrapped.py --run-id RID --phase adapt  --ckpt-name NAME -- <run_plm args>
    python abr_spec/run_wrapped.py --run-id RID --phase test_a --ckpt-name NAME -- <run_plm args>
"""
import argparse
import json
import os
import re
import runpy
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ABR = REPO / "adaptive_bitrate_streaming"
SOYUN = REPO / "results" / "soyun"


def sh(*cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
        return p.stdout.strip()
    except Exception as exc:  # pragma: no cover - defensive
        return f"<error: {exc}>"


def pkg_versions():
    out = {}
    for mod in ("torch", "transformers", "peft", "numpy", "accelerate"):
        try:
            out[mod] = __import__(mod).__version__
        except Exception as exc:
            out[mod] = f"<missing: {exc}>"
    return out


def gpu_name():
    return sh("nvidia-smi", "--query-gpu=name,memory.total,driver_version",
             "--format=csv,noheader") or "<none>"


def extract_flag(argv, flag):
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


class _Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, obj):
        for s in self.streams:
            s.write(obj)
            s.flush()

    def flush(self):
        for s in self.streams:
            s.flush()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--phase", required=True,
                    help="phase label -> results/soyun/<run-id>/<phase>/")
    ap.add_argument("--ckpt-name", required=True,
                    help="checkpoint dir name -> results/soyun/checkpoints/<name>/")
    args, passthrough = ap.parse_known_args()
    if passthrough and passthrough[0] == "--":
        passthrough = passthrough[1:]
    if not passthrough:
        ap.error("no run_plm.py arguments given after '--'")

    run_dir = SOYUN / args.run_id
    phase_dir = run_dir / args.phase
    raw_dir = phase_dir / "raw"
    ckpt_dir = SOYUN / "checkpoints" / args.ckpt_name
    for d in (phase_dir, raw_dir, ckpt_dir):
        d.mkdir(parents=True, exist_ok=True)

    # ---- apply overrides to the shared singleton BEFORE run_plm imports it ----
    os.chdir(str(ABR))
    sys.path.insert(0, str(ABR))
    import config  # adaptive_bitrate_streaming/config.py
    config.cfg.plm_ft_dir = str(ckpt_dir)
    config.cfg.results_dir = str(raw_dir)

    # ---- seed handling (best effort) ----
    seed = extract_flag(passthrough, "--seed")
    det_notes = [
        "run_plm.set_random_seed() (run_plm.py:332) and test_on_env() (test.py:42) "
        "re-seed numpy/torch/torch.cuda/random from --seed at run start.",
        "run_plm.py:501 sets torch.backends.cudnn.benchmark=True (upstream, not "
        "modifiable here) -> CUDA matmul/conv kernels are autotuned, so results are "
        "NOT guaranteed bitwise-reproducible run to run.",
        "phase test_a uses stochastic sampling (rl_policy._sample -> random.choices, "
        "seeded); test_b uses --speculative-verification-mode greedy (argmax, "
        "deterministic given fixed weights).",
    ]
    if seed is not None:
        os.environ["PYTHONHASHSEED"] = str(seed)
        try:
            import random as _random
            import numpy as _np
            _random.seed(int(seed))
            _np.random.seed(int(seed))
            import torch as _torch
            _torch.manual_seed(int(seed))
            if _torch.cuda.is_available():
                _torch.cuda.manual_seed_all(int(seed))
        except Exception as exc:  # pragma: no cover
            det_notes.append(f"wrapper pre-seed partially skipped: {exc}")
    else:
        det_notes.append("NO --seed in passthrough: seeding left to run_plm defaults "
                         "(argparse default 100003) -- record only, not fixed here.")

    sys.argv = ["run_plm.py"] + list(passthrough)

    manifest = {
        "run_id": args.run_id,
        "phase": args.phase,
        "utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": sh("git", "rev-parse", "HEAD"),
        "git_branch": sh("git", "rev-parse", "--abbrev-ref", "HEAD"),
        "git_status_porcelain": sh("git", "status", "--porcelain"),
        "argv_expanded": sys.argv,
        "seed": int(seed) if seed is not None else None,
        "determinism_notes": det_notes,
        "cfg_overrides": {
            "plm_ft_dir": config.cfg.plm_ft_dir,
            "results_dir": config.cfg.results_dir,
        },
        "cwd": os.getcwd(),
        "python": sys.version.split()[0],
        "package_versions": pkg_versions(),
        "gpu": gpu_name(),
        "parsed": {
            "adapt": "--adapt" in passthrough,
            "test": "--test" in passthrough,
            "fixed_order": "--fixed-order" in passthrough,
            "rank": extract_flag(passthrough, "--rank"),
            "num_epochs": extract_flag(passthrough, "--num-epochs"),
            "eval_per_epoch": extract_flag(passthrough, "--eval-per-epoch"),
            "trace": extract_flag(passthrough, "--trace"),
            "trace_num": extract_flag(passthrough, "--trace-num"),
            "video": extract_flag(passthrough, "--video"),
            "speculative_draft_steps": extract_flag(passthrough, "--speculative-draft-steps"),
            "speculative_verification_mode": extract_flag(passthrough, "--speculative-verification-mode"),
            "temporal_selector": extract_flag(passthrough, "--temporal-selector"),
            "token_selector": extract_flag(passthrough, "--token-selector"),
        },
    }

    mpath = run_dir / "manifest.json"
    allm = (json.loads(mpath.read_text())
            if mpath.exists() else {"run_id": args.run_id, "phases": []})
    allm["phases"].append(manifest)
    mpath.write_text(json.dumps(allm, indent=2))
    (phase_dir / "manifest_phase.json").write_text(json.dumps(manifest, indent=2))

    # ---- execute run_plm.py exactly as its CLI would ----
    log_path = phase_dir / "console.log"
    lf = open(log_path, "w")
    real_out, real_err = sys.stdout, sys.stderr
    sys.stdout = _Tee(real_out, lf)
    sys.stderr = _Tee(real_err, lf)
    t0 = time.time()
    status, err = "ok", None
    try:
        runpy.run_path(str(ABR / "run_plm.py"), run_name="__main__")
    except SystemExit as exc:
        if exc.code not in (0, None):
            status, err = "SystemExit", str(exc.code)
    except BaseException as exc:  # noqa: BLE001 - capture everything for the report
        status, err = "error", repr(exc)
        traceback.print_exc()
    finally:
        wall = time.time() - t0
        sys.stdout, sys.stderr = real_out, real_err
        lf.close()

    # ---- collect outputs ----
    collected = []
    for hit in raw_dir.rglob("selector_metrics.json"):
        dst = phase_dir / "selector_metrics.json"
        shutil.copy2(hit, dst)
        collected.append(str(dst.relative_to(REPO)))
    ckpt_files = sorted(
        str(p.relative_to(REPO))
        for p in ckpt_dir.rglob("*")
        if p.is_file() and p.name in (
            "adapter_config.json", "adapter_model.safetensors",
            "adapter_model.bin", "modules_except_plm.bin")
    )

    text = log_path.read_text(errors="replace")
    timing = {"wall_seconds": round(wall, 2)}
    for key, pat in (
        ("time_training_s", r"'time/training':\s*([0-9.]+)"),
        ("time_evaluation_s", r"'time/evaluation':\s*([0-9.]+)"),
        ("test_on_env_time_s", r"\bTest time:\s*([0-9.]+)"),
    ):
        found = re.findall(pat, text)
        if found:
            timing[key] = [round(float(x), 3) for x in found]

    result = {
        "status": status,
        "error": err,
        "wall_seconds": round(wall, 2),
        "timing": timing,
        "collected_result_files": collected,
        "checkpoint_files": ckpt_files,
        "checkpoint_dir": str(ckpt_dir.relative_to(REPO)),
        "console_log": str(log_path.relative_to(REPO)),
    }
    (phase_dir / "result.json").write_text(json.dumps(result, indent=2))
    allm = json.loads(mpath.read_text())
    allm["phases"][-1]["result"] = result
    mpath.write_text(json.dumps(allm, indent=2))

    print(f"[run_wrapped] phase={args.phase} status={status} wall={wall:.1f}s "
          f"collected={collected}")
    if status != "ok":
        print(f"[run_wrapped] FAILURE: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()

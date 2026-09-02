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

Cross-instance guard
--------------------
The manifest records the GPU string (``nvidia-smi`` name/mem/driver).  Before a
run, the wrapper scans every other ``results/soyun/*/manifest.json`` and, if any
earlier run recorded a *different* GPU string, it prints a warning and stamps
``"instance_changed": true`` on this run's manifest.  ``inference_latency``
absolute numbers are only comparable within one instance, so a run flagged
``instance_changed`` (or any run from a different GPU) must not be used as a
latency baseline.

Latency speedup
---------------
Pass ``--baseline-run-id RID`` to have the wrapper write
``results/soyun/<run-id>/summary.json`` with a ``baseline`` block: per-phase
``inference_latency`` mean/p50/p95 and the speedup ratio
``baseline_latency / this_latency``.  The speedup is computed only when the
baseline run's GPU string matches this run's exactly; otherwise it is left
``null`` with a note (prior-instance runs are never valid latency baselines).
``summary.json`` is written on every invocation (baseline block only when the
flag is given) and aggregates all phases recorded for the run so far.
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


# keys copied verbatim out of selector_metrics.json (== the full test_log) into
# each phase's result.metrics and into summary.json
METRIC_KEYS = (
    "inference_calls", "inference_latency_mean_ms", "inference_latency_p50_ms",
    "inference_latency_p95_ms",
    "target_plm_calls", "llm_call_reduction_ratio",
    "draft_attempts", "drafted_actions", "accepted_actions", "corrected_actions",
    "acceptance_rate", "executed_speculative_actions", "queued_actions_served",
    "pending_actions", "fallback_calls", "state_mismatch_fallbacks",
    "buffer_mismatch_fallbacks", "feature_mismatch_fallbacks",
    "return_mismatch_fallbacks", "draft_generation_failures",
    "throughput_predictor_updates",
    "qoe_raw_mean", "mean_reward", "mean_bitrate_mbps",
    "mean_rebuffer_s_per_chunk", "total_rebuffer_s", "mean_smoothness_mbps",
    "evaluated_video_chunks", "token_reduction_ratio",
    "speculative_draft_steps", "speculative_verification_mode",
    "speculative_buffer_tolerance", "speculative_state_tolerance",
    "speculative_return_tolerance",
)
_LAT = ("inference_latency_mean_ms", "inference_latency_p50_ms",
        "inference_latency_p95_ms")


def prior_run_gpus(current_run_id):
    """run_id -> sorted GPU strings recorded in results/soyun/<run_id>/manifest.json."""
    out = {}
    for mpath in sorted(SOYUN.glob("*/manifest.json")):
        rid = mpath.parent.name
        if rid == current_run_id:
            continue
        try:
            data = json.loads(mpath.read_text())
        except Exception:
            continue
        gpus = sorted({ph.get("gpu") for ph in data.get("phases", []) if ph.get("gpu")})
        if gpus:
            out[rid] = gpus
    return out


def read_metrics(selector_metrics_path):
    if not selector_metrics_path.is_file():
        return {}
    try:
        full = json.loads(selector_metrics_path.read_text())
    except Exception as exc:  # pragma: no cover - defensive
        return {"_parse_error": repr(exc)}
    return {k: full[k] for k in METRIC_KEYS if k in full}


def _speedup_vs_baseline(baseline_run_id, current_gpu, this_phases,
                         baseline_phase=None):
    b = {"baseline_run_id": baseline_run_id,
         "baseline_phase_requested": baseline_phase,
         "latency_speedup_mean": None}
    bpath = SOYUN / baseline_run_id / "manifest.json"
    if not bpath.is_file():
        b["note"] = f"baseline run '{baseline_run_id}' not found under results/soyun/"
        return b
    try:
        ballm = json.loads(bpath.read_text())
    except Exception as exc:
        b["note"] = f"baseline manifest unreadable: {exc!r}"
        return b
    bgpus = sorted({ph.get("gpu") for ph in ballm.get("phases", []) if ph.get("gpu")})
    b["baseline_gpu"] = bgpus
    if not bgpus or any(g != current_gpu for g in bgpus):
        b["note"] = (
            f"baseline ran on a different GPU/instance {bgpus} != current "
            f"{current_gpu!r}; latency speedup not computable "
            "(prior-instance runs are never valid latency baselines)"
        )
        return b
    # note: baseline's own manifest["instance_changed"] only means some *other*
    # run in results/soyun/ used a different GPU -- it does not disqualify this
    # baseline, whose per-phase GPU strings were just checked against current_gpu.
    # Without --baseline-phase the *last* phase carrying latency metrics wins.
    # When the baseline lives in the same run-id as the current phase that would
    # silently resolve to the current phase itself (speedup == 1.0), so a
    # multi-phase run must name its baseline phase explicitly.
    bl = None
    for ph in ballm.get("phases", []):
        if baseline_phase is not None and ph.get("phase") != baseline_phase:
            continue
        m = ph.get("result", {}).get("metrics", {})
        if "inference_latency_mean_ms" in m:
            bl = {"phase": ph.get("phase"),
                  **{k: m.get(k) for k in _LAT}}
    if bl is None:
        b["note"] = (
            f"baseline run '{baseline_run_id}'"
            + (f" phase '{baseline_phase}'" if baseline_phase else "")
            + " has no inference_latency metrics"
        )
        return b
    b["baseline_phase"] = bl["phase"]
    b["baseline_latency_ms"] = {k: bl[k] for k in _LAT}
    rows = []
    for ph in this_phases:
        m = ph.get("metrics", {})
        if "inference_latency_mean_ms" not in m:
            continue
        row = {"phase": ph.get("phase"),
               "latency_ms": {k: m.get(k) for k in _LAT}}
        for k in _LAT:
            tag = k.replace("inference_latency_", "").replace("_ms", "")
            cur, base = m.get(k), bl[k]
            row[f"speedup_{tag}"] = (base / cur) if (cur and base) else None
        rows.append(row)
    b["per_phase"] = rows
    if rows:
        b["latency_speedup_mean"] = rows[-1]["speedup_mean"]
    return b


def write_summary(run_dir, current_gpu, baseline_run_id, baseline_phase=None):
    mpath = run_dir / "manifest.json"
    allm = json.loads(mpath.read_text())
    phases = []
    for ph in allm.get("phases", []):
        r = ph.get("result", {})
        phases.append({
            "phase": ph.get("phase"),
            "utc": ph.get("utc"),
            "status": r.get("status"),
            "error": r.get("error"),
            "wall_seconds": r.get("wall_seconds"),
            "parsed": ph.get("parsed"),
            "metrics": r.get("metrics", {}),
        })
    summary = {
        "run_id": allm.get("run_id"),
        "gpu": current_gpu,
        "instance_changed": allm.get("instance_changed", False),
        "prior_run_gpus": allm.get("prior_run_gpus", {}),
        "phases": phases,
        "baseline": (_speedup_vs_baseline(baseline_run_id, current_gpu, phases,
                                          baseline_phase)
                     if baseline_run_id else None),
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


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
    ap.add_argument("--decision-trace", action="store_true",
                    help="write one JSON line per ABR decision to "
                         "results/soyun/<run-id>/<phase>/decisions.jsonl "
                         "(abr_spec/decision_trace.py; upstream untouched). "
                         "Record-building happens outside the CUDA-synced "
                         "latency window, so the measured latency is unaffected.")
    ap.add_argument("--speculative-drafter", default="mpc",
                    choices=("mpc", "repeat-last", "hybrid"),
                    help="which draft proposer run_plm.py should build. run_plm.py "
                         "is not modifiable, so this wrapper flag is applied by "
                         "abr_spec/drafter_select.py, which replaces the "
                         "RobustMPCDraftGenerator.from_video_size_dir classmethod "
                         "before run_plm.py executes. 'mpc' installs no patch.")
    ap.add_argument("--speculative-hybrid-buffer-threshold", type=float, default=5.0,
                    help="hybrid drafter: use MPC while buffer_size is below this "
                         "many seconds (default 5.0, from BASELINE6)")
    ap.add_argument("--speculative-hybrid-cv-threshold", type=float, default=0.30,
                    help="hybrid drafter: use MPC when the throughput coefficient "
                         "of variation is at least this (default 0.30, from BASELINE6)")
    ap.add_argument("--probe", default=None,
                    help="name of an abr_spec module exposing install(path); it is "
                         "imported and installed before run_plm.py executes "
                         "(e.g. --probe nan_probe). Diagnostics only.")
    ap.add_argument("--baseline-run-id", default=None,
                    help="results/soyun/<id> whose inference_latency is the speedup "
                         "reference; only used if its GPU string matches this run's")
    ap.add_argument("--baseline-phase", default=None,
                    help="phase inside --baseline-run-id to use as the latency "
                         "reference. REQUIRED when the baseline phase lives in the "
                         "same run-id as this phase, otherwise the reference "
                         "resolves to the current phase itself (speedup 1.0).")
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

    # ---- optional per-decision JSONL trace (soyun-owned, monkeypatch only) ----
    trace_path = None
    if args.decision_trace:
        sys.path.insert(0, str(REPO / "abr_spec"))
        import decision_trace
        trace_path = phase_dir / "decisions.jsonl"
        decision_trace.install(str(trace_path))
    if args.probe:
        sys.path.insert(0, str(REPO / "abr_spec"))
        probe = __import__(args.probe)
        probe.install(str(phase_dir / f"{args.probe}.json"))

    # ---- drafter selection (run_plm.py untouched; see drafter_select docstring) ----
    sys.path.insert(0, str(REPO / "abr_spec"))
    import drafter_select
    drafter_info = drafter_select.install(
        args.speculative_drafter,
        buffer_threshold=args.speculative_hybrid_buffer_threshold,
        cv_threshold=args.speculative_hybrid_cv_threshold,
    )

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
        "decision_trace": (None if trace_path is None
                           else str(trace_path.relative_to(REPO))),
        "drafter": drafter_info,
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

    # ---- cross-instance guard: compare GPU string against earlier soyun runs ----
    cur_gpu = manifest["gpu"]
    prior_gpus = prior_run_gpus(args.run_id)
    foreign = sorted({g for gs in prior_gpus.values() for g in gs if g and g != cur_gpu})
    manifest["current_gpu"] = cur_gpu
    manifest["prior_run_gpus"] = prior_gpus
    manifest["instance_changed"] = bool(foreign)
    if foreign:
        manifest["instance_change_note"] = (
            f"this run GPU {cur_gpu!r} differs from earlier results/soyun runs "
            f"{foreign}; inference_latency absolute values are NOT comparable across "
            "instances -- only a same-GPU run may serve as a latency baseline."
        )
        print("\n[run_wrapped] !! INSTANCE CHANGED", file=sys.stderr)
        print(f"[run_wrapped]    this run : {cur_gpu}", file=sys.stderr)
        for rid, gs in prior_gpus.items():
            if any(g != cur_gpu for g in gs):
                print(f"[run_wrapped]    {rid} : {gs}", file=sys.stderr)
        print("[run_wrapped]    -> manifest['instance_changed']=true; latency absolute "
              "values not comparable to those runs.\n", file=sys.stderr)
    if args.baseline_run_id and args.baseline_run_id in prior_gpus \
            and any(g != cur_gpu for g in prior_gpus[args.baseline_run_id]):
        print(f"[run_wrapped] !! --baseline-run-id {args.baseline_run_id} ran on "
              f"{prior_gpus[args.baseline_run_id]} != this GPU; speedup will be null.",
              file=sys.stderr)

    mpath = run_dir / "manifest.json"
    allm = (json.loads(mpath.read_text())
            if mpath.exists() else {"run_id": args.run_id, "phases": []})
    allm["phases"].append(manifest)
    allm["instance_changed"] = bool(foreign) or bool(allm.get("instance_changed"))
    allm["prior_run_gpus"] = prior_gpus
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

    metrics = read_metrics(phase_dir / "selector_metrics.json")

    decision_trace_info = None
    if trace_path is not None:
        try:
            import decision_trace as _dt
            _dt._S.fh.flush()
            n = sum(1 for _ in open(trace_path))
        except Exception as exc:  # pragma: no cover - defensive
            n = f"<error: {exc!r}>"
        decision_trace_info = {"path": str(trace_path.relative_to(REPO)),
                               "records": n}
        print(f"[run_wrapped] decision_trace records={n} -> {trace_path}")

    result = {
        "status": status,
        "error": err,
        "wall_seconds": round(wall, 2),
        "timing": timing,
        "metrics": metrics,
        "collected_result_files": collected,
        "checkpoint_files": ckpt_files,
        "checkpoint_dir": str(ckpt_dir.relative_to(REPO)),
        "console_log": str(log_path.relative_to(REPO)),
        "decision_trace": decision_trace_info,
        "drafter": drafter_info,
    }
    (phase_dir / "result.json").write_text(json.dumps(result, indent=2))
    allm = json.loads(mpath.read_text())
    allm["phases"][-1]["result"] = result
    mpath.write_text(json.dumps(allm, indent=2))

    # ---- run-level summary (all phases so far) + optional baseline speedup ----
    summary = write_summary(run_dir, cur_gpu, args.baseline_run_id,
                            args.baseline_phase)
    bl = summary.get("baseline")
    if bl:
        sp = bl.get("latency_speedup_mean")
        print(f"[run_wrapped] baseline={bl['baseline_run_id']} "
              f"latency_speedup_mean={sp if sp is None else round(sp, 3)}"
              + (f"  ({bl['note']})" if bl.get("note") else ""))

    lat = metrics.get("inference_latency_mean_ms")
    print(f"[run_wrapped] phase={args.phase} status={status} wall={wall:.1f}s "
          f"lat_mean_ms={None if lat is None else round(lat, 1)} "
          f"instance_changed={manifest['instance_changed']} collected={collected}")
    if status != "ok":
        print(f"[run_wrapped] FAILURE: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
